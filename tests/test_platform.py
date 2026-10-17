"""Platform tests: auth, datastore, devices, ingestion, RAG, live monitoring."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["FORCE_MOCK"] = "1"  # Offline embeddings/model for deterministic tests.

import auth
import datastore
import device_data
import devices
import ingest
import knowledge
import rag
from integrations import confluence, github
from live import rest_adapter, sim_feed
from live.inference import suggest_field_map
from live.monitor import LiveMonitor


class PlatformTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"AEGIS_LOCAL_STORE": self.tmp.name, "USE_FIRESTORE": "0",
                                            "GCS_BUCKET": "", "USE_SECRET_MANAGER": "0"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()


class AuthTests(PlatformTestBase):
    def test_password_hash_roundtrip_and_rejects_wrong(self):
        encoded = auth.hash_password("secret123")
        self.assertTrue(auth.verify_password("secret123", encoded))
        self.assertFalse(auth.verify_password("wrong", encoded))

    def test_short_password_rejected(self):
        with self.assertRaises(auth.AuthError):
            auth.hash_password("abc")

    def test_create_authenticate_and_duplicate(self):
        auth.create_user("eng@x.com", "secret123", "engineer")
        self.assertEqual(auth.authenticate("ENG@x.com", "secret123")["role"], "engineer")
        with self.assertRaises(auth.AuthError):
            auth.create_user("eng@x.com", "secret123", "engineer")
        with self.assertRaises(auth.AuthError):
            auth.authenticate("eng@x.com", "bad")

    def test_role_gating(self):
        self.assertTrue(auth.can_configure("admin"))
        self.assertFalse(auth.can_configure("engineer"))
        self.assertTrue(auth.can_operate("engineer"))
        self.assertFalse(auth.can_operate("user"))

    def test_seed_admin_only_once(self):
        first = auth.ensure_seed_admin()
        self.assertIsNotNone(first)
        self.assertIsNone(auth.ensure_seed_admin())


class DatastoreTests(PlatformTestBase):
    def test_crud_and_nearest(self):
        datastore.set_doc("c", "a", {"embedding": [1.0, 0.0], "text": "a"})
        datastore.set_doc("c", "b", {"embedding": [0.0, 1.0], "text": "b"})
        self.assertEqual(datastore.count_docs("c"), 2)
        nearest = datastore.nearest("c", [0.9, 0.1], top_k=1)
        self.assertEqual(nearest[0]["text"], "a")
        datastore.delete_doc("c", "a")
        self.assertEqual(datastore.count_docs("c"), 1)


class DeviceTests(PlatformTestBase):
    def test_create_list_update_delete(self):
        device = devices.create_device(name="Feeder 1", type="METER", criticality="high", protocol="rest")
        self.assertEqual(devices.get_device(device["id"])["name"], "Feeder 1")
        devices.update_device(device["id"], {"status": "ready"})
        self.assertEqual(devices.get_device(device["id"])["status"], "ready")
        devices.delete_device(device["id"])
        self.assertIsNone(devices.get_device(device["id"]))

    def test_invalid_protocol_and_criticality(self):
        with self.assertRaises(devices.DeviceError):
            devices.create_device(name="x", type="t", protocol="serial")
        with self.assertRaises(devices.DeviceError):
            devices.create_device(name="x", type="t", criticality="extreme")


class IngestionTests(PlatformTestBase):
    def test_chunking_overlaps_and_covers(self):
        text = "\n\n".join(f"Paragraph {i} about voltage and current." for i in range(200))
        chunks = ingest.chunk_text(text, size=500, overlap=100)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(chunks))

    def test_ingest_text_embeds_and_retrieves(self):
        device = devices.create_device(name="Meter", type="METER")
        record = ingest.ingest_text(device["id"], name="datasheet", kind="datasheet",
                                    text="The breaker trips when current exceeds the rated overload limit. "
                                         "Voltage sag indicates an upstream supply disturbance. " * 50)
        self.assertGreater(record["chunk_count"], 0)
        self.assertEqual(ingest.corpus_size(device["id"]), record["chunk_count"])
        hits = rag.retrieve(device["id"], "why did the breaker trip", top_k=3)
        self.assertTrue(hits)
        ingest.delete_source(device["id"], record["id"])
        self.assertEqual(ingest.corpus_size(device["id"]), 0)

    def test_extract_csv_and_text(self):
        self.assertIn("a,b", ingest.extract_text("x.csv", b"a,b\n1,2"))
        self.assertIn("hello", ingest.extract_text("x.txt", b"hello world"))

    def test_reembed_stale_fixes_dimension(self):
        device = devices.create_device(name="D", type="METER")
        ingest.ingest_text(device["id"], name="doc", kind="document", text="voltage sag info " * 40)
        datastore.set_doc(devices.chunks_path(device["id"]), "stale-1",
                          {"source_id": "s", "source_name": "old", "kind": "document", "index": 0,
                           "text": "calibration procedure for voltage and current", "embedding": [0.1] * 10})
        self.assertEqual(ingest.embedding_health(device["id"])["stale"], 1)
        result = ingest.reembed_stale(device["id"])
        self.assertEqual(result["reembedded"], 1)
        self.assertEqual(ingest.embedding_health(device["id"])["stale"], 0)


class RagTests(PlatformTestBase):
    def test_offline_answer_is_grounded_and_labeled(self):
        device = devices.create_device(name="Meter", type="METER")
        ingest.ingest_text(device["id"], name="doc", kind="document",
                           text="Harmonic distortion above the THD limit is mitigated by the active filter. " * 40)
        result = rag.answer(device["id"], "how is harmonic distortion handled?")
        self.assertTrue(result["grounded"])
        self.assertIn("Offline", result["answer"])
        self.assertTrue(result["sources"])

    def test_history_is_accepted_and_formatted(self):
        history = [{"role": "user", "content": "what is the capacity?"},
                   {"role": "assistant", "content": "200 waveforms."}]
        formatted = rag._format_history(history)
        self.assertIn("User: what is the capacity?", formatted)
        self.assertIn("Assistant: 200 waveforms.", formatted)
        device = devices.create_device(name="Meter", type="METER")
        ingest.ingest_text(device["id"], name="doc", kind="document", text="voltage sag info " * 40)
        # Offline answer should still work when history is passed.
        result = rag.answer(device["id"], "and the voltage?", history=history)
        self.assertTrue(result["grounded"])

    def test_no_corpus_returns_guidance(self):
        device = devices.create_device(name="Empty", type="METER")
        result = rag.answer(device["id"], "anything")
        self.assertFalse(result["grounded"])


class LiveMonitorTests(PlatformTestBase):
    def test_detects_escalates_and_auto_resolves(self):
        monitor = LiveMonitor(criticality="low", z_threshold=4.0)
        for _ in range(20):
            monitor.observe({"metrics": {"temperature_c": 35.0}, "codes": ["OK"]})
        monitor.observe({"metrics": {"temperature_c": 95.0}, "codes": []})  # anomaly
        self.assertEqual(monitor.summary()["issues"], 1)
        self.assertEqual(monitor.summary()["monitoring"], 1)
        for _ in range(3):
            monitor.observe({"metrics": {"temperature_c": 35.0}, "codes": ["OK"]})
        summary = monitor.summary()
        self.assertEqual(summary["auto_resolved"], 1)
        self.assertGreater(summary["cost_avoided_usd"], 0)

    def test_hard_code_forces_escalation(self):
        monitor = LiveMonitor(criticality="low")
        for _ in range(10):
            monitor.observe({"metrics": {"load_pct": 60.0}, "codes": ["OK"]})
        monitor.observe({"metrics": {"load_pct": 61.0}, "codes": ["BREAKER_OPEN"]})
        self.assertEqual(monitor.summary()["escalated"], 1)


class LiveAdapterTests(PlatformTestBase):
    def test_disabled_protocols(self):
        with self.assertRaises(rest_adapter.ProtocolDisabled):
            rest_adapter.poll("modbus", {})
        with self.assertRaises(rest_adapter.ProtocolDisabled):
            rest_adapter.poll("dlms", {})

    def test_dig_paths(self):
        self.assertEqual(rest_adapter._dig({"a": {"b": 3}}, "a.b"), 3)
        self.assertEqual(rest_adapter._dig({"r": [{"v": 9}]}, "r.0.v"), 9)

    def test_poll_rest_extracts_metrics(self):
        payload = {"data": {"voltage": 480.5, "temp": 36.0}, "status": "OK"}

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return payload

        with patch("live.rest_adapter.requests.get", return_value=FakeResponse()):
            reading = rest_adapter.poll("rest", {"endpoint": "http://x", "auth_mode": "none",
                                                 "field_map": {"voltage_v": "data.voltage"},
                                                 "event_path": "status"})
        self.assertEqual(reading["metrics"]["voltage_v"], 480.5)
        self.assertEqual(reading["codes"], ["OK"])

    def test_simulated_feed_shapes(self):
        reading = sim_feed.simulated_reading(5, inject_anomaly=True)
        self.assertIn("temperature_c", reading["metrics"])
        self.assertTrue(reading["codes"])


class InferenceAndIntegrationParsers(PlatformTestBase):
    def test_offline_field_map_heuristic(self):
        device = devices.create_device(name="M", type="METER")
        sample = json.dumps({"data": {"voltage_v": 480, "current_a": 12.0, "note": "x"}})
        result = suggest_field_map(device["id"], sample)
        self.assertEqual(result["field_map"].get("voltage_v"), "data.voltage_v")

    def test_github_parse_repo(self):
        self.assertEqual(github.parse_repo("https://github.com/eaton/prism.git"), ("eaton", "prism"))
        self.assertEqual(github.parse_repo("eaton/prism"), ("eaton", "prism"))
        with self.assertRaises(ValueError):
            github.parse_repo("justone")

    def test_github_ingest_reports_progress(self):
        device = devices.create_device(name="D", type="METER")
        files = [{"path": f"src/f{i}.c", "sha": f"sha{i}", "size": 100} for i in range(5)]
        calls = []
        with patch("integrations.github._default_branch", return_value="main"), \
             patch("integrations.github._list_files", return_value=(files, False, 5, "treesha")), \
             patch("integrations.github._fetch_blob", side_effect=lambda o, r, s: "register map voltage " * 30):
            result = github.ingest_repo(device["id"], "o/r",
                                        on_progress=lambda done, total, label: calls.append((done, total)))
        self.assertEqual(result["files"], 5)
        self.assertEqual(calls[-1], (5, 5))
        self.assertEqual(ingest.corpus_size(device["id"]), result["chunks"])
        for path in ("src/main.c", "inc/driver.hpp", "CMakeLists.txt", "Makefile",
                     "docs/readme.md", "build/toolchain.cmake", "data/registers.csv", "Dockerfile"):
            self.assertTrue(github._is_text_path(path), path)
        for path in ("firmware.bin", "image.png", "logo.svg", "archive.zip"):
            self.assertFalse(github._is_text_path(path), path)

    def test_confluence_page_id_and_html(self):
        self.assertEqual(confluence.page_id_from("12345"), "12345")
        self.assertEqual(confluence.page_id_from("https://x.atlassian.net/wiki/spaces/A/pages/777/Title"), "777")
        self.assertIn("Hello", confluence._html_to_text("<p>Hello</p><p>World</p>"))

    def test_confluence_base_normalizes_to_origin(self):
        with patch.dict(os.environ, {"CONFLUENCE_BASE_URL": "https://eaton-corp.atlassian.net/wiki/spaces/Perseus/",
                                     "CONFLUENCE_EMAIL": "a@b.com", "CONFLUENCE_API_TOKEN": "tok"}):
            base, _, _ = confluence._config()
        self.assertEqual(base, "https://eaton-corp.atlassian.net")


class DeviceDataTests(PlatformTestBase):
    def test_set_get_clear_dataset_local(self):
        device = devices.create_device(name="D", type="METER")
        dataset = device_data.build_prism_demo_dataset()
        device_data.set_dataset(device["id"], dataset)
        self.assertEqual(device_data.mode(device["id"]), "dataset")
        loaded = device_data.get_dataset(device["id"])
        self.assertEqual(len(loaded.assets), len(dataset.assets))
        device_data.set_synthetic(device["id"])
        self.assertEqual(device_data.mode(device["id"]), "synthetic")
        self.assertIsNone(device_data.get_dataset(device["id"]))


def _fake_repo_ingest(device_id, ref, branch, link_id=None, on_progress=None):
    ingest.ingest_text(device_id, name=f"github:{ref}/f1", kind="github",
                       text="voltage and current register map " * 40, link_id=link_id)
    if on_progress:
        on_progress(1, 1, "f1")
    return {"files": 1, "chunks": 1, "repo": ref, "branch": "main",
            "matched": 1, "capped": False, "tree_truncated": False}


def _make_github_mocks(state: dict):
    """Build repo_listing / ingest_items side effects driven by a mutable file->sha map."""
    def fake_listing(ref, branch=None):
        files = [{"path": path, "sha": sha, "size": 100} for path, sha in state["files"].items()]
        return {"owner": "o", "repo": "r", "branch": "main", "tree_sha": state["tree"],
                "files": files, "truncated": False, "matched": len(files)}

    def fake_items(device_id, owner, repo, items, link_id=None, on_progress=None, done_offset=0, total=None):
        total = total if total is not None else len(items)
        count = 0
        for item in items:
            ingest.ingest_text(device_id, name=f"github:o/r/{item['path']}", kind="github",
                               text="register map content " * 30, link_id=link_id,
                               meta={"path": item["path"], "blob_sha": item["sha"]})
            count += 1
            if on_progress:
                on_progress(count, total, item["path"])
        return count, count
    return fake_listing, fake_items


class KnowledgePersistenceTests(PlatformTestBase):
    def test_corpus_accumulates_and_persists_across_reads(self):
        device = devices.create_device(name="D", type="METER")
        ingest.ingest_text(device["id"], name="a", kind="document", text="voltage sag info " * 40)
        ingest.ingest_text(device["id"], name="b", kind="document", text="breaker trip info " * 40)
        size = ingest.corpus_size(device["id"])
        self.assertGreaterEqual(size, 2)
        self.assertEqual(ingest.corpus_size(device["id"]), size)
        self.assertEqual(len(ingest.list_sources(device["id"])), 2)

    def test_incremental_refresh_only_processes_changes(self):
        device = devices.create_device(name="D", type="METER")
        state = {"files": {"a.c": "s1", "b.c": "s2"}, "tree": "t1"}
        listing, items = _make_github_mocks(state)
        with patch("knowledge.github.repo_listing", side_effect=listing), \
             patch("knowledge.github.ingest_items", side_effect=items):
            first = knowledge.add_or_refresh(device["id"], "github", "o/r")
            self.assertEqual(first["added"], 2)
            self.assertFalse(first.get("skipped"))
            base_corpus = ingest.corpus_size(device["id"])

            # Unchanged tree -> whole repo skipped, no re-embedding.
            second = knowledge.add_or_refresh(device["id"], "github", "o/r")
            self.assertTrue(second["skipped"])
            self.assertEqual(ingest.corpus_size(device["id"]), base_corpus)

            # One file changes -> only that file is re-embedded; counts reflect it.
            state["files"]["b.c"] = "s2b"
            state["tree"] = "t2"
            third = knowledge.add_or_refresh(device["id"], "github", "o/r")
            self.assertEqual(third["updated"], 1)
            self.assertEqual(third["added"], 0)
            self.assertEqual(third["unchanged"], 1)

            # A removed file drops its sources.
            del state["files"]["a.c"]
            state["tree"] = "t3"
            fourth = knowledge.add_or_refresh(device["id"], "github", "o/r")
            self.assertEqual(fourth["removed"], 1)
            paths = {s.get("path") for s in ingest.sources_by_link(device["id"], knowledge._link_id("github", "o/r"))}
            self.assertEqual(paths, {"b.c"})

    def test_reingest_all_reports_progress(self):
        device = devices.create_device(name="D", type="METER")
        state = {"files": {"a.c": "s1", "b.c": "s2"}, "tree": "t1"}
        listing, items = _make_github_mocks(state)
        calls = []
        with patch("knowledge.github.repo_listing", side_effect=listing), \
             patch("knowledge.github.ingest_items", side_effect=items):
            knowledge.add_or_refresh(device["id"], "github", "o/r")  # create the saved link
            state["files"]["b.c"] = "s2b"  # a change so re-ingest does work
            state["tree"] = "t2"
            knowledge.reingest_all(device["id"], on_progress=lambda d, t, label: calls.append(label))
        self.assertTrue(calls)

    def test_force_full_reingest(self):
        device = devices.create_device(name="D", type="METER")
        state = {"files": {"a.c": "s1"}, "tree": "t1"}
        listing, items = _make_github_mocks(state)
        with patch("knowledge.github.repo_listing", side_effect=listing), \
             patch("knowledge.github.ingest_items", side_effect=items):
            knowledge.add_or_refresh(device["id"], "github", "o/r")
            forced = knowledge.add_or_refresh(device["id"], "github", "o/r", force=True)
        self.assertFalse(forced.get("skipped"))
        self.assertEqual(forced["added"], 1)

    def test_links_persist_and_delete(self):
        device = devices.create_device(name="D", type="METER")
        state = {"files": {"a.c": "s1"}, "tree": "t1"}
        listing, items = _make_github_mocks(state)
        with patch("knowledge.github.repo_listing", side_effect=listing), \
             patch("knowledge.github.ingest_items", side_effect=items):
            knowledge.add_or_refresh(device["id"], "github", "o/r1")
            state2 = {"files": {"x.c": "s9"}, "tree": "t9"}
            listing2, items2 = _make_github_mocks(state2)
            with patch("knowledge.github.repo_listing", side_effect=listing2), \
                 patch("knowledge.github.ingest_items", side_effect=items2):
                knowledge.add_or_refresh(device["id"], "github", "o/r2")
        links = knowledge.list_links(device["id"])
        self.assertEqual(len(links), 2)
        corpus_before = ingest.corpus_size(device["id"])
        knowledge.delete_link(device["id"], links[0]["id"])
        self.assertEqual(len(knowledge.list_links(device["id"])), 1)
        self.assertLess(ingest.corpus_size(device["id"]), corpus_before)


if __name__ == "__main__":
    unittest.main()
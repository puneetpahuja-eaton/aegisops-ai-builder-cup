import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import bq
from fleet_data import FleetDataset, csv_template, demo_dataset, load_bundle, load_csv
from fleet_models import LearnedDetectors
from fleet_runtime import FleetEngine
from gemini_client import ModelUnavailable
from power_demo import POWER_SCENARIOS, power_demo_dataset

SOP = (Path(__file__).resolve().parents[1] / "data" / "sop.md").read_text(encoding="utf-8")


class FleetTests(unittest.TestCase):
    def setUp(self):
        self.data = demo_dataset()

    def engine(self, uploaded=False):
        if uploaded:
            self.data.source = "uploaded"
        return FleetEngine(self.data, SOP, offline=True)

    def fault(self, engine):
        engine.tick()
        engine.tick()
        return next(case for case in engine.cases if case["category"] == "electrical_supply")

    def test_csv_and_json_replace_sample_source_and_roundtrip(self):
        loaded = load_csv(csv_template(self.data))
        self.assertEqual(loaded.source, "uploaded")
        self.assertEqual(len(loaded.telemetry), 48)
        self.assertEqual(load_bundle(self.data.model_dump_json()).source, "uploaded")
        self.assertEqual(loaded.assets[1].parent_id, "FEEDER-01")

    def test_cycle_unknown_asset_duplicate_nonfinite_and_incomplete_rejected(self):
        invalid = []
        cycle = self.data.model_dump(mode="json")
        cycle["assets"][0]["parent_id"] = "MTR-07"
        invalid.append(cycle)
        missing = self.data.model_dump(mode="json")
        missing["telemetry"].pop()
        invalid.append(missing)
        unknown = self.data.model_dump(mode="json")
        unknown["telemetry"][0]["asset_id"] = "not-a-fleet-asset"
        invalid.append(unknown)
        duplicate = self.data.model_dump(mode="json")
        duplicate["telemetry"].append(duplicate["telemetry"][0])
        invalid.append(duplicate)
        nonfinite = self.data.model_dump(mode="json")
        nonfinite["history"][0]["metrics"]["voltage_v"] = float("nan")
        invalid.append(nonfinite)
        for payload in invalid:
            with self.subTest(payload=invalid.index(payload)), self.assertRaises(ValueError):
                FleetDataset.model_validate(payload)

    def test_future_history_and_changing_metrics_rejected(self):
        payload = self.data.model_dump(mode="json")
        payload["history"][0]["timestamp"] = payload["telemetry"][-1]["timestamp"]
        with self.assertRaises(ValueError):
            FleetDataset.model_validate(payload)
        payload = self.data.model_dump(mode="json")
        payload["telemetry"][0]["metrics"].pop("current_a")
        with self.assertRaises(ValueError):
            FleetDataset.model_validate(payload)

    def test_unknown_phase_metadata_and_oversized_upload_rejected(self):
        text = csv_template(self.data)
        with self.assertRaises(ValueError):
            load_csv(text.replace(",history,", ",bad-phase,", 1))
        with self.assertRaises(ValueError):
            load_bundle(" " * 2_000_001)

    def test_models_train_on_history_only(self):
        detector = LearnedDetectors(self.data)
        expected = detector.states["MTR-07"]["median"].copy()
        self.data.telemetry[0].metrics["voltage_v"] = 999_999
        altered = LearnedDetectors(self.data)
        np.testing.assert_array_equal(expected, altered.states["MTR-07"]["median"])

    def test_detector_sees_fault_and_markov_does_not_flag_benign_rare_code(self):
        detector = LearnedDetectors(self.data)
        reading = next(row for row in self.data.telemetry if row.asset_id == "FEEDER-01" and "VOLT_SAG" in row.event_codes)
        self.assertTrue(detector.score(reading)["is_anomaly"])
        self.assertTrue(detector.scan_codes(reading, ["OK"])["is_anomaly"])
        reading.event_codes = ["SELFTEST_PASS"]
        self.assertFalse(detector.scan_codes(reading, ["OK"])["is_anomaly"])

    def test_topology_groups_symptoms_and_cases_are_deduplicated(self):
        engine = self.engine()
        case = self.fault(engine)
        self.assertEqual(case["root_asset_id"], "FEEDER-01")
        self.assertEqual(case["symptom_asset_ids"], ["MTR-07", "PMP-03"])
        engine.tick()
        self.assertEqual(len([case for case in engine.cases if case["category"] == "electrical_supply"]), 1)
        self.assertEqual(engine.ancestors("MTR-07"), ["FEEDER-01"])
        self.assertIn("correlate_topology", [event["tool"] for event in engine.trace])
        # Vertex prompts must be native JSON, not numpy scalars coerced into strings.
        encoded = json.loads(json.dumps(case["evidence"]))
        self.assertIsInstance(encoded["fleet_context"]["correlated_observations"]["FEEDER-01"]["metric_model"]["signals"][0]["anomalous"], bool)

    def test_approval_requires_name_and_later_samples(self):
        engine = self.engine()
        case = self.fault(engine)
        self.assertEqual(case["status"], "AWAITING_APPROVAL")
        with self.assertRaises(ValueError):
            engine.approve(case["case_id"], " ")
        engine.approve(case["case_id"], "Supervisor")
        self.assertEqual(case["status"], "ACTING")
        engine.tick()
        self.assertEqual(case["status"], "ACTING")
        engine.tick()
        self.assertEqual(case["status"], "RESOLVED")
        self.assertEqual(case["verification"]["status"], "simulated_recovery")
        self.assertEqual(case["value"]["realized_usd"], 0)
        # Original timeline and caller's dataset remain untouched.
        self.assertEqual(engine.frames[2][1]["FEEDER-01"].metrics["voltage_v"], 330)
        self.assertEqual(self.data.telemetry[8].metrics["voltage_v"], 330)

    def test_upload_approval_never_changes_measurements_and_times_out(self):
        engine = self.engine(uploaded=True)
        case = self.fault(engine)
        engine.approve(case["case_id"], "Observer")
        for _ in range(3):
            engine.tick()
        self.assertEqual(case["status"], "FAILED")
        self.assertEqual(engine.latest["FEEDER-01"]["reading"].metrics["voltage_v"], 330)
        self.assertEqual(engine.simulated_fixes, {})

    def test_uploaded_observed_recovery_is_not_claimed_as_repair_or_savings(self):
        engine = self.engine(uploaded=True)
        case = self.fault(engine)
        for index in (2, 3):
            for asset_id in ["FEEDER-01", "MTR-07", "PMP-03"]:
                row = engine.frames[index][1][asset_id]
                row.metrics["voltage_v"] = 400
                row.event_codes = ["OK"]
        engine.approve(case["case_id"], "Observer")
        engine.tick()
        engine.tick()
        self.assertEqual(case["verification"]["status"], "observed_recovery")
        self.assertEqual(case["value"]["potential_usd"], 0)
        engine.tick()
        self.assertEqual(case["status"], "REOPENED")

    def test_local_bearing_fault_is_not_swallowed_by_upstream_group(self):
        engine = self.engine()
        for _ in range(5):
            engine.tick()
        bearing = next(case for case in engine.cases if case["category"] == "bearing")
        self.assertEqual(bearing["root_asset_id"], "PMP-03")
        self.assertEqual(bearing["status"], "ESCALATED")
        self.assertIn("bearing", bearing["diagnosis"]["root_cause"].lower())
        with self.assertRaises(ValueError):
            engine.approve(bearing["case_id"], "Supervisor")

    def test_events_are_emitted_during_work_not_only_at_end(self):
        engine = self.engine()
        engine.tick()
        seen = []
        with patch("orchestrator.diagnose", side_effect=ModelUnavailable("test outage")):
            engine.tick(on_event=lambda event: seen.append((engine.cursor, event["agent"], event["tool"])))
        case = engine.cases[0]
        self.assertEqual(case["status"], "ERROR")
        self.assertTrue(case["errors"])
        self.assertEqual(case["diagnosis"]["_source"], "unavailable")
        self.assertTrue(all(cursor == 1 for cursor, _, _ in seen))
        self.assertIn((1, "Diagnostician", "grounded_diagnosis_started"), seen)
        self.assertIsNone(engine.callback)

    def test_full_replay_and_audit_are_serializable(self):
        engine = self.engine()
        while not engine.at_end:
            engine.tick()
        self.assertGreaterEqual(len(engine.cases), 3)
        self.assertTrue(json.dumps(engine.audit(), default=lambda value: value.isoformat()))
        with self.assertRaises(ValueError):
            engine.tick()

    def test_critical_downstream_asset_forces_supply_escalation(self):
        self.data.assets[1].criticality = "critical"
        engine = self.engine()
        case = self.fault(engine)
        self.assertEqual(case["status"], "ESCALATED")
        self.assertTrue(any("critical" in reason for reason in case["decision"]["reasons"]))

    def test_unknown_code_gates_an_otherwise_valid_sandbox(self):
        for row in self.data.telemetry:
            if row.asset_id == "FEEDER-01" and "VOLT_SAG" in row.event_codes:
                row.event_codes.append("SITE_SPECIFIC_UNKNOWN")
        engine = self.engine()
        case = self.fault(engine)
        self.assertEqual(case["status"], "ESCALATED")

    def test_failed_analysis_can_be_retried_without_duplicate_case(self):
        engine = self.engine()
        engine.tick()
        with patch("orchestrator.diagnose", side_effect=ModelUnavailable("outage")):
            engine.tick()
        case = engine.cases[0]
        identifier = case["case_id"]
        engine.retry(identifier)
        self.assertEqual(len(engine.cases), 1)
        self.assertEqual(case["case_id"], identifier)
        self.assertEqual(case["status"], "AWAITING_APPROVAL")
        self.assertFalse(case["errors"])

    def test_unlabelled_voltage_anomaly_is_still_verified(self):
        for row in self.data.telemetry:
            row.event_codes = ["OK"]
        engine = self.engine()
        engine.tick()
        engine.tick()
        engine.tick()
        case = next(case for case in engine.cases if case["root_asset_id"] == "FEEDER-01")
        self.assertIn("voltage_v", case["verification_metrics"]["FEEDER-01"])

    def test_case_summaries_fit_existing_bigquery_contract(self):
        engine = self.engine()
        case = self.fault(engine)
        case["audit_revision"] = 9
        with patch("bq.client") as client, patch("bq.is_enabled", return_value=True), patch("bq.table_id", return_value="demo.audit.cases"):
            client.return_value.insert_rows_json.return_value = []
            self.assertEqual(bq.log_cases([case]), 1)
            row = client.return_value.insert_rows_json.call_args.args[1][0]
            self.assertEqual(row["revision"], 9)

    def test_prism_power_fleet_replays_all_six_scenarios(self):
        data = power_demo_dataset()
        self.assertEqual(len(data.assets), 22)
        self.assertEqual(len(data.history), 22 * 864)
        engine = FleetEngine(data, SOP, offline=True, evaluation_scenarios=POWER_SCENARIOS)
        while not engine.at_end:
            engine.tick()
        evaluation = engine.evaluation()
        self.assertEqual(len(evaluation), 6)
        self.assertTrue(all(row["detected"] for row in evaluation), evaluation)
        self.assertTrue(all(row["detection_delay_ticks"] == 0 for row in evaluation), evaluation)
        self.assertTrue(all(case["decision"]["autonomous"] is False for case in engine.cases))
        battery = next(case for case in engine.cases if case["category"] == "battery")
        self.assertEqual(battery["status"], "ESCALATED")
        # A breaker cutting downstream current/load is one topology case, not duplicate local cases.
        self.assertFalse(any(case["category"] == "local" and case["opened_tick"] >= 78
                             and case["root_asset_id"] in {"BRK-4", "RACK-4"} for case in engine.cases))
        self.assertFalse(any("ground_truth" in str(event["result"]) for event in engine.trace))


if __name__ == "__main__":
    unittest.main()

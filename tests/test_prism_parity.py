from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from streamlit.testing.v1 import AppTest

from prism_cloud import Engine, ReferenceEngine, load_topology
from prism_extensions import template
from gemini_client import ModelUnavailable

ROOT = Path(__file__).resolve().parents[1]


class PrismParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ, {"FORCE_MOCK": "1", "GCS_BUCKET": "", "BQ_DATASET": ""})
        cls.environment.start()
        cls.reference = ReferenceEngine()
        cls.integrated = Engine(offline=True)
        cls.reference.run_all()
        cls.integrated.run_all()

    @classmethod
    def tearDownClass(cls):
        cls.environment.stop()

    def test_canonical_package_is_byte_identical_to_reference_manifest(self):
        manifest = json.loads((ROOT / "prism_reference" / "manifest.json").read_text())
        for name, expected in manifest.items():
            if name.startswith("dashboard/"):
                continue
            actual = hashlib.sha256((ROOT / "prism_reference" / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)

    def test_all_96_snapshots_and_events_equal_original_prism(self):
        for tick in range(96):
            for asset in self.reference.topo.all_ids():
                self.assertEqual(self.reference.history[tick][asset], self.integrated.history[tick][asset],
                                 f"sample {tick} / {asset}")
        self.assertEqual(self.reference.events, self.integrated.events)
        self.assertEqual(self.reference.score_hist, self.integrated.score_hist)
        self.assertEqual(self.reference.surprise_hist, self.integrated.surprise_hist)

    def test_all_case_fields_and_lifecycle_equal_original_prism(self):
        self.assertEqual([asdict(case) for case in self.reference.cases],
                         [asdict(case) for case in self.integrated.cases])
        self.assertGreaterEqual(len(self.integrated.cases), 6)
        self.assertGreaterEqual(sum(case.status == "RESOLVED" for case in self.integrated.cases), 4)
        self.assertTrue(all(detail.get("simulator_only") for detail in self.integrated.cloud_cases.values()))
        self.assertTrue(all(not detail.get("equipment_commands_sent") for detail in self.integrated.cloud_cases.values()))

    def test_training_fields_and_learned_models_equal_original(self):
        self.assertEqual(self.reference.train_report, self.integrated.train_report)
        for asset_id in self.reference.topo.all_ids():
            for field in ("median", "scale", "mean", "inv_cov", "if_std"):
                np.testing.assert_array_equal(self.reference.metric_model.assets[asset_id][field],
                                              self.integrated.metric_model.assets[asset_id][field])

    def test_counterfactual_value_and_topology_fields_equal_original(self):
        actual, expected = self.integrated.summary(), self.reference.summary()
        actual.pop("tool_calls")
        expected.pop("tool_calls")
        self.assertEqual(actual, expected)
        self.assertEqual([asdict(asset) for asset in self.integrated.topo.assets.values()],
                         [asdict(asset) for asset in self.reference.topo.assets.values()])
        for asset in ("XFMR-1", "UPS-3", "PDU-1", "BRK-4"):
            for metric in ("voltage_v", "temperature_c", "load_pct", "thd_pct", "battery_soc_pct"):
                self.assertEqual(self.reference.baseline_series(asset, metric), self.integrated.baseline_series(asset, metric))
                self.assertEqual(self.reference.asset_series(asset, metric), self.integrated.asset_series(asset, metric))

    def test_all_original_named_tools_are_preserved_with_cloud_tools_added(self):
        original = {call.tool for call in self.reference.tool_calls}
        integrated = {call.tool for call in self.integrated.tool_calls}
        self.assertTrue(original.issubset(integrated))
        self.assertIn("gemini_grounded_diagnosis", integrated)
        self.assertIn("gemini_work_order", integrated)
        self.assertIn("validate_sop_citations", integrated)
        json.dumps(self.integrated.audit())

    def test_uploaded_data_replaces_topology_and_never_auto_remediates(self):
        data = template(self.integrated)
        self.assertLess(len(data.model_dump_json().encode()), 2_000_000)
        data.source = "uploaded"
        engine = Engine(offline=True, dataset=data)
        original = data.model_dump_json()
        for _ in range(16):
            engine.tick()
        self.assertEqual(data.model_dump_json(), original)
        self.assertTrue(engine.cases)
        self.assertTrue(all(case.status == "ESCALATED" for case in engine.cases))
        self.assertTrue(all(case.decision == "ESCALATE" for case in engine.cases))
        self.assertTrue(all(case.cost_avoided_usd == 0 for case in engine.cases))
        self.assertIsNone(engine.summary()["diagnosis_accuracy"])
        self.assertEqual(engine.faults, [])
        self.assertEqual(engine.baseline_sample(14), engine.history[14])
        self.assertEqual(engine.topo.get("UPS-1").site, self.integrated.topo.get("UPS-1").site)
        self.assertEqual(engine.topo.get("UPS-1").rated_kw, self.integrated.topo.get("UPS-1").rated_kw)

    def test_cloud_failure_escalates_without_faking_a_success(self):
        engine = Engine(offline=True)
        for _ in range(12):
            engine.tick()
        with patch("prism_cloud.diagnose", side_effect=ModelUnavailable("unavailable")):
            engine.tick()
        self.assertTrue(engine.cases)
        self.assertTrue(all(case.status == "ESCALATED" for case in engine.cases))
        self.assertTrue(all(detail["errors"] for detail in engine.cloud_cases.values()))
        self.assertTrue(all(fault.resolved_sample is None for fault in engine.faults))

    def test_dashboard_has_all_original_tabs_controls_and_metrics(self):
        app = AppTest.from_file(str(ROOT / "prism_reference" / "dashboard" / "app.py"), default_timeout=60).run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual([tab.label for tab in app.tabs],
                         ["Live Operations", "Cases", "Counterfactual (value)", "Power Topology", "Models & Data", "How it works"])
        labels = {button.label for button in app.button}
        self.assertTrue({"Play", "Pause", "Reset", "Step once"}.issubset(labels))
        metrics = {metric.label for metric in app.metric}
        self.assertTrue({"Cases", "Auto-resolved", "Escalated", "Diagnosis acc.", "Downtime avoided", "Cost avoided",
                         "History per asset", "Assets modelled", "Code transitions learned"}.issubset(metrics))
        next(button for button in app.button if button.label == "Step once").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["engine"].current_idx, 0)
        next(button for button in app.button if button.label == "Reset").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["engine"].current_idx, -1)

    def test_invalid_cloud_topology_fails_explicitly(self):
        for text in ("asset_id,name\nA,A", "asset_id,name,type,parent_id,site,rated_kw,criticality\nA,A,UPS,A,S,1,HIGH"):
            with self.assertRaises(ValueError):
                load_topology(text)


if __name__ == "__main__":
    unittest.main()

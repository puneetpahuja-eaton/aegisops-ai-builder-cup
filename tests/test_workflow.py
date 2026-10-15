import copy
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from diagnostician import offline_diagnose, validate_diagnosis
from evidence import build_evidence, robust_z
from gemini_client import ModelUnavailable
from orchestrator import approve_simulation, run_case
from verifier import verify
import bq
import storage

DATA = Path(__file__).resolve().parents[1] / "data"
SOP = (DATA / "sop.md").read_text(encoding="utf-8")
SCENARIOS = json.loads((DATA / "scenarios.json").read_text())


class WorkflowTests(unittest.TestCase):
    def test_fleet_requires_review_and_never_reports_real_savings(self):
        cases = [run_case(incident, SOP, offline=True) for incident in SCENARIOS]
        self.assertEqual([c["decision"]["action"] for c in cases], ["propose_simulation", "escalate", "propose_simulation", "escalate"])
        self.assertTrue(all(c["value"]["cost_avoided_usd"] == 0 for c in cases))
        self.assertTrue(all(not c["decision"]["autonomous"] for c in cases))
        self.assertEqual(cases[0]["verification"]["status"], "pending_approval")
        approve_simulation(cases[0], "Demo supervisor")
        self.assertEqual(cases[0]["verification"]["status"], "simulated_recovery")

    def test_no_post_readings_means_unverified(self):
        incident = copy.deepcopy(SCENARIOS[0])
        incident.pop("post_action_metrics")
        case = run_case(incident, SOP, offline=True)
        approve_simulation(case, "Reviewer")
        self.assertEqual(case["verification"]["status"], "unverified")
        self.assertEqual(case["value"]["potential_usd"], 0)

    def test_failed_recovery_reopens(self):
        incident = copy.deepcopy(SCENARIOS[0])
        incident["post_action_metrics"]["winding_temp_c"] = 100
        case = run_case(incident, SOP, offline=True)
        approve_simulation(case, "Reviewer")
        self.assertEqual(case["verification"]["status"], "reopened")

    def test_escalation_cannot_be_approved(self):
        with self.assertRaises(ValueError):
            approve_simulation(run_case(SCENARIOS[1], SOP, offline=True), "Reviewer")

    def test_empty_approval_rejected(self):
        with self.assertRaises(ValueError):
            approve_simulation(run_case(SCENARIOS[0], SOP, offline=True), " ")

    def test_model_outage_is_explicit_and_does_not_fake_gemini(self):
        with patch("orchestrator.diagnose", side_effect=ModelUnavailable("503")):
            case = run_case(SCENARIOS[0], SOP)
        self.assertEqual(case["diagnosis"]["_source"], "unavailable")
        self.assertEqual(case["decision"]["action"], "escalate")
        self.assertTrue(case["errors"])

    def test_missing_sop_fails(self):
        with self.assertRaises(ValueError):
            offline_diagnose(build_evidence(SCENARIOS[0]), "")

    def test_invalid_citation_rejected(self):
        evidence = build_evidence(SCENARIOS[0])
        result = offline_diagnose(evidence, SOP)
        result["citation_quotes"]["SOP-101"] = "fabricated quote"
        with self.assertRaises(ValueError):
            validate_diagnosis(result, evidence, SOP)

    def test_wrong_asset_rejected(self):
        evidence = build_evidence(SCENARIOS[0])
        result = offline_diagnose(evidence, SOP)
        result["asset_id"] = "OTHER"
        with self.assertRaises(ValueError):
            validate_diagnosis(result, evidence, SOP)

    def test_whitespace_only_citation_changes_are_valid(self):
        evidence = build_evidence(SCENARIOS[0])
        result = offline_diagnose(evidence, SOP)
        result["citation_quotes"]["SOP-101"] = result["citation_quotes"]["SOP-101"].replace(" ", "\n")
        validate_diagnosis(result, evidence, SOP)

    def test_all_supporting_quotes_are_checked(self):
        evidence = build_evidence(SCENARIOS[0])
        result = offline_diagnose(evidence, SOP)
        result["citation_quotes"] = [
            {"sop_id": "SOP-101", "quote": "invented"},
            {"sop_id": "SOP-101", "quote": "FAN-SLOW is supporting evidence, not proof of a failed fan."},
        ]
        with self.assertRaises(ValueError):
            validate_diagnosis(result, evidence, SOP)

    def test_invalid_types_rejected(self):
        evidence = build_evidence(SCENARIOS[0])
        for key, invalid in [("confidence", 2), ("escalate", "false")]:
            result = offline_diagnose(evidence, SOP)
            result[key] = invalid
            with self.assertRaises(ValueError):
                validate_diagnosis(result, evidence, SOP)

    def test_empty_nan_baseline_rejected(self):
        for baseline in ([], [float("nan")] * 5):
            with self.assertRaises(ValueError):
                robust_z(baseline, 1)

    def test_constant_baseline_is_finite(self):
        self.assertEqual(robust_z([100] * 5, 100), 0)
        self.assertLess(robust_z([100] * 5, 101), 1)

    def test_unknown_asset_escalates(self):
        incident = copy.deepcopy(SCENARIOS[0])
        incident["asset"]["criticality"] = "unknown"
        self.assertEqual(run_case(incident, SOP, offline=True)["decision"]["action"], "escalate")

    def test_configured_gcs_failure_not_hidden(self):
        with patch.dict(os.environ, {"GCS_BUCKET": "bad"}), patch("storage._gcs_text", side_effect=RuntimeError("denied")):
            with self.assertRaises(RuntimeError):
                storage.load_text("sop.md")

    def test_bq_row_errors_not_success(self):
        case = run_case(SCENARIOS[0], SOP, offline=True)
        with patch.dict(os.environ, {"BQ_DATASET": "audit", "GOOGLE_CLOUD_PROJECT": "demo"}), patch("bq.client") as client:
            client.return_value.insert_rows_json.return_value = [{"index": 0, "errors": ["denied"]}]
            with self.assertRaises(RuntimeError):
                bq.log_cases([case])

    def test_unknown_metric_escalates(self):
        incident = {"asset": {"id": "X", "type": "test", "criticality": "medium"}, "metrics": {"unknown": {"baseline": [1, 2, 1, 2, 1], "latest": 20}}}
        self.assertEqual(run_case(incident, SOP, offline=True)["decision"]["action"], "escalate")


if __name__ == "__main__":
    unittest.main()

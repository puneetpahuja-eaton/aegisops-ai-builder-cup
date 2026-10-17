import os
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "legacy_app.py"


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"FORCE_MOCK": "1", "GCS_BUCKET": "", "BQ_DATASET": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def incident_app(self):
        app = AppTest.from_file(str(APP)).run()
        return app.radio[0].set_value("Single incident").run()

    def test_offline_dashboard_retains_approved_case(self):
        app = self.incident_app()
        self.assertEqual(len(app.exception), 0)
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["cases"][0]["verification"]["status"], "pending_approval")
        app.text_input[0].set_value("Test reviewer").run()
        next(button for button in app.button if button.label == "Approve sandbox simulation").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["cases"][0]["verification"]["status"], "simulated_recovery")
        app.run()
        self.assertTrue(app.session_state["cases"][0]["approval"]["approved"])

    def test_mode_toggle_does_not_mutate_process_environment(self):
        app = self.incident_app()
        app.toggle[0].set_value(False).run()
        self.assertEqual(os.environ["FORCE_MOCK"], "1")
        self.assertEqual(len(app.exception), 0)

    def test_fleet_results_render_without_exceptions(self):
        app = self.incident_app()
        app.multiselect[0].set_value(["MTR-07", "PMP-03", "SWG-02", "PRESS-01"]).run()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.session_state["cases"]), 4)

    def test_audit_history_persists_across_reruns(self):
        with patch.dict(os.environ, {"BQ_DATASET": "audit"}), patch("bq.recent_history", return_value=[{"asset_id": "MTR-07"}]):
            app = self.incident_app()
            next(button for button in app.button if button.label == "Refresh audit history").click().run()
            self.assertEqual(len(app.exception), 0)
            self.assertEqual(app.session_state["audit_history"][0]["asset_id"], "MTR-07")
            app.run()
            self.assertEqual(len(app.dataframe), 1)

    def test_fleet_default_load_step_approve_verify_and_reset(self):
        app = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assertEqual(app.radio[0].value, "Fleet operations")
        next(button for button in app.button if button.label == "Load built-in synthetic fleet").click().run()
        self.assertEqual(len(app.exception), 0)
        for _ in range(2):
            next(button for button in app.button if button.label == "Process next timestamp").click().run()
        self.assertEqual(len(app.exception), 0)
        engine = app.session_state["fleet_engine"]
        case = engine.cases[0]
        self.assertEqual(case["status"], "AWAITING_APPROVAL")
        next(field for field in app.text_input if field.label == "Fleet reviewer name").set_value("Fleet supervisor").run()
        next(button for button in app.button if button.label == "Approve fleet sandbox").click().run()
        self.assertEqual(len(app.exception), 0)
        for _ in range(2):
            next(button for button in app.button if button.label == "Process next timestamp").click().run()
        self.assertEqual(app.session_state["fleet_engine"].cases[0]["status"], "RESOLVED")
        next(button for button in app.button if button.label == "Reset this replay").click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.session_state["fleet_engine"].cursor, 0)
        self.assertEqual(len(app.session_state["fleet_engine"].cases), 0)

    def test_fleet_sessions_are_isolated(self):
        first = AppTest.from_file(str(APP), default_timeout=20).run()
        next(button for button in first.button if button.label == "Load built-in synthetic fleet").click().run()
        second = AppTest.from_file(str(APP), default_timeout=20).run()
        self.assertNotIn("fleet_engine", second.session_state)

    def test_fleet_audit_feedback_survives_rerun(self):
        with patch.dict(os.environ, {"BQ_DATASET": "audit"}), patch("bq.log_cases", return_value=1):
            app = AppTest.from_file(str(APP), default_timeout=20).run()
            next(button for button in app.button if button.label == "Load built-in synthetic fleet").click().run()
            for _ in range(2):
                next(button for button in app.button if button.label == "Process next timestamp").click().run()
            next(button for button in app.button if button.label == "Save fleet case summaries to BigQuery").click().run()
            self.assertEqual(len(app.exception), 0)
            app.run()
            self.assertTrue(any("Saved 1 case summaries" in message.value for message in app.success))


if __name__ == "__main__":
    unittest.main()

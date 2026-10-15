import os
from pathlib import Path
import unittest
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parents[1] / "app.py"


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {"FORCE_MOCK": "1", "GCS_BUCKET": "", "BQ_DATASET": ""})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_offline_dashboard_retains_approved_case(self):
        app = AppTest.from_file(str(APP)).run()
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
        app = AppTest.from_file(str(APP)).run()
        app.toggle[0].set_value(False).run()
        self.assertEqual(os.environ["FORCE_MOCK"], "1")
        self.assertEqual(len(app.exception), 0)

    def test_fleet_results_render_without_exceptions(self):
        app = AppTest.from_file(str(APP)).run()
        app.multiselect[0].set_value(["MTR-07", "PMP-03", "SWG-02", "PRESS-01"]).run()
        app.button[0].click().run()
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(len(app.session_state["cases"]), 4)


if __name__ == "__main__":
    unittest.main()

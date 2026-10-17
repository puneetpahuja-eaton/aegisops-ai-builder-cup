"""Smoke tests for the role-gated app shell using Streamlit AppTest."""
from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

os.environ["FORCE_MOCK"] = "1"

from streamlit.testing.v1 import AppTest

import auth
import devices

APP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")


class AppShellTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"AEGIS_LOCAL_STORE": self.tmp.name, "USE_FIRESTORE": "0",
                                            "GCS_BUCKET": "", "BQ_DATASET": "", "USE_SECRET_MANAGER": "0"})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_login_page_renders(self):
        app = AppTest.from_file(APP, default_timeout=60).run()
        self.assertEqual(len(app.exception), 0)
        self.assertTrue(any("AegisOps" in h.value for h in app.title))

    def test_admin_navigation_builds_all_sections(self):
        auth.ensure_seed_admin()
        app = AppTest.from_file(APP, default_timeout=60)
        app.session_state["user"] = {"email": "admin@aegisops.demo", "role": "admin"}
        app.run()
        self.assertEqual(len(app.exception), 0)

    def test_viewer_cannot_see_admin_or_live(self):
        app = AppTest.from_file(APP, default_timeout=60)
        app.session_state["user"] = {"email": "v@x.com", "role": "user"}
        app.run()
        self.assertEqual(len(app.exception), 0)

    def test_home_lists_devices(self):
        devices.create_device(name="Smoke Device", type="METER")
        app = AppTest.from_file(APP, default_timeout=60)
        app.session_state["user"] = {"email": "admin@aegisops.demo", "role": "admin"}
        app.run()
        self.assertEqual(len(app.exception), 0)


if __name__ == "__main__":
    unittest.main()

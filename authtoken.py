"""Short-lived gcloud access-token auto-refresh for local cloud-backed runs.

run_local.ps1 seeds GOOGLE_OAUTH_ACCESS_TOKEN, which expires after ~1 hour. This
module refreshes it on demand by invoking the gcloud SDK, so Vertex AI, Storage
and BigQuery keep working without restarting the server. On Cloud Run (attached
service account via ADC) this is inert.
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time

_LOCK = threading.Lock()
_LAST_REFRESH = 0.0
_REFRESH_EVERY_S = 50 * 60  # Tokens last ~60 min; refresh comfortably before expiry.


def _refresh_enabled() -> bool:
    # Only when we were launched with a seeded gcloud token (local cloud mode).
    return bool(os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN")) and os.getenv("AEGIS_TOKEN_REFRESH", "1") != "0"


def _gcloud_cmd() -> list[str] | None:
    sdk = os.getenv("CLOUDSDK_GCLOUD_PY") or os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Google", "Cloud SDK", "google-cloud-sdk", "lib", "gcloud.py")
    python = os.getenv("CLOUDSDK_PYTHON") or sys.executable
    if os.path.exists(sdk):
        return [python, sdk, "auth", "print-access-token"]
    return None  # Fall back to whatever token is already set.


def ensure_fresh_token(force: bool = False) -> None:
    """Refresh GOOGLE_OAUTH_ACCESS_TOKEN if stale (or when force=True after a 401)."""
    global _LAST_REFRESH
    if not _refresh_enabled():
        return
    now = time.time()
    if not force and now - _LAST_REFRESH < _REFRESH_EVERY_S:
        return
    with _LOCK:
        if not force and now - _LAST_REFRESH < _REFRESH_EVERY_S:
            return
        cmd = _gcloud_cmd()
        if not cmd:
            return
        try:
            env = dict(os.environ)
            token = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env).stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return
        if token:
            os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"] = token
            _LAST_REFRESH = now

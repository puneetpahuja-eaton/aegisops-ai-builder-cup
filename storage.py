"""Cloud Storage-backed data loading with a local fallback.

If GCS_BUCKET is set, SOP/scenario files are read from the bucket; otherwise the
bundled local data/ files are used. This keeps local dev working with no GCP.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DATA = Path(__file__).parent / "data"


def backend() -> str:
    return "gcs" if os.getenv("GCS_BUCKET") else "local"


def _gcs_text(name: str) -> str:
    from google.cloud import storage

    credentials = None
    if os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN"):
        from google.oauth2.credentials import Credentials
        credentials = Credentials(os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"])
    client = storage.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"), credentials=credentials)
    bucket = client.bucket(os.environ["GCS_BUCKET"])
    prefix = os.getenv("GCS_PREFIX", "")
    return bucket.blob(f"{prefix}{name}").download_as_text(timeout=20)


def load_text(name: str) -> str:
    if name not in {"sop.md", "scenarios.json", "sample_incident.json"}:
        raise ValueError("Unsupported data file.")
    if os.getenv("GCS_BUCKET"):
        return _gcs_text(name)
    return (DATA / name).read_text(encoding="utf-8")


def load_json(name: str):
    return json.loads(load_text(name))

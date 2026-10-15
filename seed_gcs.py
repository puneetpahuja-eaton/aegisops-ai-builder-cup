"""Seed a Cloud Storage bucket with the SOP and scenario files.

    python seed_gcs.py            # uses $GCS_BUCKET / $GCS_PREFIX

Run once after creating the bucket so the deployed app can read from GCS.
"""
from __future__ import annotations

import os
from pathlib import Path

DATA = Path(__file__).parent / "data"
FILES = ["sop.md", "scenarios.json", "sample_incident.json"]


def main() -> None:
    bucket_name = os.environ["GCS_BUCKET"]
    prefix = os.getenv("GCS_PREFIX", "")
    from google.cloud import storage

    client = storage.Client()
    bucket = client.bucket(bucket_name)
    for name in FILES:
        blob = bucket.blob(f"{prefix}{name}")
        blob.upload_from_filename(str(DATA / name))
        print(f"uploaded gs://{bucket_name}/{prefix}{name}")


if __name__ == "__main__":
    main()

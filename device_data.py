"""Per-device telemetry dataset storage and synthetic generation.

A device is analyzed in one of two modes:
  * "synthetic": the built-in PRISM power simulator (full auto-remediation demo).
  * "dataset":   an uploaded or live-captured FleetDataset (observation-only).

Datasets are stored in GCS when a bucket is configured, else in the local store
(the local store has no document-size limit, unlike Firestore).
"""
from __future__ import annotations

import json
import os

import datastore
import devices
from fleet_data import FleetDataset

_TELEMETRY = "telemetry"  # subcollection: devices/<id>/telemetry/current


def _gcs_blob(device_id: str):
    from google.cloud import storage as gcs

    credentials = None
    if os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN"):
        from google.oauth2.credentials import Credentials
        credentials = Credentials(os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"])
    client = gcs.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"), credentials=credentials)
    prefix = os.getenv("GCS_PREFIX", "")
    return client.bucket(os.environ["GCS_BUCKET"]).blob(f"{prefix}telemetry/{device_id}.json")


def set_dataset(device_id: str, dataset: FleetDataset) -> None:
    payload = dataset.model_dump_json()
    if os.getenv("GCS_BUCKET"):
        _gcs_blob(device_id).upload_from_string(payload, content_type="application/json")
        datastore.set_doc(devices.telemetry_path(device_id), "current", {"location": "gcs"})
    else:
        datastore.set_doc(devices.telemetry_path(device_id), "current", {"location": "local", "json": payload})
    devices.update_device(device_id, {"telemetry_mode": "dataset", "status": "ready"})


def get_dataset(device_id: str) -> FleetDataset | None:
    record = datastore.get_doc(devices.telemetry_path(device_id), "current")
    if not record:
        return None
    if record.get("location") == "gcs":
        payload = _gcs_blob(device_id).download_as_text()
    else:
        payload = record.get("json")
    if not payload:
        return None
    return FleetDataset.model_validate(json.loads(payload))


def clear_dataset(device_id: str) -> None:
    datastore.delete_doc(devices.telemetry_path(device_id), "current")
    devices.update_device(device_id, {"telemetry_mode": "synthetic"})


def set_synthetic(device_id: str) -> None:
    clear_dataset(device_id)
    devices.update_device(device_id, {"telemetry_mode": "synthetic", "status": "ready"})


def mode(device_id: str) -> str:
    device = devices.get_device(device_id) or {}
    return device.get("telemetry_mode", "synthetic")


def build_prism_demo_dataset() -> FleetDataset:
    """Build an uploadable FleetDataset mirroring the 22-asset PRISM power fleet.

    Reuses the template logic already proven in prism_extensions so the dataset
    carries the original asset metadata and 96 replay snapshots.
    """
    from prism_cloud import Engine
    import prism_extensions as cloud

    engine = Engine(offline=True)
    return cloud.template(engine)

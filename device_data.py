"""Per-device telemetry dataset storage and synthetic generation.

A device is analyzed in one of two modes:
  * "synthetic": the built-in PRISM power simulator (full auto-remediation demo).
  * "dataset":   an uploaded or live-captured FleetDataset (observation-only).

Datasets can be large, so they are stored outside the datastore document:
  * GCS when truly cloud-persistent (USE_FIRESTORE=1 with a bucket), else
  * a file under the local store directory (no size limit).
This matches the datastore backend so the dataset is always readable by the
same process that wrote it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import datastore
import devices
from fleet_data import FleetDataset

_TELEMETRY = "telemetry"  # subcollection: devices/<id>/telemetry/current


def _use_gcs() -> bool:
    # Only use GCS for durable cloud persistence; local runs keep datasets on disk.
    return bool(os.getenv("GCS_BUCKET")) and os.getenv("USE_FIRESTORE") == "1"


def _gcs_blob(device_id: str):
    from google.cloud import storage as gcs

    credentials = None
    if os.getenv("GOOGLE_OAUTH_ACCESS_TOKEN"):
        from google.oauth2.credentials import Credentials
        credentials = Credentials(os.environ["GOOGLE_OAUTH_ACCESS_TOKEN"])
    client = gcs.Client(project=os.environ.get("GOOGLE_CLOUD_PROJECT"), credentials=credentials)
    prefix = os.getenv("GCS_PREFIX", "")
    return client.bucket(os.environ["GCS_BUCKET"]).blob(f"{prefix}telemetry/{device_id}.json")


def _local_file(device_id: str) -> Path:
    base = Path(os.getenv("AEGIS_LOCAL_STORE", Path(__file__).parent / ".localstore"))
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in device_id)
    return base / "telemetry" / f"{safe}.json"


def set_dataset(device_id: str, dataset: FleetDataset) -> None:
    payload = dataset.model_dump_json()
    if _use_gcs():
        _gcs_blob(device_id).upload_from_string(payload, content_type="application/json")
        datastore.set_doc(devices.telemetry_path(device_id), "current", {"location": "gcs"})
    else:
        path = _local_file(device_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
        datastore.set_doc(devices.telemetry_path(device_id), "current", {"location": "file"})
    devices.update_device(device_id, {"telemetry_mode": "dataset", "status": "ready"})


def get_dataset(device_id: str) -> FleetDataset | None:
    record = datastore.get_doc(devices.telemetry_path(device_id), "current")
    if not record:
        return None
    location = record.get("location")
    if location == "gcs":
        payload = _gcs_blob(device_id).download_as_text()
    elif location == "file":
        path = _local_file(device_id)
        payload = path.read_text(encoding="utf-8") if path.exists() else None
    else:
        payload = record.get("json")  # Legacy inline payload.
    if not payload:
        return None
    return FleetDataset.model_validate(json.loads(payload))


def clear_dataset(device_id: str) -> None:
    datastore.delete_doc(devices.telemetry_path(device_id), "current")
    path = _local_file(device_id)
    if path.exists():
        path.unlink()
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

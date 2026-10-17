"""Device registry (multi-device) backed by the datastore."""
from __future__ import annotations

import datetime
import re
import uuid

import datastore

_DEVICES = "devices"
PROTOCOLS = ("rest", "modbus", "dlms")
CRITICALITIES = ("low", "medium", "high", "critical")


class DeviceError(RuntimeError):
    pass


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return f"{base or 'device'}-{uuid.uuid4().hex[:6]}"


def create_device(*, name: str, type: str, model: str = "", site: str = "", ip: str = "",
                  criticality: str = "medium", protocol: str = "rest", created_by: str = "",
                  metadata: dict | None = None) -> dict:
    name = (name or "").strip()
    if not name:
        raise DeviceError("Device name is required.")
    if criticality not in CRITICALITIES:
        raise DeviceError(f"Criticality must be one of {CRITICALITIES}.")
    if protocol not in PROTOCOLS:
        raise DeviceError(f"Protocol must be one of {PROTOCOLS}.")
    device_id = _slug(name)
    record = {
        "id": device_id, "name": name, "type": (type or "").strip() or "GENERIC",
        "model": model.strip(), "site": site.strip(), "ip": ip.strip(),
        "criticality": criticality, "protocol": protocol, "status": "configuring",
        "created_by": created_by, "created_at": _now(), "metadata": metadata or {},
    }
    datastore.set_doc(_DEVICES, device_id, record)
    return record


def get_device(device_id: str) -> dict | None:
    return datastore.get_doc(_DEVICES, device_id)


def list_devices() -> list[dict]:
    return sorted(datastore.list_docs(_DEVICES), key=lambda d: d.get("created_at", ""))


def update_device(device_id: str, changes: dict) -> None:
    if not get_device(device_id):
        raise DeviceError("No such device.")
    allowed = {"name", "type", "model", "site", "ip", "criticality", "protocol", "status",
               "metadata", "telemetry_mode"}
    datastore.update_doc(_DEVICES, device_id, {k: v for k, v in changes.items() if k in allowed})


def delete_device(device_id: str) -> None:
    datastore.delete_doc(_DEVICES, device_id)


# Per-device subcollection paths ------------------------------------------- #
def sources_path(device_id: str) -> str:
    return f"{_DEVICES}/{device_id}/sources"


def chunks_path(device_id: str) -> str:
    return f"{_DEVICES}/{device_id}/chunks"


def live_path(device_id: str) -> str:
    return f"{_DEVICES}/{device_id}/live"


def telemetry_path(device_id: str) -> str:
    return f"{_DEVICES}/{device_id}/telemetry"

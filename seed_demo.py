"""Seed a populated demo device so a first-time visitor never sees an empty shell.

Creates one multi-asset, physically-consistent, LABELED dataset (ground-truth
scenarios) so Analysis immediately shows diagnosis accuracy, downtime avoided and
cost avoided working end-to-end. The data is clearly synthetic and the scenarios
are disclosed; this is a demonstration fixture, not real field data.

Idempotent and race-safe: uses a FIXED device id so concurrent Cloud Run
instances converge to a single document, and it removes any stray demo devices.
"""
from __future__ import annotations

import datetime

import datastore
import device_data
import devices
from dataset_gen import AnomalySpec, AssetSpec, DatasetSpec, MetricSpec, build_dataset
from fleet_data import FleetDataset

_DEMO_MARKER = "kairos-demo-v2"
_DEMO_ID = "demo-power-panel"
_DEMO_NAME = "Demo - Power Distribution Panel"


def _power_metrics() -> list[MetricSpec]:
    return [
        MetricSpec(name="voltage_a_v", unit="V", normal_min=228, normal_max=235),
        MetricSpec(name="voltage_b_v", unit="V", normal_min=228, normal_max=235),
        MetricSpec(name="voltage_c_v", unit="V", normal_min=228, normal_max=235),
        MetricSpec(name="current_a_a", unit="A", normal_min=180, normal_max=240),
        MetricSpec(name="current_b_a", unit="A", normal_min=180, normal_max=240),
        MetricSpec(name="current_c_a", unit="A", normal_min=180, normal_max=240),
        MetricSpec(name="power_factor", unit="", normal_min=0.92, normal_max=0.99),
        MetricSpec(name="active_power_kw", unit="kW", normal_min=120, normal_max=160),
        MetricSpec(name="active_energy_kwh", unit="kWh", normal_min=0, normal_max=100000),
        MetricSpec(name="thd_current_pct", unit="%", normal_min=2.0, normal_max=4.5),
    ]


def build_demo_dataset() -> FleetDataset:
    """A three-asset power panel with three distinct injected faults (ground truth)."""
    assets = [
        AssetSpec(id="MAIN-INCOMER", type="METER", criticality="critical", metrics=_power_metrics()),
        AssetSpec(id="FEEDER-02", type="METER", criticality="high", metrics=_power_metrics()),
        AssetSpec(id="MOTOR-07", type="MOTOR", criticality="high", metrics=_power_metrics()),
    ]
    anomalies = [
        AnomalySpec(asset_id="MAIN-INCOMER", metric="voltage_a_v", kind="sag",
                    start_fraction=0.45, severity=0.7, recovers=True,
                    description="Phase-A voltage sag at the incomer during peak load (auto-corrected)."),
        AnomalySpec(asset_id="FEEDER-02", metric="current_a_a", kind="spike",
                    start_fraction=0.6, severity=0.8, recovers=True,
                    description="Overload current spike on feeder 2 (load shed and rebalanced)."),
        AnomalySpec(asset_id="MOTOR-07", metric="current_a_a", kind="spike",
                    start_fraction=0.5, severity=0.85, recovers=False,
                    description="Sustained overload on motor 7 — auto-fix does not clear it, so it is "
                                "escalated to an engineer."),
    ]
    spec = DatasetSpec(assets=assets, sample_interval_min=5, duration_days=2,
                       history_days=1, anomalies=anomalies)
    return build_dataset(spec)


def ensure_demo(force: bool = False) -> str | None:
    """Create the demo device + labeled dataset if it does not already exist.

    Uses a fixed device id so concurrent instances converge on one document, and
    deletes any stray demo devices from earlier races. Returns the device id, or
    None if seeding is skipped or fails. Never raises, so it is safe at startup.
    """
    try:
        current = devices.get_device(_DEMO_ID)
        # Remove any demo device from an older version (different marker or stray id)
        # so a changed demo regenerates with the latest dataset.
        for d in devices.list_devices():
            marker = (d.get("metadata") or {}).get("demo")
            if marker and (marker != _DEMO_MARKER or d.get("id") != _DEMO_ID):
                try:
                    devices.delete_device(d["id"])
                except Exception:
                    pass
        up_to_date = bool(current) and (current.get("metadata") or {}).get("demo") == _DEMO_MARKER
        if not force and up_to_date:
            return _DEMO_ID
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        record = {
            "id": _DEMO_ID, "name": _DEMO_NAME, "type": "METER", "model": "RTK DCI PanelBoard",
            "site": "DEMO-PLANT", "ip": "", "criticality": "high", "protocol": "rest",
            "status": "configuring", "created_by": "seed", "created_at": now,
            "metadata": {"demo": _DEMO_MARKER,
                         "note": "Synthetic labeled demo: 3 assets, 3 disclosed ground-truth faults."},
        }
        datastore.set_doc("devices", _DEMO_ID, record)
        device_data.set_dataset(_DEMO_ID, build_demo_dataset())
        return _DEMO_ID
    except Exception:  # Seeding must never block app startup.
        return None


if __name__ == "__main__":
    print("Seeded demo device:", ensure_demo(force=False))

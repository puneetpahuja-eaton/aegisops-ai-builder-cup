"""PRISM-style synthetic 22-asset power chain and six evolving fault scenarios."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import math

import numpy as np

from fleet_data import FleetAsset, FleetDataset, Reading

POWER_SCENARIOS = [
    {"asset_id": "XFMR-1", "category": "electrical_supply", "start_tick": 12, "description": "Upstream voltage sag with correlated downstream symptoms."},
    {"asset_id": "PDU-2", "category": "overload", "start_tick": 24, "description": "Local load/current overload."},
    {"asset_id": "UPS-3", "category": "battery", "start_tick": 36, "description": "Battery reserve degradation; human-only handoff."},
    {"asset_id": "UPS-1", "category": "thermal", "start_tick": 54, "description": "Increasing module temperature."},
    {"asset_id": "PDU-1", "category": "harmonics", "start_tick": 66, "description": "Harmonic distortion at a local load."},
    {"asset_id": "BRK-4", "category": "electrical_supply", "start_tick": 78, "description": "Breaker-open indication and downstream loss of supply."},
]


def power_demo_dataset() -> FleetDataset:
    rng = np.random.default_rng(2026)
    layout = [
        ("UTIL-1", "utility", None, "medium"), ("XFMR-1", "transformer", "UTIL-1", "high"),
        ("SWGR-1", "switchgear", "XFMR-1", "high"), ("UPS-1", "UPS", "SWGR-1", "critical"),
        ("PDU-1", "PDU", "UPS-1", "high"), ("BRK-1", "breaker", "PDU-1", "medium"),
        ("RACK-1", "load", "BRK-1", "critical"), ("BRK-2", "breaker", "PDU-1", "medium"),
        ("RACK-2", "load", "BRK-2", "high"), ("UPS-2", "UPS", "SWGR-1", "critical"),
        ("PDU-2", "PDU", "UPS-2", "high"), ("BRK-3", "breaker", "PDU-2", "medium"),
        ("RACK-3", "load", "BRK-3", "high"), ("UTIL-2", "utility", None, "medium"),
        ("XFMR-2", "transformer", "UTIL-2", "high"), ("SWGR-2", "switchgear", "XFMR-2", "high"),
        ("UPS-3", "UPS", "SWGR-2", "critical"), ("PDU-3", "PDU", "UPS-3", "high"),
        ("BRK-4", "breaker", "PDU-3", "medium"), ("RACK-4", "load", "BRK-4", "critical"),
        ("BRK-5", "breaker", "PDU-3", "medium"), ("RACK-5", "load", "BRK-5", "medium"),
    ]
    assets = [FleetAsset(id=key, type=kind, parent_id=parent, criticality=criticality)
              for key, kind, parent, criticality in layout]
    by_id = {asset.id: asset for asset in assets}
    def downstream(asset_id: str, root: str) -> bool:
        current = asset_id
        while current:
            if current == root:
                return True
            current = by_id[current].parent_id
        return False
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    def sample(asset: FleetAsset, index: int) -> Reading:
        load = 65 + 8 * math.sin(index * 2 * math.pi / 288) + rng.normal(0, .6)
        metrics = {
            "voltage_v": round(400 + rng.normal(0, 1.4), 2), "current_a": round(load * .7 + rng.normal(0, .7), 2),
            "load_pct": round(load, 2), "temperature_c": round(35 + (load - 65) * .1 + rng.normal(0, .5), 2),
            "thd_pct": round(3 + rng.normal(0, .15), 2), "frequency_hz": round(50 + rng.normal(0, .01), 3),
        }
        if asset.type == "UPS":
            metrics["battery_soc_pct"] = round(99 + rng.normal(0, .2), 2)
        if asset.type == "breaker":
            metrics["breaker_status"] = 1
        return Reading(timestamp=start + timedelta(minutes=index * 5), asset_id=asset.id, metrics=metrics,
                       event_codes=["SELFTEST_PASS" if index % 20 == 0 else "OK"])
    # Three complete daily cycles; the replay follows them and cannot leak into fitting.
    history = [sample(asset, index) for index in range(864) for asset in assets]
    telemetry = []
    for tick in range(96):
        for asset in assets:
            row = sample(asset, 864 + tick)
            for scenario in POWER_SCENARIOS:
                if tick < scenario["start_tick"]:
                    continue
                category, root = scenario["category"], scenario["asset_id"]
                if category == "electrical_supply" and downstream(asset.id, root):
                    if root == "BRK-4":
                        row.metrics["voltage_v"] = 0
                        row.metrics["current_a"] = 0
                        row.metrics["load_pct"] = 0
                        if asset.id == root:
                            row.metrics["breaker_status"] = 0
                        row.event_codes = ["BREAKER_OPEN" if asset.id == root else "LOAD_LOST"]
                    else:
                        row.metrics["voltage_v"] = 340
                        row.event_codes = ["VOLT_SAG" if asset.id == root else "INPUT_UNDERVOLT"]
                elif asset.id == root:
                    if category == "overload":
                        row.metrics.update(load_pct=120, current_a=90)
                        row.event_codes.append("OVERLOAD_ALARM")
                    elif category == "battery":
                        row.metrics["battery_soc_pct"] = 55
                        row.event_codes.append("BATT_WEAK")
                    elif category == "thermal":
                        row.metrics["temperature_c"] = 65 + min(tick - scenario["start_tick"], 20)
                        row.event_codes.append("TEMP_CRIT")
                    elif category == "harmonics":
                        row.metrics["thd_pct"] = 12
                        row.event_codes.append("THD_HIGH")
            row.event_codes = [code for code in row.event_codes if code != "OK"] or ["OK"]
            telemetry.append(row)
    return FleetDataset(source="synthetic", assets=assets, history=history, telemetry=telemetry)

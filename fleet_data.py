"""Validated fleet topology, healthy history and chronological replay inputs."""
from __future__ import annotations

import csv
import io
import math
from datetime import datetime, timedelta, timezone
from typing import Literal

import numpy as np
from pydantic import Field, model_validator

from models import Asset, Contract

BENIGN_CODES = {"OK", "FAN_OK", "SELFTEST_PASS", "LOAD_HIGH"}
PROPAGATING_CODES = {"VOLT_SAG", "INPUT_UNDERVOLT", "BREAKER_OPEN", "LOAD_LOST"}
FAULT_CODES = PROPAGATING_CODES | {
    "TEMP-RISE", "FAN-SLOW", "TEMP_WARN", "TEMP_CRIT", "FAN_FAULT",
    "VIB-HI", "BRG-WEAR", "OC-TRIP", "OUTPUT_OVERCURRENT", "OVERLOAD_ALARM",
    "PRS-LOW", "LEAK", "SMOKE", "THD_HIGH", "WAVEFORM_DISTORT", "BATT_WEAK", "SELFTEST_FAIL",
}


class FleetAsset(Asset):
    name: str = Field(default="", max_length=200)
    site: str = Field(default="", max_length=120)
    rated_kw: float = Field(default=1, gt=0, le=1_000_000)
    parent_id: str | None = None
    downtime_cost_per_minute: float = Field(default=50, ge=0, le=1_000_000)
    assumed_manual_mttr_minutes: float = Field(default=60, gt=0, le=100_000)


class Reading(Contract):
    timestamp: datetime
    asset_id: str = Field(min_length=1, max_length=80)
    metrics: dict[str, float]
    event_codes: list[str] = Field(default_factory=lambda: ["OK"], max_length=30)

    @model_validator(mode="after")
    def validate_reading(self):
        if self.timestamp.utcoffset() is None:
            raise ValueError("Timestamps must include a timezone (for example +00:00).")
        self.timestamp = self.timestamp.astimezone(timezone.utc)
        if not self.metrics or len(self.metrics) > 120:
            raise ValueError("Each reading requires 1-120 numeric metrics.")
        if any(not key or len(key) > 80 for key in self.metrics):
            raise ValueError("Metric names must have 1-80 characters.")
        if any(key in {"timestamp", "asset_id"} or key.startswith("original_") for key in self.metrics):
            raise ValueError("Metric names timestamp, asset_id and the original_ prefix are reserved for audit metadata.")
        if any(not math.isfinite(value) for value in self.metrics.values()):
            raise ValueError("All readings must be finite.")
        if any(not code or len(code) > 80 for code in self.event_codes):
            raise ValueError("Event codes must have 1-80 characters.")
        return self


class FleetDataset(Contract):
    source: Literal["synthetic", "uploaded"] = "uploaded"
    assets: list[FleetAsset] = Field(min_length=1, max_length=50)
    history: list[Reading] = Field(min_length=20, max_length=20_000)
    telemetry: list[Reading] = Field(min_length=1, max_length=10_000)

    @model_validator(mode="after")
    def validate_fleet(self):
        assets = {asset.id: asset for asset in self.assets}
        if len(assets) != len(self.assets):
            raise ValueError("Asset IDs must be unique.")
        for asset in self.assets:
            visited = {asset.id}
            parent = asset.parent_id
            while parent:
                if parent not in assets:
                    raise ValueError(f"Unknown topology parent: {parent}.")
                if parent in visited:
                    raise ValueError("Topology must not contain a cycle.")
                visited.add(parent)
                parent = assets[parent].parent_id
        for phase, rows in (("history", self.history), ("telemetry", self.telemetry)):
            seen = set()
            for row in rows:
                if row.asset_id not in assets:
                    raise ValueError(f"Unknown asset in {phase}: {row.asset_id}.")
                key = (row.timestamp, row.asset_id)
                if key in seen:
                    raise ValueError(f"Duplicate timestamp/asset in {phase}: {key}.")
                seen.add(key)
        self.history.sort(key=lambda row: (row.timestamp, row.asset_id))
        self.telemetry.sort(key=lambda row: (row.timestamp, row.asset_id))
        for asset in self.assets:
            history = [row for row in self.history if row.asset_id == asset.id]
            replay = [row for row in self.telemetry if row.asset_id == asset.id]
            if len(history) < 20:
                raise ValueError(f"{asset.id} needs at least 20 known-healthy history readings.")
            if any(code not in BENIGN_CODES for row in history for code in row.event_codes):
                raise ValueError(f"{asset.id}: healthy history contains fault/unknown codes.")
            features = set(history[0].metrics)
            if any(set(row.metrics) != features for row in history + replay):
                raise ValueError(f"{asset.id}: metric columns must remain consistent across history and replay.")
        if max(row.timestamp for row in self.history) >= min(row.timestamp for row in self.telemetry):
            raise ValueError("All healthy training history must precede the replay period (no future leakage).")
        # A partial fleet tick could hide upstream evidence. Require a complete snapshot.
        snapshots: dict[datetime, set[str]] = {}
        for row in self.telemetry:
            snapshots.setdefault(row.timestamp, set()).add(row.asset_id)
        if any(ids != set(assets) for ids in snapshots.values()):
            raise ValueError("Each replay timestamp must include exactly one reading for every asset.")
        return self


def load_bundle(text: str) -> FleetDataset:
    if len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("Fleet uploads must be under 2 MB.")
    data = FleetDataset.model_validate_json(text)
    # A user-supplied 'synthetic' field cannot enable simulator mutation.
    data.source = "uploaded"
    return data


def load_csv(text: str) -> FleetDataset:
    """One wide CSV contains metadata, healthy history and replay rows."""
    if len(text.encode("utf-8")) > 2_000_000:
        raise ValueError("Fleet uploads must be under 2 MB.")
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    required = {"timestamp", "asset_id", "phase", "asset_type", "criticality", "parent_id", "event_codes"}
    columns = reader.fieldnames or []
    if len(columns) != len(set(columns)):
        raise ValueError("CSV column names must be unique.")
    if not required.issubset(columns):
        raise ValueError(f"CSV requires columns: {', '.join(sorted(required))}.")
    optional_metadata = {"name", "site", "rated_kw"}
    features = [column for column in columns if column not in required | optional_metadata]
    if not features:
        raise ValueError("CSV needs at least one numeric metric column.")
    assets, history, telemetry = {}, [], []
    for line, row in enumerate(reader, 2):
        try:
            if None in row or any(value is None for value in row.values()):
                raise ValueError("Row has a different number of values than the header.")
            asset = {"id": row["asset_id"], "type": row["asset_type"],
                     "criticality": row["criticality"], "parent_id": row["parent_id"] or None}
            asset.update({key: row[key] for key in ("name", "site") if key in row})
            if "rated_kw" in row:
                asset["rated_kw"] = float(row["rated_kw"])
            if asset["id"] in assets and asset != assets[asset["id"]]:
                raise ValueError("Asset metadata changed between rows.")
            assets[asset["id"]] = asset
            reading = {"timestamp": row["timestamp"], "asset_id": row["asset_id"],
                       "event_codes": [code.strip() for code in row["event_codes"].split("|") if code.strip()] or ["OK"],
                       "metrics": {key: float(row[key]) for key in features if row[key] != ""}}
            if row["phase"] == "history":
                history.append(reading)
            elif row["phase"] == "replay":
                telemetry.append(reading)
            else:
                raise ValueError("phase must be history or replay.")
        except (ValueError, TypeError, KeyError) as error:
            raise ValueError(f"CSV line {line}: {error}") from error
    return FleetDataset.model_validate({"assets": list(assets.values()), "history": history, "telemetry": telemetry})


def demo_dataset() -> FleetDataset:
    """Reproducible synthetic feeder -> motor/pump fleet, not a sensor connection."""
    rng = np.random.default_rng(42)
    assets = [
        FleetAsset(id="FEEDER-01", type="manufacturing feeder", criticality="high"),
        FleetAsset(id="MTR-07", type="motor / VFD", criticality="high", parent_id="FEEDER-01"),
        FleetAsset(id="PMP-03", type="coolant pump", criticality="high", parent_id="FEEDER-01"),
        FleetAsset(id="PRESS-01", type="hydraulic press", criticality="critical"),
    ]
    start = datetime(2026, 10, 1, tzinfo=timezone.utc)
    def healthy(asset: FleetAsset, index: int) -> Reading:
        return Reading(timestamp=start + timedelta(minutes=5 * index), asset_id=asset.id,
                       metrics={"voltage_v": round(400 + rng.normal(0, 1.5), 2),
                                "winding_temp_c": round(70 + rng.normal(0, 1), 2),
                                "vibration_mm_s": round(2 + rng.normal(0, 0.08), 3),
                                "current_a": round(42 + rng.normal(0, 1), 2),
                                "hydraulic_pressure_bar": round(210 + rng.normal(0, 2), 2)},
                       event_codes=["SELFTEST_PASS" if index % 15 == 0 else "OK"])
    history = [healthy(asset, index) for index in range(80) for asset in assets]
    telemetry = []
    for tick in range(12):
        for asset in assets:
            row = healthy(asset, 80 + tick)
            if tick >= 1 and asset.id in {"FEEDER-01", "MTR-07", "PMP-03"}:
                row.metrics["voltage_v"] = 330
                row.event_codes = ["VOLT_SAG" if asset.id == "FEEDER-01" else "INPUT_UNDERVOLT"]
            if tick >= 4 and asset.id == "PMP-03":
                row.metrics["vibration_mm_s"] = 9.4
                row.event_codes.append("BRG-WEAR")
            if tick >= 6 and asset.id == "PRESS-01":
                row.metrics["hydraulic_pressure_bar"] = 128
                row.event_codes = ["PRS-LOW"]
            telemetry.append(row)
    return FleetDataset(source="synthetic", assets=assets, history=history, telemetry=telemetry)


def csv_template(data: FleetDataset) -> str:
    buffer = io.StringIO()
    features = sorted({key for row in data.history + data.telemetry for key in row.metrics})
    fields = ["timestamp", "asset_id", "phase", "asset_type", "criticality", "parent_id", "name", "site", "rated_kw", "event_codes", *features]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    assets = {asset.id: asset for asset in data.assets}
    for phase, rows in (("history", data.history), ("replay", data.telemetry)):
        for row in rows:
            asset = assets[row.asset_id]
            writer.writerow({"timestamp": row.timestamp.isoformat(), "asset_id": row.asset_id, "phase": phase,
                             "asset_type": asset.type, "criticality": asset.criticality,
                             "parent_id": asset.parent_id or "", "name": asset.name, "site": asset.site,
                             "rated_kw": asset.rated_kw, "event_codes": "|".join(row.event_codes), **row.metrics})
    return buffer.getvalue()

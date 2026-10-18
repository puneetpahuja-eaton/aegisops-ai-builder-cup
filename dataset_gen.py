"""Generate an Analysis-ready dataset from a natural-language request via Gemini.

Flow:
  1. clarifying_questions(): Gemini asks what it needs before generating.
  2. generate_spec(): Gemini returns a compact JSON spec (assets, metrics with
     normal ranges, anomalies) grounded in the device's docs / a referenced file.
  3. build_dataset(): deterministic synthesis expands the spec into a full
     FleetDataset (healthy history + replay with injected anomalies) that the
     Analysis engine loads, updating its asset/metric selectors.

Generating a compact spec (not thousands of rows) avoids model output limits and
keeps the data reproducible.
"""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta, timezone
import json
import re

from pydantic import BaseModel, Field

from fleet_data import FleetAsset, FleetDataset, Reading
from gemini_client import generate_text, is_live

_ANOMALY_CODE = {"spike": "OVERLOAD_ALARM", "sag": "VOLT_SAG", "drift": "THD_HIGH", "dropout": "LOAD_LOST"}


class MetricSpec(BaseModel):
    name: str = Field(description="Short metric/column name, e.g. voltage_a_v")
    unit: str = Field(default="", description="Engineering unit, e.g. V, A, kW")
    normal_min: float = Field(description="Typical minimum healthy value")
    normal_max: float = Field(description="Typical maximum healthy value")


class AssetSpec(BaseModel):
    id: str = Field(description="Asset/device identifier")
    type: str = Field(default="METER")
    criticality: str = Field(default="medium")
    metrics: list[MetricSpec] = Field(min_length=1, max_length=30)


class AnomalySpec(BaseModel):
    asset_id: str
    metric: str
    start_fraction: float = Field(default=0.5, ge=0, le=1, description="Where in the replay it begins (0..1)")
    kind: str = Field(default="spike", description="spike | sag | drift | dropout")
    severity: float = Field(default=0.6, ge=0, le=1)
    description: str = ""


class DatasetSpec(BaseModel):
    assets: list[AssetSpec] = Field(min_length=1, max_length=10)
    sample_interval_min: int = Field(default=5, ge=1, le=1440)
    duration_days: int = Field(default=3, ge=1, le=14)
    history_days: int = Field(default=1, ge=1, le=14)
    anomalies: list[AnomalySpec] = Field(default_factory=list)
    notes: str = ""


def clarifying_questions(device_context: str, request: str, reference: str = "") -> str:
    prompt = (
        "A user wants to generate a synthetic dataset for a monitored device. Before generating, ask 3-6 "
        "concise clarifying questions that would materially change the dataset (parameters to include, "
        "units/ranges, duration and sampling, which anomalies to inject, number of assets). Ask only "
        "questions; do not generate data yet. Use the context to avoid asking what is already known.\n\n"
        f"Device context:\n{device_context[:8000]}\n\n"
        f"Referenced parameter file (optional):\n{reference[:8000]}\n\n"
        f"User request: {request}"
    )
    return generate_text(prompt, temperature=0.3)


_SCHEMA_HINT = """Return ONLY a JSON object (no prose, no markdown fences) with this shape:
{
  "assets": [
    {"id": "METER-1", "type": "METER", "criticality": "high",
     "metrics": [{"name": "voltage_a_v", "unit": "V", "normal_min": 220, "normal_max": 240}]}
  ],
  "sample_interval_min": 1,
  "duration_days": 3,
  "history_days": 1,
  "anomalies": [
    {"asset_id": "METER-1", "metric": "voltage_a_v", "start_fraction": 0.5,
     "kind": "sag", "severity": 0.7, "description": "voltage sag on phase A"}
  ],
  "notes": "assumptions here"
}
Rules: metric names are short snake_case; include unit and realistic normal_min/normal_max.
anomaly kind is one of: spike, sag, drift, dropout. 1-10 assets, <=30 metrics each, 1-4 anomalies."""


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
    return json.loads(text)


def generate_spec(device_context: str, request: str, reference: str = "", answers: str = "") -> dict:
    if not is_live():
        raise RuntimeError("Google AI is required to generate a dataset spec.")
    prompt = (
        "Design a COMPACT dataset specification (not the data itself) for a synthetic dataset of the "
        "monitored device. Choose realistic metrics with normal_min/normal_max ranges and units, grounded "
        "in the context and referenced parameter list. Include 1-4 labelled anomalies. Make reasonable "
        "assumptions for anything unspecified.\n\n"
        f"{_SCHEMA_HINT}\n\n"
        f"Device context:\n{device_context[:8000]}\n\n"
        f"Referenced parameter file (optional, authoritative for names/IDs/units):\n{reference[:12000]}\n\n"
        f"User request: {request}\n\n"
        f"User answers to clarifying questions (if any): {answers}"
    )
    text = generate_text(prompt, temperature=0.3, max_output_tokens=16384)
    try:
        raw = _extract_json(text)
    except (json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(f"Could not parse the dataset spec from the model response: {error}") from error
    return DatasetSpec.model_validate(raw).model_dump()


# --------------------------------------------------------------------------- #
# Deterministic synthesis
# --------------------------------------------------------------------------- #
def _rand01(*keys) -> float:
    digest = hashlib.md5("|".join(str(k) for k in keys).encode()).hexdigest()[:8]
    return int(digest, 16) / 0xFFFFFFFF


def _diurnal(abs_idx: int, interval_min: int, asset_id: str) -> float:
    minutes = abs_idx * interval_min
    tod = (minutes % 1440) / 1440.0
    phase = _rand01(asset_id, "phase") * 0.15
    return math.sin(2 * math.pi * (tod - 0.25 - phase))


def _healthy_value(metric: MetricSpec, asset_id: str, abs_idx: int, interval_min: int) -> float:
    span = metric.normal_max - metric.normal_min
    midpoint = (metric.normal_max + metric.normal_min) / 2.0
    swing = 0.25 * span * _diurnal(abs_idx, interval_min, asset_id + metric.name)
    noise = (span or 1.0) * 0.03 * (_rand01(asset_id, metric.name, abs_idx) * 2 - 1)
    value = midpoint + swing + noise
    return max(metric.normal_min - 0.1 * (span or 1), min(metric.normal_max + 0.1 * (span or 1), value))


def _apply_anomaly(value: float, metric: MetricSpec, anomaly: AnomalySpec, progress: float) -> float:
    span = (metric.normal_max - metric.normal_min) or abs(value) or 1.0
    strength = anomaly.severity * progress
    if anomaly.kind == "spike":
        return metric.normal_max + span * (0.5 + strength)
    if anomaly.kind == "sag":
        return metric.normal_min - span * (0.5 + strength)
    if anomaly.kind == "dropout":
        return 0.0
    # drift: gradual departure above the range
    return value + span * strength


def build_dataset(spec: DatasetSpec) -> FleetDataset:
    interval = spec.sample_interval_min
    per_day = max(1, (24 * 60) // interval)
    n_assets = len(spec.assets)
    history_n = min(max(20, spec.history_days * per_day), max(20, 20_000 // n_assets))
    replay_n = min(max(2, spec.duration_days * per_day), max(2, 10_000 // n_assets))

    assets = [FleetAsset(id=a.id, name=a.id, type=a.type.upper(), criticality=a.criticality.lower(),
                         site="SYNTHETIC", rated_kw=100.0) for a in spec.assets]
    start = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(
        minutes=(history_n + replay_n) * interval)

    anomalies_by_asset: dict[str, list[AnomalySpec]] = {}
    for anomaly in spec.anomalies:
        anomalies_by_asset.setdefault(anomaly.asset_id, []).append(anomaly)

    history: list[Reading] = []
    telemetry: list[Reading] = []
    for asset_spec in spec.assets:
        metrics = asset_spec.metrics
        for index in range(history_n):
            ts = start + timedelta(minutes=index * interval)
            history.append(Reading(
                timestamp=ts, asset_id=asset_spec.id, event_codes=["OK"],
                metrics={m.name: round(_healthy_value(m, asset_spec.id, index, interval), 4) for m in metrics}))
        for index in range(replay_n):
            abs_idx = history_n + index
            ts = start + timedelta(minutes=abs_idx * interval)
            values = {m.name: _healthy_value(m, asset_spec.id, abs_idx, interval) for m in metrics}
            codes: list[str] = []
            progress = index / max(1, replay_n - 1)
            for anomaly in anomalies_by_asset.get(asset_spec.id, []):
                if progress >= anomaly.start_fraction and anomaly.metric in values:
                    local = (progress - anomaly.start_fraction) / max(1e-6, 1 - anomaly.start_fraction)
                    metric = next(m for m in metrics if m.name == anomaly.metric)
                    values[anomaly.metric] = _apply_anomaly(values[anomaly.metric], metric, anomaly, local)
                    codes.append(_ANOMALY_CODE.get(anomaly.kind, "ALARM"))
            telemetry.append(Reading(
                timestamp=ts, asset_id=asset_spec.id, event_codes=codes or ["OK"],
                metrics={name: round(value, 4) for name, value in values.items()}))
    return FleetDataset(source="uploaded", assets=assets, history=history, telemetry=telemetry)

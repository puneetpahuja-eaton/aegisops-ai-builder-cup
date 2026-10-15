"""Deterministic evidence layer: robust z-scores over telemetry.

This is the trustworthy, non-hallucinating detection layer. Gemini reasons over
the evidence it produces but never invents the numbers.
"""
from __future__ import annotations

import numpy as np
from models import Incident


def robust_z(series: list[float], value: float) -> float:
    """Median/MAD z-score — resistant to outliers in the baseline window."""
    arr = np.asarray(series, dtype=float)
    if len(arr) < 5 or not np.all(np.isfinite(arr)) or not np.isfinite(value):
        raise ValueError("At least five finite baseline readings and a finite latest value are required.")
    median = np.median(arr)
    mad = np.median(np.abs(arr - median))
    if mad == 0:
        mad = max(abs(float(median)) * 0.01, 0.01)
    return float((value - median) / (1.4826 * mad))


def build_evidence(incident: dict) -> dict:
    """Score the latest reading of each metric against its baseline window."""
    incident = Incident.model_validate(incident).model_dump()
    asset = incident["asset"]
    signals = []
    for metric, obj in incident["metrics"].items():
        baseline = obj["baseline"]
        latest = obj["latest"]
        z = robust_z(baseline, latest)
        signals.append(
            {
                "metric": metric,
                "latest": latest,
                "unit": obj.get("unit", ""),
                "robust_z": round(z, 2),
                "anomalous": abs(z) >= 3.0,
                "baseline_scale": "MAD" if float(np.median(np.abs(np.asarray(baseline) - np.median(baseline)))) else "1% median floor",
            }
        )
    anomalous = [s for s in signals if s["anomalous"]]
    return {
        "asset_id": asset["id"],
        "asset_type": asset["type"],
        "asset_criticality": asset.get("criticality", "unknown"),
        "event_codes": incident.get("event_codes", []),
        "signals": signals,
        "anomalous_metrics": [s["metric"] for s in anomalous],
        "has_anomaly": bool(anomalous),
    }

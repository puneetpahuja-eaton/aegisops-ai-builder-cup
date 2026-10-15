"""Illustrative opportunity, explicitly separate from realized savings."""
BASE_DOWNTIME_MIN = {"critical": 120, "high": 60, "medium": 30, "low": 15}
COST_PER_MINUTE_USD = 50


def estimate_value(evidence: dict, decision: dict, verification: dict) -> dict:
    base = BASE_DOWNTIME_MIN.get(evidence["asset_criticality"], 0)
    potential_minutes = round(base * 0.5) if verification.get("held") else 0
    return {
        "minutes_avoided": 0,
        "cost_avoided_usd": 0,
        "potential_minutes": potential_minutes,
        "potential_usd": potential_minutes * COST_PER_MINUTE_USD,
        "assumptions": f"Illustration only: ${COST_PER_MINUTE_USD}/min, {base} min baseline, 50% reduction if a real intervention succeeds.",
        "basis": "Synthetic scenario; no measured downtime reduction or realized savings.",
    }

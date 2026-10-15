"""Evaluate explicit post-action synthetic readings, never fabricate recovery."""
from __future__ import annotations

import copy

from evidence import build_evidence


def verify(incident: dict, evidence: dict, decision: dict, *, approved: bool = False) -> dict:
    if decision["action"] != "propose_simulation":
        return {"status": "awaiting_human", "held": None, "simulated": True}
    if not approved:
        return {"status": "pending_approval", "held": None, "simulated": True}
    readings = incident.get("post_action_metrics")
    if not readings or set(readings) != set(incident["metrics"]):
        return {"status": "unverified", "held": None, "simulated": True}
    post = copy.deepcopy(incident)
    for metric, reading in readings.items():
        post["metrics"][metric]["latest"] = reading
    post["event_codes"] = []
    post_evidence = build_evidence(post)
    held = not post_evidence["has_anomaly"]
    return {
        "status": "simulated_recovery" if held else "reopened",
        "held": held,
        "post_evidence": post_evidence,
        "simulated": True,
        "basis": "Predefined synthetic post-action readings, not production measurements.",
    }

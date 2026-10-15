"""Decider — deterministic autonomy gate.

Re-validates the Gemini diagnosis against hard safety rules before any action.
Keeping this deterministic is the guardrail: the LLM proposes, the gate disposes.
"""
from __future__ import annotations

CONFIDENCE_THRESHOLD = 0.6
# Event-code prefixes that always require a physical/human repair.
PHYSICAL_REPAIR_PREFIXES = ("BRG", "PRS-LOW", "LEAK", "SMOKE")


def decide(evidence: dict, diagnosis: dict) -> dict:
    reasons: list[str] = []
    auto = True

    if diagnosis.get("insufficient_evidence"):
        auto = False
        reasons.append("diagnosis reports insufficient evidence")
    if diagnosis.get("escalate"):
        auto = False
        reasons.append("diagnosis escalated per SOP autonomy rule")
    if evidence.get("asset_criticality") == "critical":
        auto = False
        reasons.append("asset criticality is 'critical'")
    if evidence.get("asset_criticality") == "unknown":
        auto = False
        reasons.append("asset criticality is unknown")
    if not diagnosis.get("cited_sop_ids") or not diagnosis.get("_citation_check"):
        auto = False
        reasons.append("verified SOP citations are required")
    if any(s["metric"] == "vibration_mm_s" and abs(s["robust_z"]) >= 6 for s in evidence.get("signals", [])):
        auto = False
        reasons.append("severe vibration requires engineer review")

    confidence = float(diagnosis.get("confidence", 0.0))
    if confidence < CONFIDENCE_THRESHOLD:
        auto = False
        reasons.append(f"confidence {confidence:.2f} below {CONFIDENCE_THRESHOLD} threshold")

    physical = [
        c for c in evidence.get("event_codes", [])
        if any(c.upper().startswith(p) for p in PHYSICAL_REPAIR_PREFIXES)
    ]
    if physical:
        auto = False
        reasons.append(f"physical-repair code(s) present: {physical}")

    return {
        "action": "propose_simulation" if auto else "escalate",
        "autonomous": False,
        "requires_approval": auto,
        "reasons": reasons or ["sandbox review conditions met; named human approval still required"],
        "confidence": confidence,
    }

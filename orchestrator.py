"""Five-stage workflow with explicit failures, approval, and provenance."""
from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable

from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import GoogleAuthError
from pydantic import ValidationError
import httpx

from actuator import act
from decider import decide
from diagnostician import diagnose
from evidence import build_evidence
from gemini_client import ModelUnavailable
from models import Incident
import storage
from value import estimate_value
from verifier import verify

logger = logging.getLogger(__name__)
MODEL_FAILURES = (ModelUnavailable, ValidationError, ValueError, GoogleAuthError, GoogleAPICallError, httpx.HTTPError)


def load_sop() -> str:
    return storage.load_text("sop.md")


def load_scenarios() -> list[dict]:
    data = storage.load_json("scenarios.json")
    if not isinstance(data, list) or not data:
        raise ValueError("Scenario data must be a nonempty list.")
    return [Incident.model_validate(incident).model_dump() for incident in data]


def run_case(
    incident: dict, sop_text: str, *, offline: bool = False,
    context: dict | None = None,
    on_event: Callable[[str, str, dict], None] | None = None,
) -> dict:
    started = time.monotonic()
    incident = Incident.model_validate(incident).model_dump()
    evidence = build_evidence(incident)
    if context is not None:
        evidence["fleet_context"] = context
    def emit(agent: str, tool: str, detail: dict) -> None:
        if on_event:
            on_event(agent, tool, detail)
    emit("Monitor", "build_evidence", evidence)
    errors = []
    emit("Diagnostician", "grounded_diagnosis_started", {"asset_id": evidence["asset_id"], "offline": offline})
    try:
        diagnosis = diagnose(evidence, sop_text, offline=offline)
    except MODEL_FAILURES as error:
        logger.error("Diagnosis failed for %s: %s", evidence["asset_id"], type(error).__name__)
        errors.append(f"Diagnosis unavailable: {type(error).__name__}: {error}")
        diagnosis = {
            "root_cause": "Diagnosis unavailable - engineer review required",
            "asset_id": evidence["asset_id"],
            "confidence": 0.0,
            "cited_sop_ids": [],
            "citation_quotes": {},
            "reasoning": "No Google AI diagnosis accepted. No offline result substituted.",
            "recommended_action": "Request qualified engineer review.",
            "escalate": True,
            "insufficient_evidence": True,
            "_source": "unavailable",
        }
    emit("Diagnostician", "grounded_diagnosis_completed", diagnosis)
    decision = decide(evidence, diagnosis)
    if context and context.get("unknown_codes"):
        decision.update(action="escalate", requires_approval=False)
        decision["reasons"].append("Unrecognized event codes require engineer review.")
    if context and context.get("protected_symptom_assets"):
        decision.update(action="escalate", requires_approval=False)
        decision["reasons"].append("Correlated symptoms affect critical or unknown-criticality assets.")
    if context and context.get("playbook"):
        playbook = context["playbook"]
        decision["reversibility"] = playbook["reversibility"]
        decision["sandbox_action"] = playbook["action"]
        if playbook["reversibility"] == "NONE" or diagnosis["confidence"] < playbook["min_confidence"]:
            decision.update(action="escalate", requires_approval=False)
            decision["reasons"].append("Playbook reversibility/confidence policy requires engineer review.")
    emit("Decider", "safety_gate", decision)
    emit("Actuator", "prepare_review_output", {"action": decision["action"]})
    try:
        action = act(evidence, diagnosis, decision, sop_text, offline=offline)
    except MODEL_FAILURES as error:
        logger.error("Work order failed for %s: %s", evidence["asset_id"], type(error).__name__)
        errors.append(f"Work order unavailable: {type(error).__name__}: {error}")
        action = {"type": "unavailable", "status": "failed", "summary": "Work order generation failed. Manual review required."}
    verification = verify(incident, evidence, decision)
    emit("Actuator", "review_output_ready", action)
    return {
        "case_id": str(uuid.uuid4()),
        "mode": "offline simulation" if offline else "Google AI / synthetic telemetry",
        "incident": incident,
        "evidence": evidence,
        "diagnosis": diagnosis,
        "decision": decision,
        "action": action,
        "verification": verification,
        "value": estimate_value(evidence, decision, verification),
        "errors": errors,
        "elapsed_seconds": round(time.monotonic() - started, 2),
        "approval": {"approved": False, "reviewer": None},
    }


def approve_simulation(case: dict, reviewer: str) -> dict:
    if case["decision"]["action"] != "propose_simulation" or case["errors"]:
        raise ValueError("This case is not eligible for a sandbox simulation.")
    if not reviewer.strip():
        raise ValueError("A reviewer name is required.")
    case["approval"] = {"approved": True, "reviewer": reviewer.strip()}
    case["action"]["status"] = "simulated"
    case["action"]["summary"] = "Human-approved sandbox scenario; no equipment commands sent."
    case["verification"] = verify(case["incident"], case["evidence"], case["decision"], approved=True)
    case["value"] = estimate_value(case["evidence"], case["decision"], case["verification"])
    return case


def run_all(*, offline: bool = False) -> list[dict]:
    sop = load_sop()
    return [run_case(incident, sop, offline=offline) for incident in load_scenarios()]

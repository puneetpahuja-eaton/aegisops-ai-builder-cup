"""Draft review-only work orders; never dispatch or control real equipment."""
from __future__ import annotations

import json

from diagnostician import sop_sections
from gemini_client import generate_json
from models import WorkOrder


def act(evidence: dict, diagnosis: dict, decision: dict, sop_text: str, *, offline: bool = False, approved: bool = False) -> dict:
    if decision["action"] == "propose_simulation":
        return {
            "type": "simulation",
            "status": "simulated" if approved else "pending_approval",
            "summary": "Approved sandbox scenario only; no command sent to any equipment." if approved else "Supervisor approval required; no action taken.",
            "cited_sop_ids": diagnosis["cited_sop_ids"],
        }
    sections = sop_sections(sop_text)
    cited = {key: sections[key] for key in diagnosis["cited_sop_ids"]}
    if offline or diagnosis.get("_source") == "unavailable":
        work_order = {
            "title": f"Review incident for {evidence['asset_id']}",
            "asset_id": evidence["asset_id"],
            "priority": "P1" if evidence["asset_criticality"] == "critical" else "P2",
            "summary": diagnosis["root_cause"],
            "steps": ["Review the incident evidence and applicable approved procedures with a qualified engineer."],
            "safety_notes": ["No equipment control or maintenance instructions are issued by this prototype."],
            "cited_sop_ids": diagnosis["cited_sop_ids"],
            "_source": "template (review-only)",
        }
    else:
        prompt = f"""Draft a REVIEW-ONLY work order using this evidence, diagnosis and SOP.
Do not claim a repair happened or a ticket was dispatched. Do not issue equipment
control or maintenance instructions. Include qualified human review in safety_notes.
Preserve the exact asset_id and only the supplied cited SOP IDs.
DATA:
{json.dumps({'evidence': evidence, 'diagnosis': diagnosis, 'sop': cited})}
"""
        work_order = generate_json(prompt, WorkOrder)
        if work_order["asset_id"] != evidence["asset_id"] or set(work_order["cited_sop_ids"]) != set(cited):
            raise ValueError("Work order asset/citations do not match the validated diagnosis.")
    return {"type": "work_order", "status": "draft_for_review", "work_order": work_order}

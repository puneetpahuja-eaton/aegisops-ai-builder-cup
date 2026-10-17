"""
Agent 4 - Actuator.

Carries out the Decider's verdict via tools:

  * AUTO_REMEDIATE -> execute_remediation. In this offline demo, "executing"
    means signalling the simulator that the fault is being corrected, so the
    asset recovers on the next 5-minute sample (the Verifier confirms).
  * ESCALATE       -> raise_work_order for a human. Nothing on the equipment is
    changed; PRISM has already done the detection and diagnosis.

In production the execute step would call real control APIs (setpoint changes,
transfer switches, harmonic filters, breaker reclose, etc.).
"""

from __future__ import annotations

from typing import Optional

from ..agent_runtime import Agent, Blackboard, Tool
from ..case import Case


class ActuatorAgent(Agent):
    name = "Actuator"
    role = "Execute the remediation or raise a work order"

    def __init__(self):
        super().__init__([
            Tool("execute_remediation", "Apply a reversible control action to an asset",
                 lambda asset_id, action: {"ok": True, "asset": asset_id, "action": action}),
            Tool("raise_work_order", "Open a work order for an on-call engineer",
                 lambda case_id, asset_id: {"ok": True, "wo": f"WO-{case_id}", "asset": asset_id}),
        ])

    def act(self, case: Case, step: int, fault: Optional[object], bb: Blackboard) -> str:
        if case.decision == "AUTO_REMEDIATE":
            self.call(bb, "execute_remediation", f"{case.root_asset_id}: {case.action}",
                      asset_id=case.root_asset_id, action=case.action)
            case.status = "ACTING"
            case.act_step = step
            # The remediation takes effect from the next sample.
            if fault is not None:
                fault.resolved_sample = step + 1
            return (
                f"Executed remediation on {case.root_asset_id}: \"{case.action}\". "
                f"Awaiting verification next sample."
            )

        # ESCALATE
        self.call(bb, "raise_work_order", f"{case.case_id} for {case.root_asset_id}",
                  case_id=case.case_id, asset_id=case.root_asset_id)
        case.status = "ESCALATED"
        case.act_step = step
        return (
            f"Raised work order WO-{case.case_id} for {case.root_asset_id}: "
            f"\"{case.action}\". Full diagnosis and evidence attached for the on-call engineer."
        )

"""
Agent 3 - Decider (confidence-gated autonomy).

Responsibility: given a diagnosed case, decide whether PRISM is allowed to fix it
ON ITS OWN, or must hand it to a human. This is the safety brain of the system.

The gate considers three things, not just confidence:
  * diagnostic confidence   (is the diagnosis trustworthy?)
  * action reversibility     (HIGH = software/setpoint; NONE = physical part)
  * asset criticality        (how much is at stake if we are wrong?)

This is what separates a responsible autonomous system from a reckless one.
"""

from __future__ import annotations

from .. import config
from ..agent_runtime import Agent, Blackboard, Tool
from ..case import Case
from ..topology import Topology


class DeciderAgent(Agent):
    name = "Decider"
    role = "Confidence-gated autonomy: decide whether to act alone or escalate"

    def __init__(self, topo: Topology):
        self.topo = topo
        super().__init__([
            Tool("lookup_playbook", "Fetch the remediation action and reversibility for a fault",
                 lambda fault_type: config.PLAYBOOK.get(fault_type, {})),
        ])

    def decide(self, case: Case, bb: Blackboard) -> None:
        play = self.call(bb, "lookup_playbook", case.fault_type, fault_type=case.fault_type)
        case.action = play.get("action", "Manual investigation required")
        case.reversibility = play.get("reversibility", "NONE")

        conf = case.confidence
        crit = self.topo.get(case.root_asset_id).criticality
        thr = config.AUTO_CONFIDENCE_THRESHOLD

        # 1. Physical / irreversible remediation always needs a human.
        if case.reversibility == "NONE":
            case.decision = "ESCALATE"
            extra = "" if conf >= thr else f" Confidence {conf:.2f} is also below the {thr:.2f} autonomy threshold."
            case.decision_reason = (
                f"Remediation requires a non-reversible physical intervention; "
                f"routing to a human with a pre-diagnosed work order.{extra}"
            )
            return

        # 2. Low confidence -> escalate regardless of how easy the fix is.
        if conf < thr:
            case.decision = "ESCALATE"
            case.decision_reason = (
                f"Diagnostic confidence {conf:.2f} is below the {thr:.2f} autonomy "
                f"threshold; escalating for human confirmation."
            )
            return

        # 3. Fully reversible + confident -> act autonomously.
        if case.reversibility == "HIGH":
            case.decision = "AUTO_REMEDIATE"
            case.decision_reason = (
                f"Confidence {conf:.2f} >= {thr:.2f} and remediation is fully "
                f"reversible (HIGH); proceeding autonomously."
            )
            return

        # 4. Medium-reversibility actions need a higher bar AND a non-critical asset.
        if case.reversibility == "MED":
            if conf >= config.MED_REVERSIBILITY_THRESHOLD and crit != "CRITICAL":
                case.decision = "AUTO_REMEDIATE"
                case.decision_reason = (
                    f"Confidence {conf:.2f} >= {config.MED_REVERSIBILITY_THRESHOLD:.2f} "
                    f"and asset criticality is {crit}; medium-reversibility action approved."
                )
            else:
                case.decision = "ESCALATE"
                case.decision_reason = (
                    f"Medium-reversibility action on a {crit} asset with confidence "
                    f"{conf:.2f}; human sign-off required before execution."
                )
            return

        # Fallback - be conservative.
        case.decision = "ESCALATE"
        case.decision_reason = "No autonomous path matched; escalating to a human."

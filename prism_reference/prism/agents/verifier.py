"""
Agent 5 - Verifier (the closed-loop check).

After the Actuator acts, the Verifier confirms the fault is actually gone - this
is what makes PRISM a true CLOSED LOOP rather than a fire-and-forget script.

For each ACTING case it re-reads the root asset (via the recheck_asset tool,
which reuses the trained metric model plus the live event codes):
  * healthy again           -> close the case as RESOLVED and book the value.
  * still faulting after a
    grace period              -> mark FAILED and escalate to a human.
"""

from __future__ import annotations

from .. import config
from ..agent_runtime import Agent, Blackboard, Tool
from ..case import Case
from ..topology import Topology

GRACE_SAMPLES = 3   # samples to wait for recovery before declaring the fix failed
_BENIGN = {config.CODE_OK, "SELFTEST_PASS", "FAN_OK", "LOAD_HIGH"}


class VerifierAgent(Agent):
    name = "Verifier"
    role = "Confirm the remediation worked; close or escalate the case"

    def __init__(self, topo: Topology, metric_model):
        self.topo = topo
        self.metric_model = metric_model
        super().__init__([
            Tool("recheck_asset", "Re-score an asset with the trained model + codes",
                 self._recheck),
        ])

    def verify(self, case: Case, step: int, bb: Blackboard) -> str | None:
        if case.status != "ACTING":
            return None

        s = bb.sample.get(case.root_asset_id, {})
        res = self.call(bb, "recheck_asset", case.root_asset_id,
                        aid=case.root_asset_id, metrics=s.get("metrics", {}),
                        primary_code=s.get("primary_code", config.CODE_OK))
        if res["healthy"]:
            case.status = "RESOLVED"
            case.resolved_step = step
            return (
                f"Re-checked {case.root_asset_id} at sample {step}: model score "
                f"{res['score']:.2f}, code {res['code']}. Healthy again - "
                f"case CLOSED (self-healed)."
            )

        if case.act_step is not None and step - case.act_step >= GRACE_SAMPLES:
            case.status = "FAILED"
            case.resolved_step = step
            return (
                f"{case.root_asset_id} has not recovered after {GRACE_SAMPLES} samples. "
                f"Auto-remediation FAILED - escalating to a human immediately."
            )
        return None

    def _recheck(self, aid: str, metrics: dict, primary_code: str) -> dict:
        if metrics.get("breaker_status") == 0:
            return {"healthy": False, "score": 1.0, "code": "BREAKER_OPEN"}
        res = self.metric_model.score(aid, metrics)
        healthy = (not res["is_anomaly"]) and (primary_code in _BENIGN)
        return {"healthy": healthy, "score": res["score"], "code": primary_code}

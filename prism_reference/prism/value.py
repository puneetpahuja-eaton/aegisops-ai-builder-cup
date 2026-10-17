"""
Counterfactual value estimator.

For every case PRISM closes, we estimate the downtime (and therefore money) it
avoided versus the "no PRISM" world where a human would have taken the typical
mean-time-to-resolve (MTTR) to notice, diagnose and fix the same fault.

  downtime_avoided = manual_MTTR - PRISM_time_to_resolve
  cost_avoided     = downtime_avoided * cost_per_minute(asset criticality) * severity

Escalated cases still create value: PRISM hands the human a fully diagnosed case,
so we credit a fraction (EARLY_DETECTION_CREDIT) of the manual MTTR.
"""

from __future__ import annotations

from . import config
from .case import Case
from .topology import Topology


def estimate(case: Case, topo: Topology) -> None:
    """Populate case.downtime_avoided_min and case.cost_avoided_usd in place."""
    asset = topo.get(case.root_asset_id)
    cost_per_min = config.COST_PER_MIN.get(asset.criticality, 100.0)
    manual_mttr = config.MANUAL_MTTR_MIN.get(case.fault_type, 30)

    # severity = strongest observation severity, floored so value is never zero
    severity = max([o.severity for o in case.observations], default=0.5)
    severity = max(0.5, min(1.0, severity))

    if case.status == "RESOLVED" and case.act_step is not None and case.resolved_step is not None:
        prism_ttr = max(1, case.resolved_step - case.opened_step) * config.SAMPLE_INTERVAL_MIN
        avoided = max(0.0, manual_mttr - prism_ttr)
    else:
        # escalated / pending human - credit early-detection value only
        avoided = manual_mttr * config.EARLY_DETECTION_CREDIT

    case.downtime_avoided_min = round(avoided, 1)
    case.cost_avoided_usd = round(avoided * cost_per_min * severity, 0)

"""
Agent 1 - Monitor (now model-driven).

Perceives the latest 5-minute sample for every asset and uses two TRAINED tools
to decide what is abnormal:

  * score_metric_model  - Isolation Forest + robust-z score on the telemetry.
  * scan_code_patterns  - Markov transition-surprise over the event-code stream.

Anything either tool flags becomes an Observation on the blackboard, enriched
with the model evidence (score, z, codes, surprise). The Monitor still makes no
judgement about cause - that is the Diagnostician's job.
"""

from __future__ import annotations

from collections import deque

from .. import config
from ..agent_runtime import Agent, Blackboard, Tool
from ..case import Observation


class MonitorAgent(Agent):
    name = "Monitor"
    role = "Detect anomalies from telemetry and event codes using trained models"

    def __init__(self, topo, metric_model, code_model):
        self.topo = topo
        self.metric_model = metric_model
        self.code_model = code_model
        super().__init__([
            Tool("score_metric_model",
                 "Isolation Forest + robust-z anomaly score for one asset",
                 metric_model.score),
            Tool("scan_code_patterns",
                 "Markov transition-surprise over an asset's event-code stream",
                 code_model.scan),
        ])

    def run(self, bb: Blackboard) -> None:
        for aid, s in bb.sample.items():
            mem = bb.code_memory.setdefault(aid, deque(maxlen=config.CODE_MEMORY))
            mem.append(s["primary_code"])

            mres = self.call(bb, "score_metric_model", aid, aid=aid, metrics=s["metrics"])
            cres = self.call(bb, "scan_code_patterns", aid, recent_codes=list(mem))

            # record every asset's scores so the dashboard can chart them live
            bb.tick_scores[aid] = {
                "score": mres["score"], "zmax": mres["zmax"],
                "surprise": cres["surprise"], "iforest": mres["iforest"],
            }

            if not (mres["is_anomaly"] or cres["is_anomaly"]):
                bb.flagged_assets.discard(aid)          # recovered -> allow re-flag later
                continue

            if mres["is_anomaly"] and cres["is_anomaly"]:
                source = "both"
            elif mres["is_anomaly"]:
                source = "metric"
            else:
                source = "code"

            metric = mres["top_metric"] or (cres["flagged"][0] if cres["flagged"] else "codes")
            raw = s["metrics"].get(metric, 0.0)
            value = float(raw) if isinstance(raw, (int, float)) else 0.0
            z = mres["per_metric_z"].get(mres["top_metric"], 0.0)
            code_sev = min(1.0, cres["surprise"] / (2 * config.CODE_SURPRISE_THRESHOLD))

            ob = Observation(
                asset_id=aid, metric=metric, value=value,
                severity=round(max(mres["score"], code_sev), 3),
                direction="high" if z >= 0 else "low",
                model_score=mres["score"], zmax=mres["zmax"],
                codes=[c for c in s["codes"] if c != config.CODE_OK],
                code_surprise=cres["surprise"], source=source,
            )
            bb.observations.append(ob)

            if aid not in bb.flagged_assets:
                bb.flagged_assets.add(aid)
                shown = "/".join(ob.codes) or "none"
                bb.log(self.name, "-",
                       f"Flagged {aid}: model score {mres['score']:.2f} "
                       f"(z={mres['zmax']:.1f} on {mres['top_metric']}), "
                       f"code surprise {cres['surprise']:.1f} [{shown}].",
                       "warn")

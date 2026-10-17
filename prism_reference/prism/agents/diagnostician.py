"""
Agent 2 - Diagnostician (the causal root-cause engine).

Turns the Monitor's anomalies into a small number of CASES, each naming a single
ROOT CAUSE. This is where PRISM's core cleverness lives:

  1. classify_fault - infer the fault type, preferring the EVENT CODES (which map
     directly to a fault) and falling back to the abnormal metric.
  2. walk_topology  - use the power topology (causal graph) to ELIMINATE
     downstream symptoms: a low-voltage reading is only a symptom if an upstream
     asset is also faulting. The most-upstream faulting asset is the true root.
  3. score confidence from signature clarity x topological consistency, with a
     bonus when the event codes and the ML score agree.

It deliberately does NOT decide what to do - that is the Decider's job.
"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List, Optional

from .. import config
from ..agent_runtime import Agent, Blackboard, Tool
from ..case import Observation
from ..topology import Topology

# Faults whose effect travels downstream through the power chain.
PROPAGATING = {"VOLTAGE_SAG", "BREAKER_TRIP"}


class ProtoCase:
    """A diagnosis result, before the engine turns it into a tracked Case."""

    def __init__(self, root_asset_id, fault_type, confidence, symptom_ids, observations):
        self.root_asset_id = root_asset_id
        self.fault_type = fault_type
        self.confidence = confidence
        self.symptom_asset_ids = symptom_ids
        self.observations = observations


class DiagnosticianAgent(Agent):
    name = "Diagnostician"
    role = "Isolate the single root cause behind a burst of anomalies"

    def __init__(self, topo: Topology):
        self.topo = topo
        super().__init__([
            Tool("classify_fault", "Infer fault type from event codes / abnormal metric",
                 self._classify),
            Tool("walk_topology", "List an asset's upstream ancestors in the power chain",
                 self.topo.ancestors),
        ])

    def run(self, bb: Blackboard) -> None:
        by_asset: Dict[str, Observation] = {o.asset_id: o for o in bb.observations}
        if not by_asset:
            return

        classified: Dict[str, str] = {}
        for aid, ob in by_asset.items():
            ft = self.call(bb, "classify_fault", aid, obs=ob)
            if ft:
                classified[aid] = ft

        anomalous = set(classified)
        propagating_assets = {a for a, ft in classified.items() if ft in PROPAGATING}

        roots: List[str] = []
        for aid, ft in classified.items():
            if ft in PROPAGATING:
                # A propagating-type anomaly (low voltage / lost power) is only a
                # SYMPTOM if an upstream asset is itself faulting in a propagating way.
                ancestors = self.call(bb, "walk_topology", aid, asset_id=aid)
                if any(anc in propagating_assets for anc in ancestors):
                    continue        # explained by an upstream fault -> symptom
            roots.append(aid)

        for root in roots:
            ft = classified[root]
            symptoms = ([d for d in self.topo.descendants(root) if d in anomalous]
                        if ft in PROPAGATING else [])
            conf = self._confidence(root, ft, anomalous, by_asset)
            bb.proto_cases.append(ProtoCase(root, ft, conf, symptoms, [by_asset[root]]))

    # -- tools -------------------------------------------------------------- #
    def _classify(self, obs: Observation) -> Optional[str]:
        # Prefer the operational codes - they map directly to a fault type.
        votes = [config.CODE_TO_FAULT[c] for c in obs.codes if c in config.CODE_TO_FAULT]
        if votes:
            return Counter(votes).most_common(1)[0][0]
        # Fall back to the abnormal metric.
        m, d = obs.metric, obs.direction
        if m == "load_pct" and d == "high":
            return "OVERLOAD"
        if m == "temperature_c":
            return "THERMAL_RUNAWAY"
        if m == "thd_pct":
            return "HARMONIC_DISTORTION"
        if m == "battery_soc_pct":
            return "BATTERY_DEGRADATION"
        if m == "voltage_v":
            return "VOLTAGE_SAG"
        return None

    def _confidence(self, root, fault_type, anomalous, by_asset) -> float:
        base = config.BASE_CLARITY.get(fault_type, 0.8)
        if fault_type in PROPAGATING:
            descendants = self.topo.descendants(root)
            topo = (sum(1 for d in descendants if d in anomalous) / len(descendants)
                    if descendants else 1.0)
        else:
            topo = 1.0

        ob = by_asset[root]
        signature = set(config.FAULT_CODE_SIGNATURE.get(fault_type, []))
        code_bonus = 0.03 if signature & set(ob.codes) else 0.0
        model_bonus = 0.02 if ob.model_score > 0.7 else 0.0
        return round(min(0.98, base * topo + code_bonus + model_bonus), 3)


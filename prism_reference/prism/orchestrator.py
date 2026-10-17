"""
Engine - the v2 closed-loop, streaming, agentic conductor.

Startup:
  1. TRAIN the anomaly models on healthy historical time-series (Isolation Forest
     on the telemetry + a Markov model on the event-code stream).

Every 5-minute sample (tick):
  2. Generate the next live sample for the whole fleet (with injected faults).
  3. Run the agent runtime over a shared Blackboard:
        Verifier (close in-flight) -> Monitor -> Diagnostician -> Decider -> Actuator
  4. Track cases, the reasoning trace, tool calls, telemetry/score history and the
     cumulative business-value scoreboard.

A parallel "no-PRISM" baseline (faults never resolved) is generated on demand so
the dashboard can show the counterfactual value.
"""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List, Optional

from . import config, signals, value
from .agent_runtime import Blackboard
from .agents.actuator import ActuatorAgent
from .agents.decider import DeciderAgent
from .agents.diagnostician import DiagnosticianAgent, ProtoCase
from .agents.monitor import MonitorAgent
from .agents.verifier import VerifierAgent
from .case import Case, LogEntry
from .models import CodePatternModel, MetricAnomalyModel
from .signals import FaultSpec, SignalSource
from .topology import Topology


class Engine:
    def __init__(self):
        self.topo = Topology.load()
        self.signal = SignalSource(self.topo)
        self._scenarios = self._load_scenarios()

        # Train the models ONCE on healthy history.
        self.metric_model = MetricAnomalyModel()
        self.code_model = CodePatternModel()
        self.train_report: dict = {}
        self.train()

        self.reset()

    # -- scenarios ---------------------------------------------------------- #
    def _load_scenarios(self) -> List[dict]:
        with open(config.LIVE_SCENARIOS_FILE, encoding="utf-8") as fh:
            return json.load(fh)["scenarios"]

    def _fresh_faults(self) -> List[FaultSpec]:
        return [
            FaultSpec(
                scenario_id=s["scenario_id"], asset_id=s["asset_id"],
                fault_type=s["fault_type"], start_sample=s["start_sample"],
                description=s["description"],
                ground_truth_root_cause=s.get("ground_truth_root_cause", s["asset_id"]),
            )
            for s in self._scenarios
        ]

    # -- training ----------------------------------------------------------- #
    def build_history(self):
        """Generate the healthy training history (also used to export CSVs)."""
        metric_rows: Dict[str, list] = {aid: [] for aid in self.topo.all_ids()}
        features: Dict[str, list] = {}
        code_seq: Dict[str, list] = {aid: [] for aid in self.topo.all_ids()}
        for idx in range(config.HISTORY_SAMPLES):
            fleet = self.signal.sample_fleet(idx, 0, [])
            for aid, s in fleet.items():
                m = s["metrics"]
                if aid not in features:
                    features[aid] = [c for c in signals.METRIC_COLUMNS
                                     if isinstance(m.get(c), (int, float))]
                metric_rows[aid].append([float(m[c]) for c in features[aid]])
                code_seq[aid].append(s["primary_code"])
        history = {aid: {"X": rows, "features": features[aid]}
                   for aid, rows in metric_rows.items()}
        return history, code_seq

    def train(self) -> None:
        history, code_seq = self.build_history()
        self.metric_model.fit(history)
        self.code_model.fit(list(code_seq.values()))
        algos = ["Robust z-score (median/MAD)", "Mahalanobis distance"]
        if self.metric_model.uses_iforest:
            algos.insert(0, "Isolation Forest (scikit-learn)")
        self.train_report = {
            "history_samples": config.HISTORY_SAMPLES,
            "history_days": config.HISTORY_DAYS,
            "sample_interval_min": config.SAMPLE_INTERVAL_MIN,
            "assets_modelled": self.metric_model.n_trained,
            "metric_algorithms": algos,
            "code_algorithm": "First-order Markov transition-surprise + rare-code frequency",
            "code_transitions_learned": self.code_model.n_transitions,
            "code_vocabulary": self.code_model.V,
        }

    # -- lifecycle ---------------------------------------------------------- #
    def reset(self) -> None:
        self.current_idx: int = -1
        self.faults: List[FaultSpec] = self._fresh_faults()
        self.baseline_faults: List[FaultSpec] = self._fresh_faults()

        self.bb = Blackboard(self.topo, self.metric_model, self.code_model)
        self.monitor = MonitorAgent(self.topo, self.metric_model, self.code_model)
        self.diagnostician = DiagnosticianAgent(self.topo)
        self.decider = DeciderAgent(self.topo)
        self.actuator = ActuatorAgent()
        self.verifier = VerifierAgent(self.topo, self.metric_model)

        self.cases: List[Case] = []
        self.case_index: Dict[tuple, Case] = {}
        self.history: Dict[int, dict] = {}
        self.score_hist: Dict[str, list] = defaultdict(list)
        self.surprise_hist: Dict[str, list] = defaultdict(list)
        self.events: List[dict] = []
        self._case_counter = 0

    @property
    def log(self) -> List[LogEntry]:
        return self.bb.messages

    @property
    def tool_calls(self):
        return self.bb.tool_calls

    @property
    def at_end(self) -> bool:
        return self.current_idx + 1 >= config.LIVE_SAMPLES

    def timestamp(self, live_idx: int):
        return signals.timestamp_for(config.HISTORY_SAMPLES + live_idx)

    # -- helpers ------------------------------------------------------------ #
    def _next_case_id(self) -> str:
        self._case_counter += 1
        return f"C{self._case_counter:03d}"

    def _match_fault(self, proto: ProtoCase) -> Optional[FaultSpec]:
        active = [f for f in self.faults if f.is_active(self.current_idx)]
        for f in active:
            if f.fault_type == proto.fault_type and f.asset_id == proto.root_asset_id:
                return f
        for f in active:
            if f.fault_type == proto.fault_type:
                return f
        return None

    # -- main tick ---------------------------------------------------------- #
    def tick(self) -> None:
        if self.at_end:
            return
        self.current_idx += 1
        idx = self.current_idx
        abs_idx = config.HISTORY_SAMPLES + idx

        active = [f for f in self.faults if f.is_active(idx)]
        sample = self.signal.sample_fleet(abs_idx, idx, active)
        self.history[idx] = sample
        self.bb.begin_tick(idx, sample)

        # 1) VERIFIER - confirm any in-flight remediation
        for case in self.cases:
            if case.status == "ACTING":
                msg = self.verifier.verify(case, idx, self.bb)
                if msg:
                    if case.status == "RESOLVED":
                        value.estimate(case, self.topo)
                        self.bb.log(self.verifier.name, case.case_id,
                                    f"{msg} Prevented ~{case.downtime_avoided_min:.0f} min "
                                    f"downtime (~${case.cost_avoided_usd:,.0f}).", "success")
                    else:
                        self.bb.log(self.verifier.name, case.case_id, msg, "escalate")

        # 2) MONITOR + 3) DIAGNOSTICIAN (agents write to the blackboard)
        self.monitor.run(self.bb)
        self.diagnostician.run(self.bb)

        # record score history + event stream for the live charts
        for aid, sc in self.bb.tick_scores.items():
            self.score_hist[aid].append(sc["score"])
            self.surprise_hist[aid].append(sc["surprise"])
        for aid, s in sample.items():
            if s["primary_code"] != config.CODE_OK:
                self.events.append({
                    "idx": idx, "asset": aid, "code": s["primary_code"],
                    "codes": s["codes"],
                })

        # 4) DECIDER + 5) ACTUATOR for each new case
        for proto in self.bb.proto_cases:
            key = (proto.root_asset_id, proto.fault_type)
            existing = self.case_index.get(key)
            if existing and existing.status in ("OPEN", "ACTING", "ESCALATED", "RESOLVED", "FAILED"):
                continue

            # Downstream fallout of an already-handled propagating event (voltage
            # sag / breaker trip) is a symptom, not a new root cause.
            if proto.fault_type in ("VOLTAGE_SAG", "BREAKER_TRIP"):
                if any((anc, proto.fault_type) in self.case_index
                       for anc in self.topo.ancestors(proto.root_asset_id)):
                    continue

            matched = self._match_fault(proto)
            ob = proto.observations[0]
            case = Case(
                case_id=self._next_case_id(), opened_step=idx,
                root_asset_id=proto.root_asset_id, fault_type=proto.fault_type,
                confidence=proto.confidence, symptom_asset_ids=proto.symptom_asset_ids,
                observations=proto.observations,
                ground_truth_root=(matched.ground_truth_root_cause if matched else ""),
            )
            self.cases.append(case)
            self.case_index[key] = case

            asset = self.topo.get(proto.root_asset_id)
            codes = "/".join(ob.codes) or "none"
            self.bb.log(self.monitor.name, case.case_id,
                        f"Anomaly confirmed at {proto.root_asset_id}: model score "
                        f"{ob.model_score:.2f}, codes [{codes}]"
                        + (f"; {len(proto.symptom_asset_ids)} downstream asset(s) affected."
                           if proto.symptom_asset_ids else "."), "warn")
            elim = (f" Eliminated {len(proto.symptom_asset_ids)} downstream symptom(s) "
                    f"({', '.join(proto.symptom_asset_ids)})." if proto.symptom_asset_ids else "")
            self.bb.log(self.diagnostician.name, case.case_id,
                        f"Isolated ROOT CAUSE = {proto.root_asset_id} ({asset.name}). "
                        f"Fault: {proto.fault_type}. Confidence {proto.confidence:.2f}.{elim}")

            self.decider.decide(case, self.bb)
            self.bb.log(self.decider.name, case.case_id,
                        f"Decision: {case.decision.replace('_', ' ')}. {case.decision_reason}",
                        "action" if case.decision == "AUTO_REMEDIATE" else "escalate")

            act_msg = self.actuator.act(case, idx, matched, self.bb)
            self.bb.log(self.actuator.name, case.case_id, act_msg,
                        "action" if case.decision == "AUTO_REMEDIATE" else "escalate")

            if case.status == "ESCALATED":
                value.estimate(case, self.topo)
                self.bb.log(self.actuator.name, case.case_id,
                            f"Early-detection value of pre-diagnosed handoff: "
                            f"~${case.cost_avoided_usd:,.0f}.", "info")

    def run_all(self) -> None:
        while not self.at_end:
            self.tick()

    # -- accessors for the dashboard / CLI --------------------------------- #
    def baseline_sample(self, idx: int) -> dict:
        abs_idx = config.HISTORY_SAMPLES + idx
        active = [f for f in self.baseline_faults if f.is_active(idx)]
        return self.signal.sample_fleet(abs_idx, idx, active)

    def asset_series(self, aid: str, metric: str):
        xs, ys = [], []
        for idx in range(self.current_idx + 1):
            v = self.history.get(idx, {}).get(aid, {}).get("metrics", {}).get(metric, None)
            if isinstance(v, (int, float)):
                xs.append(idx)
                ys.append(v)
        return xs, ys

    def baseline_series(self, aid: str, metric: str):
        ys = []
        for idx in range(self.current_idx + 1):
            v = self.baseline_sample(idx).get(aid, {}).get("metrics", {}).get(metric, None)
            ys.append(v if isinstance(v, (int, float)) else None)
        return ys

    def summary(self) -> dict:
        resolved = [c for c in self.cases if c.status == "RESOLVED"]
        escalated = [c for c in self.cases if c.status in ("ESCALATED", "FAILED")]
        realized = resolved + escalated
        diagnosed = [c for c in self.cases if c.ground_truth_root]
        correct = [c for c in diagnosed if c.diagnosis_correct]
        return {
            "current_idx": self.current_idx,
            "total_cases": len(self.cases),
            "auto_resolved": len(resolved),
            "escalated": len(escalated),
            "diagnosis_accuracy": (len(correct) / len(diagnosed)) if diagnosed else 1.0,
            "downtime_avoided_min": round(sum(c.downtime_avoided_min for c in realized), 1),
            "cost_avoided_usd": round(sum(c.cost_avoided_usd for c in realized), 0),
            "tool_calls": len(self.tool_calls),
        }


# Backwards-compatible alias.
Orchestrator = Engine

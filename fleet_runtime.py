"""Session-owned five-agent fleet replay with observable tools and case lifecycle."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from collections.abc import Callable
import uuid

from fleet_data import BENIGN_CODES, PROPAGATING_CODES, FleetDataset, Reading
from fleet_models import LearnedDetectors
from fleet_playbook import lookup_playbook
from orchestrator import run_case


class FleetEngine:
    def __init__(self, data: FleetDataset, sop: str, *, offline: bool = False, evaluation_scenarios: list[dict] | None = None):
        self.data = data.model_copy(deep=True)
        self.sop, self.offline = sop, offline
        if evaluation_scenarios and data.source != "synthetic":
            raise ValueError("Ground-truth evaluation is only supported for trusted synthetic scenarios.")
        self.evaluation_scenarios = [dict(row) for row in evaluation_scenarios or []]
        self.run_id = str(uuid.uuid4())
        self.assets = {asset.id: asset for asset in self.data.assets}
        self.detectors = LearnedDetectors(self.data)
        frames: dict = defaultdict(dict)
        for reading in self.data.telemetry:
            frames[reading.timestamp][reading.asset_id] = reading
        self.frames = list(sorted(frames.items()))
        self.cursor = 0
        self.cases: list[dict] = []
        self.trace: list[dict] = []
        self.samples: list[dict] = []
        self.score_history: list[dict] = []
        self.code_memory: dict[str, list[str]] = defaultdict(list)
        self.metric_streak: dict[tuple[str, str], int] = defaultdict(int)
        self.latest: dict[str, dict] = {}
        self.simulated_fixes: dict[tuple[str, str], dict] = {}
        self.callback: Callable[[dict], None] | None = None
        self.emit("Monitor", "train_models", {
            "history_rows": len(data.history), "assets": len(data.assets),
            "history_end": max(row.timestamp for row in data.history).isoformat(),
            "replay_start": self.frames[0][0].isoformat(),
            "models": ["median/MAD", "IsolationForest corroboration", "Mahalanobis diagnostic", "Markov event transitions"],
        })

    @property
    def at_end(self) -> bool:
        return self.cursor >= len(self.frames)

    def emit(self, agent: str, tool: str, result: dict) -> None:
        event = {"sequence": len(self.trace) + 1, "at": datetime.now(timezone.utc).isoformat(),
                 "tick": self.cursor, "agent": agent, "tool": tool, "result": result}
        self.trace.append(event)
        if self.callback:
            self.callback(event)

    def ancestors(self, asset_id: str) -> list[str]:
        result = []
        parent = self.assets[asset_id].parent_id
        while parent:
            result.append(parent)
            parent = self.assets[parent].parent_id
        return result

    def _category(self, row: Reading) -> str:
        codes = set(row.event_codes)
        if any(code.startswith(("BRG", "VIB")) for code in codes):
            return "bearing"
        if codes & {"PRS-LOW", "LEAK"}:
            return "pressure"
        if codes & {"BATT_WEAK", "SELFTEST_FAIL"}:
            return "battery"
        if codes & {"THD_HIGH", "WAVEFORM_DISTORT"}:
            return "harmonics"
        if codes & {"OVERLOAD_ALARM", "OUTPUT_OVERCURRENT", "OC-TRIP"}:
            return "overload"
        if any("TEMP" in code or "FAN" in code for code in codes - BENIGN_CODES):
            return "thermal"
        return "local"

    def _metrics_for(self, asset_id: str, category: str, observations: dict) -> list[str]:
        if category == "electrical_supply":
            keys = ["voltage_v", "breaker_status"]
            if "BREAKER_OPEN" in observations[asset_id]["reading"].event_codes or "LOAD_LOST" in observations[asset_id]["reading"].event_codes:
                keys.extend(["current_a", "load_pct"])
            return [key for key in keys if key in observations[asset_id]["reading"].metrics]
        if category == "thermal":
            return [key for key in ("winding_temp_c", "temperature_c") if key in observations[asset_id]["reading"].metrics]
        if category == "overload":
            return [key for key in ("load_pct", "current_a") if key in observations[asset_id]["reading"].metrics]
        specific = {"bearing": "vibration_mm_s", "pressure": "hydraulic_pressure_bar", "battery": "battery_soc_pct", "harmonics": "thd_pct"}
        if category in specific:
            return [specific[category]] if specific[category] in observations[asset_id]["reading"].metrics else []
        return [signal["metric"] for signal in observations[asset_id]["metrics"]["signals"] if signal["anomalous"]]

    def _healthy_for_case(self, case: dict, observations: dict) -> tuple[bool, list[dict]]:
        checks = []
        for asset_id in [case["root_asset_id"], *case["symptom_asset_ids"]]:
            observation = observations[asset_id]
            metrics = case["verification_metrics"].get(asset_id, [])
            signals = {signal["metric"]: signal for signal in observation["metrics"]["signals"]}
            relevant_codes = set(observation["reading"].event_codes) - BENIGN_CODES
            if case["category"] == "electrical_supply":
                relevant_codes &= PROPAGATING_CODES
            else:
                relevant_codes -= PROPAGATING_CODES
            healthy = all(not signals[key]["anomalous"] for key in metrics) and not relevant_codes
            checks.append({"asset_id": asset_id, "healthy": healthy,
                           "signals": [signals[key] for key in metrics], "remaining_codes": sorted(relevant_codes)})
        return all(check["healthy"] for check in checks), checks

    def _apply_simulation(self, rows: dict[str, Reading]) -> None:
        for (asset_id, category), intervention in self.simulated_fixes.items():
            row = rows[asset_id]
            state = self.detectors.states[asset_id]
            for feature in intervention["metrics"]:
                index = state["features"].index(feature)
                row.metrics[feature] = float(state["median"][index])
            if category == "electrical_supply":
                row.event_codes = [code for code in row.event_codes if code not in PROPAGATING_CODES] or ["OK"]
            else:
                row.event_codes = [code for code in row.event_codes if code not in intervention["codes"]] or ["OK"]

    def tick(self, on_event: Callable[[dict], None] | None = None) -> None:
        if self.at_end:
            raise ValueError("Replay has finished. Load/reset data to start again.")
        self.callback = on_event
        try:
            self._tick()
        finally:
            self.callback = None

    def _tick(self) -> None:
        timestamp, original = self.frames[self.cursor]
        rows = {key: value.model_copy(deep=True) for key, value in original.items()}
        if self.data.source == "synthetic":
            self._apply_simulation(rows)
        observations = {}
        for asset_id, row in rows.items():
            metric_result = self.detectors.score(row)
            code_result = self.detectors.scan_codes(row, self.code_memory[asset_id])
            self.code_memory[asset_id] = (self.code_memory[asset_id] + [code_result["current"]])[-8:]
            observations[asset_id] = {"reading": row, "metrics": metric_result, "codes": code_result}
            for signal in metric_result["signals"]:
                key = (asset_id, signal["metric"])
                self.metric_streak[key] = self.metric_streak[key] + 1 if signal["anomalous"] else 0
            self.emit("Monitor", "score_metric_model", {"asset_id": asset_id, **metric_result})
            self.emit("Monitor", "scan_code_patterns", {"asset_id": asset_id, **code_result})
            self.samples.append({"timestamp": timestamp.isoformat(), "asset_id": asset_id, **row.metrics,
                                 **{f"original_{key}": value for key, value in original[asset_id].metrics.items()}})
            self.score_history.append({"timestamp": timestamp.isoformat(), "asset_id": asset_id,
                                       "anomaly_score": metric_result["score"]})
        self.latest = observations
        # Verification always uses subsequent ticks, never the input that opened the case.
        for case in self.cases:
            if case["status"] not in {"ACTING", "RESOLVED"}:
                continue
            healthy, checks = self._healthy_for_case(case, observations)
            if case["status"] == "RESOLVED":
                if not healthy:
                    case["status"] = "REOPENED"
                    case["verification"] = {"status": "reopened", "checks": checks,
                                            "summary": "The fault recurred; engineer review required."}
                    self.emit("Verifier", "recurrence_detected", {"case_id": case["case_id"], "checks": checks})
                continue
            case["verification_attempts"] += 1
            case["healthy_streak"] = case["healthy_streak"] + 1 if healthy else 0
            case["verification"] = {"status": "pending", "checks": checks,
                                    "attempt": case["verification_attempts"], "healthy_streak": case["healthy_streak"]}
            if case["healthy_streak"] >= 2:
                case["status"] = "RESOLVED"
                elapsed = (timestamp - case["opened_at"]).total_seconds() / 60
                asset = self.assets[case["root_asset_id"]]
                opportunity = max(0, asset.assumed_manual_mttr_minutes - elapsed) * asset.downtime_cost_per_minute
                case["verification"]["status"] = "simulated_recovery" if self.data.source == "synthetic" else "observed_recovery"
                case["value"] = {"potential_usd": round(opportunity) if self.data.source == "synthetic" else 0,
                                 "realized_usd": 0, "elapsed_replay_minutes": elapsed,
                                 "assumed_manual_mttr_minutes": asset.assumed_manual_mttr_minutes,
                                 "assumed_cost_per_minute": asset.downtime_cost_per_minute,
                                 "basis": "Synthetic counterfactual only; correlation is not proof of repair."}
            elif case["verification_attempts"] >= 3:
                case["status"] = "FAILED"
                case["verification"]["status"] = "failed"
                case["verification"]["summary"] = "Three subsequent ticks without two consecutive healthy observations; engineer escalation."
            self.emit("Verifier", "verify_subsequent_samples", {"case_id": case["case_id"], **case["verification"]})

        propagating = {key for key, value in observations.items()
                       if set(value["reading"].event_codes) & PROPAGATING_CODES}
        roots = sorted((key for key in propagating if not set(self.ancestors(key)) & propagating),
                       key=lambda key: len(self.ancestors(key)))
        groups = []
        for root in roots:
            symptoms = sorted(key for key in propagating if root in self.ancestors(key))
            groups.append((root, "electrical_supply", symptoms))
        for asset_id, observation in observations.items():
            propagated_metrics = set(self._metrics_for(asset_id, "electrical_supply", observations)) if asset_id in propagating else set()
            local_signals = [signal for signal in observation["metrics"]["signals"]
                             if signal["anomalous"] and signal["metric"] not in propagated_metrics
                             and self.metric_streak[(asset_id, signal["metric"])] >= 2]
            local_codes = set(observation["reading"].event_codes) - BENIGN_CODES - PROPAGATING_CODES
            if local_signals or local_codes:
                groups.append((asset_id, self._category(observation["reading"]), []))
        self.emit("Diagnostician", "correlate_topology", {
            "groups": [{"root_candidate": root, "category": category, "symptoms": symptoms}
                       for root, category, symptoms in groups],
            "basis": "Upstream/downstream temporal correlation, not a proven causal diagnosis.",
        })
        for root, category, symptoms in groups:
            existing = next((case for case in reversed(self.cases)
                             if case["root_asset_id"] == root and case["category"] == category), None)
            if existing:
                existing["last_seen_tick"] = self.cursor
                new_symptoms = sorted(set(symptoms) - set(existing["symptom_asset_ids"]))
                if new_symptoms:
                    existing["symptom_asset_ids"] = sorted(set(existing["symptom_asset_ids"]) | set(symptoms))
                    for asset_id in new_symptoms:
                        existing["verification_metrics"][asset_id] = self._metrics_for(asset_id, category, observations)
                    # Expanded impact must be reviewed again, not covered by an earlier approval.
                    existing["status"] = "ESCALATED"
                    existing["decision"].update(action="escalate", requires_approval=False)
                    existing["decision"]["reasons"].append("New downstream symptoms appeared after initial assessment.")
                    existing["verification"] = {"status": "scope_changed", "summary": "Expanded impact requires engineer review."}
                    self.emit("Decider", "expanded_impact", {"case_id": existing["case_id"], "new_symptoms": new_symptoms})
                # A recurrence is escalated on the original case rather than silently suppressed.
                if existing["status"] == "RESOLVED":
                    existing["status"] = "REOPENED"
                    existing["verification"] = {"status": "reopened"}
                    self.emit("Verifier", "recurrence_detected", {"case_id": existing["case_id"]})
                continue
            self._open_case(root, category, symptoms, observations, timestamp)
        self.emit("Monitor", "tick_completed", {"timestamp": timestamp.isoformat(), "cases": len(self.cases)})
        self.cursor += 1

    def _open_case(self, root: str, category: str, symptoms: list[str], observations: dict, timestamp) -> None:
        observation = observations[root]
        row = observation["reading"]
        state = self.detectors.states[root]
        incident = {
            "asset": self.assets[root].model_dump(include={"id", "type", "criticality"}),
            "event_codes": row.event_codes[:20],
            "metrics": {key: {"baseline": [reading.metrics[key] for reading in state["rows"]],
                              "latest": value} for key, value in row.metrics.items()},
        }
        context = {"source": self.data.source, "category": category, "root_candidate": root,
                   "ancestors": self.ancestors(root), "symptom_asset_ids": symptoms,
                   "protected_symptom_assets": [key for key in symptoms if self.assets[key].criticality in {"critical", "unknown"}],
                   "correlated_observations": {asset_id: {
                       "metric_model": observations[asset_id]["metrics"], "code_model": observations[asset_id]["codes"]}
                       for asset_id in [root, *symptoms]},
                   "unknown_codes": sorted({code for asset_id in [root, *symptoms]
                                            for code in observations[asset_id]["codes"]["unknown_codes"]})}
        context["playbook"] = lookup_playbook(category)
        self.emit("Decider", "lookup_playbook", {"category": category, **context["playbook"]})
        case = run_case(incident, self.sop, offline=self.offline, context=context, on_event=self.emit)
        # A fleet case cannot be verified by a predefined incident snapshot.
        case.update(root_asset_id=root, category=category, symptom_asset_ids=symptoms,
                    opened_at=timestamp, opened_tick=self.cursor, last_seen_tick=self.cursor,
                    verification_metrics={key: self._metrics_for(key, category, observations) for key in [root, *symptoms]},
                    verification_attempts=0, healthy_streak=0,
                    status="ERROR" if case["errors"] else ("AWAITING_APPROVAL" if case["decision"]["requires_approval"] else "ESCALATED"),
                    verification={"status": "awaiting_review", "summary": "No later samples verified yet."},
                    value={"potential_usd": 0, "realized_usd": 0},
                    mode=f"{'offline rules' if self.offline else 'Google AI'} / {self.data.source} fleet replay")
        self.cases.append(case)
        self.emit("Actuator", "case_opened", {"case_id": case["case_id"], "status": case["status"]})

    def retry(self, case_id: str, on_event: Callable[[dict], None] | None = None) -> None:
        case = next(case for case in self.cases if case["case_id"] == case_id)
        if case["status"] != "ERROR":
            raise ValueError("Only a failed analysis can be retried.")
        self.callback = on_event
        try:
            result = run_case(case["incident"], self.sop, offline=self.offline,
                              context=case["evidence"]["fleet_context"], on_event=self.emit)
            for key in ("evidence", "diagnosis", "decision", "action", "errors", "elapsed_seconds"):
                case[key] = result[key]
            case["status"] = "ERROR" if case["errors"] else ("AWAITING_APPROVAL" if case["decision"]["requires_approval"] else "ESCALATED")
            self.emit("Actuator", "analysis_retried", {"case_id": case_id, "status": case["status"]})
        finally:
            self.callback = None

    def approve(self, case_id: str, reviewer: str) -> None:
        case = next(case for case in self.cases if case["case_id"] == case_id)
        if not reviewer.strip():
            raise ValueError("A named reviewer is required.")
        if case["status"] != "AWAITING_APPROVAL" or case["errors"]:
            raise ValueError("Only an eligible pending sandbox proposal can be approved.")
        if self.at_end:
            raise ValueError("No subsequent telemetry remains. Reset/replay before approving.")
        case["approval"] = {"approved": True, "reviewer": reviewer.strip()}
        case["status"] = "ACTING"
        case["action"]["status"] = "sandbox_approved"
        case["action"]["summary"] = "Sandbox approved; no equipment commands sent."
        if self.data.source == "synthetic":
            for asset_id, metrics in case["verification_metrics"].items():
                self.simulated_fixes[(asset_id, case["category"])] = {
                    "metrics": set(metrics), "codes": set(self.latest[asset_id]["reading"].event_codes) - BENIGN_CODES - PROPAGATING_CODES,
                }
        case["verification"] = {"status": "pending", "summary": "Waiting for two consecutive healthy future ticks (maximum three)."}
        self.emit("Actuator", "approve_sandbox", {
            "case_id": case_id, "reviewer": reviewer.strip(),
            "effect": "synthetic scenario intervention" if self.data.source == "synthetic" else "observation only; uploaded measurements unchanged",
        })

    def training_report(self) -> list[dict]:
        return [{"asset_id": asset_id, "history_rows": len(state["rows"]),
                 "features": ", ".join(state["features"]),
                 "history_end": state["rows"][-1].timestamp.isoformat(),
                 "Markov_transitions_learned": sum(self.detectors.transitions.values()),
                 "Markov_vocabulary": len(self.detectors.vocabulary),
                 "mahalanobis_limit": round(state["maha_limit"], 3)}
                for asset_id, state in self.detectors.states.items()]

    def audit(self) -> dict:
        return {"run_id": self.run_id, "source": self.data.source, "ticks_processed": self.cursor,
                "total_ticks": len(self.frames), "cases": self.cases, "tool_calls": self.trace,
                "training": self.training_report(), "scores": self.score_history, "samples": self.samples,
                "synthetic_evaluation": self.evaluation()}

    def evaluation(self) -> list[dict]:
        results = []
        for scenario in self.evaluation_scenarios:
            if self.cursor <= scenario["start_tick"]:
                continue
            match = next((case for case in self.cases
                          if case["root_asset_id"] == scenario["asset_id"] and case["category"] == scenario["category"]
                          and case["opened_tick"] >= scenario["start_tick"]), None)
            results.append({**scenario, "detected": match is not None,
                            "detection_delay_ticks": match["opened_tick"] - scenario["start_tick"] if match else None})
        return results

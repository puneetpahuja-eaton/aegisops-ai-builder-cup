"""Cloud adapters around the unchanged PRISM models, simulator and agent engine."""
from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import uuid

REFERENCE = Path(__file__).resolve().parent / "prism_reference"
if str(REFERENCE) not in sys.path:
    sys.path.insert(0, str(REFERENCE))

from prism import config
from prism.agent_runtime import Blackboard
from prism.agents.actuator import ActuatorAgent
from prism.agents.decider import DeciderAgent
from prism.models import CodePatternModel, MetricAnomalyModel
from prism.orchestrator import Engine as ReferenceEngine
from prism.signals import SignalSource
from prism.topology import Asset, Topology

from actuator import act
from diagnostician import diagnose
from fleet_data import FleetDataset, load_bundle, load_csv
from gemini_client import is_live
from orchestrator import MODEL_FAILURES
import storage


def load_topology(text: str) -> Topology:
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    required = {"asset_id", "name", "type", "parent_id", "site", "rated_kw", "criticality"}
    if set(reader.fieldnames or []) != required:
        raise ValueError("PRISM asset file must contain the seven original topology fields.")
    assets = {}
    for row in reader:
        asset_id = row["asset_id"]
        if not asset_id or asset_id in assets:
            raise ValueError("Topology IDs must be nonempty and unique.")
        if row["criticality"] not in {"LOW", "MEDIUM", "HIGH", "CRITICAL", "UNKNOWN"}:
            raise ValueError(f"Invalid criticality for {asset_id}.")
        rated_kw = float(row["rated_kw"])
        if not 0 < rated_kw <= 1_000_000:
            raise ValueError("rated_kw must be positive and finite.")
        assets[asset_id] = Asset(asset_id, row["name"], row["type"], row["parent_id"] or None,
                                 row["site"], rated_kw, row["criticality"])
    if not 1 <= len(assets) <= 50:
        raise ValueError("Topology needs 1-50 assets.")
    for asset in assets.values():
        visited = {asset.asset_id}
        parent = asset.parent_id
        while parent:
            if parent not in assets or parent in visited:
                raise ValueError("Topology has an unknown parent or a cycle.")
            visited.add(parent)
            parent = assets[parent].parent_id
        if asset.parent_id:
            assets[asset.parent_id].children.append(asset.asset_id)
    return Topology(assets)


class CloudBlackboard(Blackboard):
    def __init__(self, topo, metric_model, code_model, engine):
        super().__init__(topo, metric_model, code_model)
        self.engine = engine

    def record_tool(self, agent: str, tool: str, detail: str, result: str) -> None:
        super().record_tool(agent, tool, detail, result)
        event = {"timestamp": datetime.now(timezone.utc).isoformat(), "step": self.step,
                 "agent": agent, "tool": tool, "detail": detail, "result": str(result)}
        self.engine.cloud_events.append(event)
        if self.engine.on_event:
            self.engine.on_event(event)


class CloudDecider(DeciderAgent):
    def __init__(self, engine):
        super().__init__(engine.topo)
        self.engine = engine

    def decide(self, case, bb) -> None:
        # Preserve PRISM's exact deterministic confidence/reversibility policy.
        super().decide(case, bb)
        if self.engine.source == "uploaded":
            case.decision = "ESCALATE"
            case.decision_reason = "Uploaded telemetry is observation-only; simulated control is disabled. " + case.decision_reason
        self.engine.enrich(case, bb)


class CloudActuator(ActuatorAgent):
    def __init__(self, engine):
        super().__init__()
        self.engine = engine

    def act(self, case, step, fault, bb) -> str:
        if self.engine.source == "uploaded" and case.decision == "AUTO_REMEDIATE":
            raise RuntimeError("Uploaded measurements cannot receive simulated control.")
        result = super().act(case, step, fault, bb)
        detail = self.engine.cloud_cases.get(case.case_id)
        if detail:
            detail["simulator_only"] = self.engine.source == "synthetic"
            detail["equipment_commands_sent"] = False
        return result


class ReplaySource:
    def __init__(self, data: FleetDataset):
        self.frames = {}
        for index, timestamp in enumerate(sorted({row.timestamp for row in data.telemetry})):
            self.frames[index] = {
                row.asset_id: {"metrics": dict(row.metrics), "codes": list(row.event_codes),
                               "primary_code": next((code for code in row.event_codes if code in config.CODE_TO_FAULT),
                                                    row.event_codes[0] if row.event_codes else "OK")}
                for row in data.telemetry if row.timestamp == timestamp
            }

    def sample_fleet(self, abs_idx, live_idx, active):
        # Each caller receives an independent snapshot; no simulator mutations.
        import copy
        return copy.deepcopy(self.frames[live_idx])


class Engine(ReferenceEngine):
    def __init__(self, *, offline: bool | None = None, dataset: FleetDataset | None = None):
        self.offline = not is_live() if offline is None else offline
        self.source = "uploaded" if dataset is not None else "synthetic"
        self.dataset = dataset.model_copy(deep=True) if dataset is not None else None
        self.on_event = None
        self.sop = storage.load_text("sop.md")
        if self.dataset is None:
            self.topo = load_topology(storage.load_prism_text("assets.csv"))
            self.signal = SignalSource(self.topo)
            self._scenarios = json.loads(storage.load_prism_text("live_scenarios.json"))["scenarios"]
            for scenario in self._scenarios:
                if scenario["asset_id"] not in self.topo.assets or scenario["fault_type"] not in config.PLAYBOOK:
                    raise ValueError("Invalid configured PRISM scenario.")
            self.total_samples = config.LIVE_SAMPLES
        else:
            # Revalidate at the boundary, including callers other than the UI.
            self.dataset = FleetDataset.model_validate(self.dataset.model_dump())
            self.dataset.source = "uploaded"
            assets = {asset.id: Asset(asset.id, asset.name or asset.id, asset.type.upper(), asset.parent_id,
                                      asset.site or "UPLOADED", asset.rated_kw, asset.criticality.upper()) for asset in self.dataset.assets}
            for asset in assets.values():
                if asset.parent_id:
                    assets[asset.parent_id].children.append(asset.asset_id)
            self.topo = Topology(assets)
            self.signal = ReplaySource(self.dataset)
            self._scenarios = []
            self.total_samples = len(self.signal.frames)
        self.metric_model = MetricAnomalyModel()
        self.code_model = CodePatternModel()
        self.train_report = {}
        self.train()
        self.reset()

    def build_history(self):
        if self.dataset is None:
            return super().build_history()
        history, codes = {}, {}
        for asset_id in self.topo.all_ids():
            rows = [row for row in self.dataset.history if row.asset_id == asset_id]
            features = sorted(rows[0].metrics)
            history[asset_id] = {"X": [[row.metrics[key] for key in features] for row in rows], "features": features}
            codes[asset_id] = [row.event_codes[0] if row.event_codes else "OK" for row in rows]
        return history, codes

    def train(self) -> None:
        super().train()
        if self.dataset is not None:
            counts = [sum(row.asset_id == asset.id for row in self.dataset.history) for asset in self.dataset.assets]
            timestamps = sorted({row.timestamp for row in self.dataset.history})
            interval = (timestamps[1] - timestamps[0]).total_seconds() / 60 if len(timestamps) > 1 else 0
            self.train_report.update(history_samples=min(counts), history_days=round(
                (timestamps[-1] - timestamps[0]).total_seconds() / 86400, 3), sample_interval_min=interval)

    def reset(self) -> None:
        super().reset()
        self.run_id = str(uuid.uuid4())
        self.cloud_cases = {}
        self.cloud_events = []
        self.audit_revisions = {}
        self.audit_error = None
        self.bb = CloudBlackboard(self.topo, self.metric_model, self.code_model, self)
        self.decider = CloudDecider(self)
        self.actuator = CloudActuator(self)

    @property
    def at_end(self) -> bool:
        return self.current_idx + 1 >= self.total_samples

    def timestamp(self, live_idx):
        if self.dataset is None:
            return super().timestamp(live_idx)
        timestamps = sorted({row.timestamp for row in self.dataset.telemetry})
        return timestamps[live_idx]

    def enrich(self, case, bb) -> None:
        asset = self.topo.get(case.root_asset_id)
        metrics = bb.sample[case.root_asset_id]["metrics"]
        state = self.metric_model.assets[case.root_asset_id]
        evidence = {
            "asset_id": asset.asset_id, "asset_type": asset.type, "asset_criticality": asset.criticality.lower(),
            "event_codes": bb.sample[asset.asset_id]["codes"],
            "signals": [{"metric": key, "latest": metrics[key], "unit": "",
                         "robust_z": round(float((metrics[key] - state["median"][index]) / state["scale"][index]), 2),
                         "anomalous": abs(float((metrics[key] - state["median"][index]) / state["scale"][index])) >= config.ROBUST_Z_THRESHOLD}
                        for index, key in enumerate(state["features"])],
            "has_anomaly": True,
            "fleet_context": {"category": {"VOLTAGE_SAG": "electrical_supply", "BREAKER_TRIP": "electrical_supply",
                                          "THERMAL_RUNAWAY": "thermal", "OVERLOAD": "overload",
                                          "HARMONIC_DISTORTION": "harmonics", "BATTERY_DEGRADATION": "battery"}[case.fault_type],
                              "fault_type": case.fault_type, "symptom_asset_ids": case.symptom_asset_ids,
                              "ancestors": self.topo.ancestors(asset.asset_id), "source": self.source,
                              "heuristic_confidence": case.confidence, "deterministic_decision": case.decision},
        }
        evidence["anomalous_metrics"] = [signal["metric"] for signal in evidence["signals"] if signal["anomalous"]]
        detail = {"evidence": evidence, "errors": [], "work_order": None}
        self.cloud_cases[case.case_id] = detail
        bb.record_tool("Diagnostician", "gemini_grounded_diagnosis", asset.asset_id,
                       "Started explicit offline explanation" if self.offline else "Started Vertex AI request; waiting for validated output")
        try:
            diagnosis = diagnose(evidence, self.sop, offline=self.offline)
            detail["diagnosis"] = diagnosis
            bb.record_tool("Diagnostician", "validate_sop_citations", asset.asset_id,
                           f"{diagnosis['_source']} | {diagnosis['_citation_check']}")
            bb.log("Diagnostician", case.case_id, f"{diagnosis['_source']}: {diagnosis['root_cause']}")
            # Advisory cloud reasoning does not alter the canonical simulator's
            # classification/confidence. Missing grounding is not accepted as success.
            if diagnosis["insufficient_evidence"]:
                case.decision = "ESCALATE"
                case.decision_reason = "Google/offline SOP assessment reports insufficient evidence; engineer review required."
            if case.decision == "ESCALATE":
                bb.record_tool("Actuator", "gemini_work_order", case.case_id, "Preparing review-only work-order draft")
                output = act(evidence, diagnosis, {"action": "escalate"}, self.sop, offline=self.offline)
                detail["work_order"] = output["work_order"]
                bb.record_tool("Actuator", "gemini_work_order", case.case_id, output["work_order"]["_source"])
        except MODEL_FAILURES as error:
            detail["errors"].append(f"{type(error).__name__}: {error}")
            case.decision = "ESCALATE"
            case.decision_reason = "Cloud analysis failed; no offline result substituted. Engineer review required."
            bb.record_tool("Diagnostician", "cloud_analysis_failed", asset.asset_id, str(error))
            bb.log("Diagnostician", case.case_id, case.decision_reason, "escalate")

    def tick(self, on_event=None) -> None:
        if self.at_end:
            return
        self.on_event = on_event
        try:
            super().tick()
            if self.source == "uploaded":
                # There is no measured intervention/counterfactual for uploaded observations.
                for case in self.cases:
                    case.downtime_avoided_min = 0
                    case.cost_avoided_usd = 0
        finally:
            self.on_event = None

    def summary(self) -> dict:
        result = super().summary()
        if self.source == "uploaded":
            result["diagnosis_accuracy"] = None
        elif not any(case.ground_truth_root for case in self.cases):
            result["diagnosis_accuracy"] = None
        return result

    def audit(self) -> dict:
        return {"run_id": self.run_id, "source": self.source, "offline": self.offline,
                "summary": self.summary(), "training": self.train_report,
                "cases": [asdict(case) for case in self.cases], "cloud_cases": self.cloud_cases,
                "log": [asdict(entry) for entry in self.log], "tools": [asdict(call) for call in self.tool_calls],
                "events": self.cloud_events, "equipment_commands_sent": False, "realized_savings_usd": 0}


def replacement(text: str, filename: str) -> FleetDataset:
    return load_csv(text) if filename.lower().endswith(".csv") else load_bundle(text)

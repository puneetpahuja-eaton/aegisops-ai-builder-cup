"""
Shared data structures for the agentic workflow.

An `Observation` is what the Monitor sees. A `Case` is the unit of work that
flows through the whole pipeline (Monitor -> Diagnostician -> Decider ->
Actuator -> Verifier) and carries the evidence and decisions accumulated by
each agent. A `LogEntry` is one line in the human-readable reasoning trace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Observation:
    asset_id: str
    metric: str
    value: float
    severity: float        # 0..1, how far outside the healthy band / model score
    direction: str         # "low" or "high"
    # v2: evidence from the trained models
    model_score: float = 0.0          # Isolation Forest / robust-z combined score
    zmax: float = 0.0                 # strongest robust z-score
    codes: List[str] = field(default_factory=list)   # event/fault codes seen
    code_surprise: float = 0.0        # Markov transition surprise (nats)
    source: str = "metric"            # "metric" / "code" / "both"


@dataclass
class LogEntry:
    step: int
    agent: str             # Monitor / Diagnostician / Decider / Actuator / Verifier
    case_id: str
    message: str
    level: str = "info"    # info / action / success / escalate / warn


@dataclass
class Case:
    case_id: str
    opened_step: int
    root_asset_id: str
    fault_type: str
    confidence: float
    symptom_asset_ids: List[str] = field(default_factory=list)
    observations: List[Observation] = field(default_factory=list)

    # decision / action
    decision: Optional[str] = None          # AUTO_REMEDIATE / ESCALATE
    decision_reason: str = ""
    action: str = ""
    reversibility: str = ""

    # lifecycle
    status: str = "OPEN"                     # OPEN/ACTING/RESOLVED/ESCALATED/FAILED
    act_step: Optional[int] = None
    resolved_step: Optional[int] = None

    # value
    downtime_avoided_min: float = 0.0
    cost_avoided_usd: float = 0.0
    ground_truth_root: str = ""             # for scoring the diagnosis

    @property
    def diagnosis_correct(self) -> bool:
        return bool(self.ground_truth_root) and self.root_asset_id == self.ground_truth_root

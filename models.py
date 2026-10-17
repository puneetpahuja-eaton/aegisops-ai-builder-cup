"""Validated contracts for synthetic incidents and grounded model outputs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Asset(Contract):
    id: str = Field(min_length=1, max_length=80)
    type: str = Field(min_length=1, max_length=120)
    criticality: Literal["low", "medium", "high", "critical", "unknown"] = "unknown"


class Metric(Contract):
    unit: str = Field(default="", max_length=20)
    baseline: list[float] = Field(min_length=5, max_length=20_000)
    latest: float


class Incident(Contract):
    asset: Asset
    event_codes: list[str] = Field(default_factory=list, max_length=20)
    metrics: dict[str, Metric]
    post_action_metrics: dict[str, float] | None = None

    @field_validator("metrics")
    @classmethod
    def nonempty_metrics(cls, value: dict[str, Metric]) -> dict[str, Metric]:
        if not value or len(value) > 30:
            raise ValueError("An incident requires between 1 and 30 metrics.")
        return value

    @field_validator("event_codes")
    @classmethod
    def bounded_codes(cls, value: list[str]) -> list[str]:
        if any(not code or len(code) > 80 for code in value):
            raise ValueError("Event codes must contain 1-80 characters.")
        return value


class Citation(Contract):
    sop_id: str
    quote_index: int = Field(ge=0, le=100)


class Diagnosis(Contract):
    root_cause: str = Field(min_length=1, max_length=1000)
    asset_id: str = Field(min_length=1, max_length=80)
    confidence: float = Field(ge=0, le=1)
    cited_sop_ids: list[str] = Field(max_length=10)
    citation_quotes: list[Citation] = Field(max_length=10)
    reasoning: str = Field(min_length=1, max_length=5000)
    recommended_action: str = Field(min_length=1, max_length=2000)
    escalate: StrictBool
    insufficient_evidence: StrictBool


class WorkOrder(Contract):
    title: str = Field(min_length=1, max_length=200)
    asset_id: str = Field(min_length=1, max_length=80)
    priority: Literal["P1", "P2", "P3"]
    summary: str = Field(min_length=1, max_length=2000)
    steps: list[str] = Field(min_length=1, max_length=10)
    safety_notes: list[str] = Field(min_length=1, max_length=10)
    cited_sop_ids: list[str] = Field(max_length=10)

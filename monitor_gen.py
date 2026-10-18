"""Generate a live-monitoring plan from a natural-language instruction via Gemini.

The agent reads the device's ingested docs (RAG) to resolve parameter IDs, a
polling interval, and an event-log parameter plus a decode spec, so the existing
REST poller can monitor them. Event logs rarely decode trivially, so the flow
asks clarifying questions about the event structure first.

Flow mirrors the dataset builder:
  1. clarifying_questions(): Gemini asks about params, interval, event-log layout.
  2. generate_plan(): Gemini returns a compact JSON plan grounded in the docs.
The plan maps straight onto the Live Monitoring config (monitored params + an
optional event-log decode spec).
"""
from __future__ import annotations

import json
import re

from pydantic import BaseModel, Field

import rag
from gemini_client import generate_text, is_live


class MonitorParam(BaseModel):
    pid: str = Field(description="Parameter ID to poll via /rs/param/<id>/value")
    label: str = Field(default="", description="Human label, e.g. 'Phase A voltage'")
    unit: str = Field(default="")
    lower: float | None = Field(default=None, description="Lower alarm limit, if known")
    upper: float | None = Field(default=None, description="Upper alarm limit, if known")
    path: str = Field(default="", description="JSON path to the value if not the default 'value'")


class EventLogSpec(BaseModel):
    pid: str = Field(default="", description="Parameter ID / endpoint that returns the event log")
    format: str = Field(default="", description="How the event log is encoded (free-text understanding)")
    decode: str = Field(default="", description="Step-by-step decode instructions, for the engineer")
    word_index: int = Field(default=-1, description="0-based index of the hex word holding the event code (-1=unknown)")
    code_map: dict[str, str] = Field(default_factory=dict,
                                     description="Map raw code value (decimal or 0x hex string) -> event code name")


class MonitorPlan(BaseModel):
    poll_interval_s: int = Field(default=300, ge=1, le=86400)
    hex_as_float: bool = Field(default=True)
    params: list[MonitorParam] = Field(default_factory=list)
    event_log: EventLogSpec | None = Field(default=None)
    notes: str = Field(default="")


_SCHEMA_HINT = """Return ONLY a JSON object (no prose, no fences) like:
{
  "poll_interval_s": 300,
  "hex_as_float": true,
  "params": [
    {"pid": "22120", "label": "Phase A voltage", "unit": "V", "lower": 210, "upper": 250, "path": ""}
  ],
  "event_log": {"pid": "40010", "format": "ring buffer of 32-bit words",
                "decode": "each entry = timestamp(2 words) + code(1 word)",
                "word_index": 2, "code_map": {"0x0001": "VOLT_SAG", "0x0002": "OVERLOAD_ALARM"}},
  "notes": "assumptions"
}
Use the referenced docs to resolve real parameter IDs and units. For the event log,
set word_index to the 0-based hex-word position of the event code and code_map to the
raw-value -> event-name mapping. If the layout is unknown, leave event_log null."""


def _context(device_id: str) -> str:
    chunks = rag.retrieve(device_id, "parameter id register map event log fault log units thresholds "
                                     "voltage current power energy rest api", top_k=20)
    return "\n\n".join(c.get("text", "")[:900] for c in chunks)


def clarifying_questions(device_id: str, request: str, reference: str = "") -> str:
    prompt = (
        "A user wants to set up LIVE monitoring of a device over REST. Before building the plan, ask 3-6 "
        "concise clarifying questions that materially change it: which exact parameters/IDs to poll, the "
        "polling interval, alarm thresholds, and—critically—the EVENT LOG structure (which parameter/"
        "endpoint holds it, how entries are encoded, where the event code lives, how to decode it). Ask "
        "only questions; do not build the plan yet. Use the context to avoid asking what is already known.\n\n"
        f"Device context:\n{_context(device_id)[:8000]}\n\n"
        f"Referenced parameter file (optional):\n{reference[:8000]}\n\n"
        f"User request: {request}"
    )
    return generate_text(prompt, temperature=0.3)


def generate_plan(device_id: str, request: str, reference: str = "", answers: str = "") -> dict:
    if not is_live():
        raise RuntimeError("Google AI is required to generate a monitoring plan.")
    prompt = (
        "Design a COMPACT live-monitoring plan for this device over REST, grounded in the context and the "
        "referenced parameter list. Resolve real parameter IDs and units. Include alarm thresholds where the "
        "docs imply them. If the user described an event log, fill event_log with a concrete decode spec; "
        "otherwise set it to null. Make reasonable assumptions and note them.\n\n"
        f"{_SCHEMA_HINT}\n\n"
        f"Device context:\n{_context(device_id)[:8000]}\n\n"
        f"Referenced parameter file (optional, authoritative for IDs/units):\n{reference[:12000]}\n\n"
        f"User request: {request}\n\n"
        f"User answers to clarifying questions (if any): {answers}"
    )
    text = generate_text(prompt, temperature=0.3, max_output_tokens=8192)
    try:
        raw = _extract_json(text)
    except (json.JSONDecodeError, ValueError) as error:
        raise RuntimeError(f"Could not parse the monitoring plan from the model response: {error}") from error
    return MonitorPlan.model_validate(raw).model_dump()


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            text = text[start:end + 1]
    return json.loads(text)


def plan_to_config(plan: dict, base_endpoint: str) -> dict:
    """Translate a generated plan into the Live Monitoring config structure."""
    monitored = [{"pid": str(p["pid"]).strip(), "lower": p.get("lower"), "upper": p.get("upper"),
                  "label": p.get("label", ""), "path": p.get("path", "")}
                 for p in plan.get("params", []) if str(p.get("pid", "")).strip()]
    event_log = plan.get("event_log") or None
    return {
        "endpoint": base_endpoint,
        "interval": int(plan.get("poll_interval_s", 300)),
        "hex_as_float": bool(plan.get("hex_as_float", True)),
        "monitored": monitored,
        "param_ids": [m["pid"] for m in monitored],
        "event_log": event_log,
    }

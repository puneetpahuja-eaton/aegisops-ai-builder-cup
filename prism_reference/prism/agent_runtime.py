"""
agent_runtime.py - a small but real multi-agent runtime.

This is what makes PRISM's agents ACTUAL agents rather than plain function calls:

  * Blackboard - a shared working memory / message bus. Agents read the current
    world state and write observations, messages and results to it.
  * Tool       - a named capability an agent can invoke. Every invocation is
    recorded as a ToolCall, so the dashboard can show, live, which agent used
    which tool and what came back. That visible tool-use is the hallmark of an
    agentic workflow.
  * Agent      - a base class with a role, a set of tools, and a run() method
    implementing perceive -> reason -> act against the blackboard.

The reasoning is deterministic (ML models + rules), not an LLM - by design, so
the demo is fully offline and reproducible. The ARCHITECTURE, however, is a
genuine autonomous multi-agent system.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List

from .case import LogEntry


@dataclass
class ToolCall:
    step: int
    agent: str
    tool: str
    detail: str          # what the agent asked
    result: str          # short summary of what came back


class Tool:
    def __init__(self, name: str, description: str, fn: Callable):
        self.name = name
        self.description = description
        self.fn = fn


class Blackboard:
    """Shared memory the agents collaborate through."""

    def __init__(self, topo, metric_model, code_model):
        self.topo = topo
        self.metric_model = metric_model
        self.code_model = code_model

        # persistent across ticks
        self.code_memory: Dict[str, deque] = {}
        self.messages: List[LogEntry] = []
        self.tool_calls: List[ToolCall] = []
        self.flagged_assets: set = set()

        # per-tick working memory
        self.step: int = -1
        self.sample: Dict[str, dict] = {}
        self.observations: list = []
        self.proto_cases: list = []
        self.tick_scores: Dict[str, dict] = {}    # aid -> model scores (for live charts)

    def begin_tick(self, step: int, sample: Dict[str, dict]) -> None:
        self.step = step
        self.sample = sample
        self.observations = []
        self.proto_cases = []
        self.tick_scores = {}

    def log(self, agent: str, case_id: str, message: str, level: str = "info") -> None:
        self.messages.append(LogEntry(self.step, agent, case_id, message, level))

    def record_tool(self, agent: str, tool: str, detail: str, result: str) -> None:
        self.tool_calls.append(ToolCall(self.step, agent, tool, detail, str(result)[:160]))


class Agent:
    name: str = "Agent"
    role: str = ""

    def __init__(self, tools: List[Tool] | None = None):
        self.tools: Dict[str, Tool] = {t.name: t for t in (tools or [])}

    def call(self, bb: Blackboard, tool_name: str, detail: str, **kwargs):
        """Invoke a tool and record the call on the blackboard."""
        tool = self.tools[tool_name]
        result = tool.fn(**kwargs)
        bb.record_tool(self.name, tool_name, detail, self._summarise(result))
        return result

    @staticmethod
    def _summarise(result) -> str:
        if isinstance(result, dict):
            keys = ("is_anomaly", "score", "surprise", "fault_type", "decision", "ok")
            picked = {k: result[k] for k in keys if k in result}
            return str(picked) if picked else str(result)[:120]
        return str(result)[:120]

    def run(self, bb: Blackboard) -> None:      # pragma: no cover - overridden
        raise NotImplementedError

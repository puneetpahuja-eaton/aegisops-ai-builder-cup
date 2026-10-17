"""Lightweight live anomaly monitor for streamed REST readings.

Trains per-metric robust baselines from a rolling healthy window, flags anomalies
and produces issues with an auto-resolve/escalate decision and an *estimated*
downtime/cost-avoided figure (clearly labeled as an estimate, never measured).
"""
from __future__ import annotations

import statistics
from collections import defaultdict, deque

_HARD_CODES = {"BREAKER_OPEN", "OVERLOAD_ALARM", "SELFTEST_FAIL", "SMOKE", "ON_BATTERY", "TEMP_CRIT"}


def _robust_z(window: list[float], value: float) -> float:
    if len(window) < 5:
        return 0.0
    median = statistics.median(window)
    deviations = [abs(x - median) for x in window]
    mad = statistics.median(deviations) or 1e-9
    return abs(value - median) / (1.4826 * mad)


class LiveMonitor:
    def __init__(self, *, criticality: str = "medium", z_threshold: float = 4.0,
                 downtime_min_per_issue: float = 12.0, cost_per_min: float = 50.0, window: int = 40):
        self.criticality = criticality
        self.z_threshold = z_threshold
        self.downtime_min = downtime_min_per_issue
        self.cost_per_min = cost_per_min
        self.windows: dict[str, deque] = defaultdict(lambda: deque(maxlen=window))
        self.issues: list[dict] = []
        self.readings = 0
        self.downtime_avoided = 0.0
        self.cost_avoided = 0.0
        self._open_by_metric: dict[str, dict] = {}

    def observe(self, reading: dict) -> list[dict]:
        self.readings += 1
        metrics = reading.get("metrics", {})
        codes = set(reading.get("codes", []))
        new_issues: list[dict] = []

        for metric, value in metrics.items():
            window = self.windows[metric]
            z = _robust_z(list(window), value)
            window.append(value)
            anomalous = z >= self.z_threshold or bool(codes & _HARD_CODES)
            open_issue = self._open_by_metric.get(metric)

            if anomalous and not open_issue:
                hard = bool(codes & _HARD_CODES)
                escalate = hard or self.criticality in ("high", "critical")
                issue = {
                    "metric": metric, "value": round(value, 3), "z": round(z, 2),
                    "codes": sorted(codes), "timestamp": reading.get("timestamp"),
                    "decision": "ESCALATE" if escalate else "AUTO_RESOLVE",
                    "status": "ESCALATED" if escalate else "MONITORING",
                    "downtime_avoided_min": 0.0, "cost_avoided_usd": 0.0,
                }
                self.issues.append(issue)
                self._open_by_metric[metric] = issue
                new_issues.append(issue)
            elif not anomalous and open_issue and open_issue["status"] == "MONITORING":
                # A subsequent healthy reading resolves an auto-resolvable issue.
                open_issue["status"] = "RESOLVED"
                open_issue["downtime_avoided_min"] = self.downtime_min
                open_issue["cost_avoided_usd"] = round(self.downtime_min * self.cost_per_min, 2)
                self.downtime_avoided += self.downtime_min
                self.cost_avoided += open_issue["cost_avoided_usd"]
                self._open_by_metric.pop(metric, None)
        return new_issues

    def summary(self) -> dict:
        return {
            "readings": self.readings,
            "issues": len(self.issues),
            "auto_resolved": sum(1 for i in self.issues if i["status"] == "RESOLVED"),
            "escalated": sum(1 for i in self.issues if i["status"] == "ESCALATED"),
            "monitoring": sum(1 for i in self.issues if i["status"] == "MONITORING"),
            "downtime_avoided_min": round(self.downtime_avoided, 1),
            "cost_avoided_usd": round(self.cost_avoided, 2),
        }

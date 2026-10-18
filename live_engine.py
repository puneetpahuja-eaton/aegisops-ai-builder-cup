"""Bridge a live REST reading stream into the PRISM five-agent engine.

Both live monitoring and historic dataset analysis now run through the SAME
engine (prism_cloud.Engine):
  * Historic: a complete FleetDataset is replayed.
  * Live:     a warmup window establishes the healthy baseline and trains the
              models, then each new poll appends one frame and ticks the engine.

A single device is modelled as one asset. Metric columns are held constant
(missing values carry forward) so the engine's models stay valid.
"""
from __future__ import annotations

import datetime

from fleet_data import FleetAsset, FleetDataset, Reading
from prism_cloud import Engine  # Importing this prepends prism_reference to sys.path.
from prism import config as prism_config


def _parse_ts(value) -> datetime.datetime:
    if isinstance(value, datetime.datetime):
        ts = value
    else:
        ts = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=datetime.timezone.utc)
    return ts.astimezone(datetime.timezone.utc)


class LiveFleetEngine:
    """Warm up on healthy readings, then stream readings through PRISM."""

    def __init__(self, *, asset_id: str, criticality: str = "medium", offline: bool = False,
                 warmup: int = 20):
        self.asset_id = asset_id
        self.criticality = criticality
        self.offline = offline
        self.warmup = max(20, warmup)
        self.engine: Engine | None = None
        self._warmup_readings: list[Reading] = []
        self._features: list[str] | None = None
        self._last_metrics: dict[str, float] = {}
        self._last_ts: datetime.datetime | None = None
        self.status = "warming"

    # -- reading -> fleet frame ------------------------------------------- #
    def _clean_metrics(self, metrics: dict) -> dict[str, float]:
        numeric = {k: float(v) for k, v in (metrics or {}).items() if isinstance(v, (int, float))}
        if self._features is None:
            self._features = sorted(numeric) or ["value"]
        # Hold the column set constant: carry forward any missing metric.
        out = {}
        for key in self._features:
            if key in numeric:
                out[key] = numeric[key]
            else:
                out[key] = self._last_metrics.get(key, 0.0)
        self._last_metrics = dict(out)
        return out

    def _frame(self, metrics: dict[str, float], codes: list[str]) -> dict:
        primary = next((c for c in codes if c in prism_config.CODE_TO_FAULT), codes[0] if codes else "OK")
        return {self.asset_id: {"metrics": dict(metrics), "codes": list(codes) or ["OK"],
                                "primary_code": primary}}

    def _monotonic_ts(self, ts: datetime.datetime) -> datetime.datetime:
        # Strictly increasing timestamps so history precedes replay and ticks order.
        if self._last_ts is not None and ts <= self._last_ts:
            ts = self._last_ts + datetime.timedelta(seconds=1)
        self._last_ts = ts
        return ts

    # -- public API -------------------------------------------------------- #
    def observe(self, reading: dict) -> dict:
        """Feed one poll result. Returns {status, ticked, summary|None}."""
        metrics = self._clean_metrics(reading.get("metrics", {}))
        codes = list(reading.get("codes", []) or [])
        ts = self._monotonic_ts(_parse_ts(reading.get("timestamp") or datetime.datetime.now(datetime.timezone.utc)))

        if self.engine is None:
            # Warmup assumes a healthy baseline (only benign codes kept for training).
            self._warmup_readings.append(Reading(timestamp=ts, asset_id=self.asset_id,
                                                 metrics=metrics, event_codes=["OK"]))
            if len(self._warmup_readings) >= self.warmup + 1:
                self._build_engine()
                self.status = "live"
                return {"status": "live", "ticked": True, "summary": self.engine.summary()}
            return {"status": "warming", "ticked": False, "summary": None,
                    "collected": len(self._warmup_readings), "needed": self.warmup + 1}

        frame = self._frame(metrics, codes)
        self.engine.append_live(frame, ts)
        self.engine.tick()
        return {"status": "live", "ticked": True, "summary": self.engine.summary()}

    def _build_engine(self) -> None:
        history = self._warmup_readings[:-1]
        first = self._warmup_readings[-1]
        asset = FleetAsset(id=self.asset_id, name=self.asset_id, type="METER",
                           criticality=self.criticality.lower(), site="LIVE", rated_kw=100.0)
        dataset = FleetDataset(source="uploaded", assets=[asset], history=history, telemetry=[first])
        self.engine = Engine(offline=self.offline, dataset=dataset)
        # Live monitoring credits estimated early-detection value (accuracy stays n/a).
        self.engine.credit_value = True

    def summary(self) -> dict | None:
        return self.engine.summary() if self.engine else None

    def audit(self) -> dict | None:
        return self.engine.audit() if self.engine else None

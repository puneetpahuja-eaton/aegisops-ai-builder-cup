"""
signals.py - deterministic time-series generator with event/fault codes.

This is the v2 data source. Given an absolute sample index (each sample = 5 min)
and the set of active faults, it produces, for every asset:

  * a multivariate metric vector (voltage, current, load, temperature, THD,
    frequency, battery SoC), shaped by a realistic DAILY (diurnal) load cycle, and
  * a list of operational/fault EVENT CODES (e.g. OK, SELFTEST_PASS, VOLT_SAG,
    BATT_WEAK, BREAKER_OPEN) - the "flood of codes" the pattern model mines.

The same generator produces both the long HEALTHY history used to TRAIN the
anomaly models and the LIVE stream (with injected faults) shown on the dashboard.
Everything is reproducible: all noise derives from a hash of (asset, index, key).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from . import config
from .topology import Topology

# Order of metric columns used everywhere (models, CSVs, charts).
METRIC_COLUMNS = [
    "voltage_v", "current_a", "load_pct", "temperature_c",
    "thd_pct", "frequency_hz", "battery_soc_pct",
]

# Severity ranking used to pick the single "primary" code for a sample.
_CODE_SEVERITY = {
    "OK": 0, "FAN_OK": 1, "SELFTEST_PASS": 2, "LOAD_HIGH": 3, "BATT_WEAK": 4,
    "AVR_ENGAGE": 5, "VOLT_SAG": 6, "THD_HIGH": 7, "TEMP_WARN": 8,
    "FAN_FAULT": 9, "WAVEFORM_DISTORT": 10, "OVERLOAD_ALARM": 11,
    "INPUT_UNDERVOLT": 12, "ON_BATTERY": 13, "OUTPUT_OVERCURRENT": 14,
    "TEMP_CRIT": 15, "SELFTEST_FAIL": 16, "LOAD_LOST": 17, "BREAKER_OPEN": 18,
}
_SIM_START = datetime.fromisoformat(config.SIM_START_ISO)


# --------------------------------------------------------------------------- #
# Deterministic pseudo-noise
# --------------------------------------------------------------------------- #
def _rand01(*keys) -> float:
    s = f"{config.RANDOM_SEED}|" + "|".join(str(k) for k in keys)
    return int(hashlib.md5(s.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def _noise(amp: float, *keys) -> float:
    return (_rand01(*keys) * 2.0 - 1.0) * amp


def timestamp_for(abs_idx: int) -> datetime:
    return _SIM_START + timedelta(minutes=abs_idx * config.SAMPLE_INTERVAL_MIN)


# --------------------------------------------------------------------------- #
# Fault specification (lives on the LIVE timeline)
# --------------------------------------------------------------------------- #
@dataclass
class FaultSpec:
    scenario_id: str
    asset_id: str
    fault_type: str
    start_sample: int                 # index within the live window
    description: str
    ground_truth_root_cause: str = ""
    resolved_sample: Optional[int] = None   # set by the Actuator when fixed

    def is_active(self, live_idx: int) -> bool:
        if live_idx < self.start_sample:
            return False
        if self.resolved_sample is not None and live_idx >= self.resolved_sample:
            return False
        return True

    def elapsed(self, live_idx: int) -> int:
        return max(0, live_idx - self.start_sample)


# --------------------------------------------------------------------------- #
# Signal source
# --------------------------------------------------------------------------- #
class SignalSource:
    def __init__(self, topo: Topology):
        self.topo = topo

    # -- healthy baselines (per-asset, stable) ------------------------------ #
    def _base_load(self, aid: str) -> float:
        return 55.0 + _rand01(aid, "load_base") * 18.0        # 55-73 %

    def _base_temp(self, aid: str) -> float:
        return 33.0 + _rand01(aid, "temp_base") * 4.0         # 33-37 C

    def _base_thd(self, aid: str) -> float:
        return 2.5 + _rand01(aid, "thd_base") * 1.0           # 2.5-3.5 %

    def _diurnal(self, abs_idx: int, aid: str) -> float:
        """Daily load swing: low at night, peak midday, with a per-asset phase."""
        minutes = abs_idx * config.SAMPLE_INTERVAL_MIN
        tod = (minutes % 1440) / 1440.0                       # 0..1 across a day
        phase = _rand01(aid, "phase") * 0.15                  # small per-asset offset
        return config.DIURNAL_AMPLITUDE * math.sin(2 * math.pi * (tod - 0.25 - phase))

    def _current(self, asset, voltage: float, load_pct: float) -> float:
        if voltage <= 1.0:
            return 0.0
        kw = asset.rated_kw * (load_pct / 100.0)
        return (kw * 1000.0) / (voltage * math.sqrt(3) * 0.95)

    # -- the whole fleet at one sample -------------------------------------- #
    def sample_fleet(self, abs_idx: int, live_idx: int,
                     active: List[FaultSpec]) -> Dict[str, dict]:
        """Return {asset_id: {metrics, codes, primary_code}} for one 5-min sample."""
        by_asset: Dict[str, List[FaultSpec]] = {}
        for f in active:
            by_asset.setdefault(f.asset_id, []).append(f)

        # propagate voltage-type faults downstream
        voltage_drop: Dict[str, float] = {}
        power_cut: Dict[str, bool] = {}
        for f in active:
            affected = [f.asset_id] + self.topo.descendants(f.asset_id)
            if f.fault_type == "VOLTAGE_SAG":
                drop = min(0.18, 0.05 * (f.elapsed(live_idx) + 1))
                for aid in affected:
                    voltage_drop[aid] = max(voltage_drop.get(aid, 0.0), drop)
            elif f.fault_type == "BREAKER_TRIP":
                for aid in affected:
                    power_cut[aid] = True

        out: Dict[str, dict] = {}
        for aid, asset in self.topo.assets.items():
            m = self._healthy(aid, asset, abs_idx)
            for f in by_asset.get(aid, []):
                self._apply_local(m, f, live_idx)

            if aid in power_cut:
                m["voltage_v"] = round(abs(_noise(0.5, aid, abs_idx, "vdead")), 2)
                m["current_a"] = 0.0
                m["load_pct"] = round(abs(_noise(0.4, aid, abs_idx, "ldead")), 2)
            elif aid in voltage_drop:
                m["voltage_v"] = round(m["voltage_v"] * (1.0 - voltage_drop[aid]), 2)

            if asset.type == "BREAKER":
                tripped = any(f.fault_type == "BREAKER_TRIP" for f in by_asset.get(aid, []))
                m["breaker_status"] = 0 if tripped else 1

            codes = self._codes(asset, aid, abs_idx, m,
                                 upstream_cut=(aid in power_cut and asset.type != "BREAKER"))
            primary = max(codes, key=lambda c: _CODE_SEVERITY.get(c, 0)) if codes else config.CODE_OK
            out[aid] = {"metrics": m, "codes": codes, "primary_code": primary}
        return out

    # -- healthy metric vector ---------------------------------------------- #
    def _healthy(self, aid: str, asset, abs_idx: int) -> dict:
        load = self._base_load(aid) + self._diurnal(abs_idx, aid) + _noise(1.6, aid, abs_idx, "load")
        load = max(5.0, load)
        voltage = config.NOMINAL_VOLTAGE + _noise(1.4, aid, abs_idx, "volt")
        temp = self._base_temp(aid) + 0.14 * (load - 60.0) + _noise(0.7, aid, abs_idx, "temp")
        thd = self._base_thd(aid) + _noise(0.3, aid, abs_idx, "thd")
        freq = config.NOMINAL_FREQ + _noise(0.03, aid, abs_idx, "freq")
        m = {
            "voltage_v": round(voltage, 2),
            "current_a": round(self._current(asset, voltage, load), 2),
            "load_pct": round(load, 2),
            "temperature_c": round(temp, 2),
            "thd_pct": round(thd, 2),
            "frequency_hz": round(freq, 3),
        }
        m["battery_soc_pct"] = round(100.0 + _noise(0.4, aid, abs_idx, "soc"), 2) if asset.type == "UPS" else ""
        if asset.type == "BREAKER":
            m["breaker_status"] = 1
        return m

    # -- fault effects (index-based, tuned so detection lands in 1-5 samples) #
    def _apply_local(self, m: dict, f: FaultSpec, live_idx: int) -> None:
        e = f.elapsed(live_idx)
        if f.fault_type == "OVERLOAD":
            m["load_pct"] = round(min(145.0, m["load_pct"] + 12.0 * (e + 1)), 2)
            m["current_a"] = round(m["current_a"] * (m["load_pct"] / 65.0), 2)
            m["temperature_c"] = round(m["temperature_c"] + 1.5 * (e + 1), 2)
        elif f.fault_type == "THERMAL_RUNAWAY":
            m["temperature_c"] = round(min(96.0, m["temperature_c"] + 12.0 * (e + 1)), 2)
        elif f.fault_type == "HARMONIC_DISTORTION":
            m["thd_pct"] = round(min(15.0, m["thd_pct"] + 2.2 * (e + 1)), 2)
        elif f.fault_type == "BATTERY_DEGRADATION" and m.get("battery_soc_pct") != "":
            m["battery_soc_pct"] = round(max(12.0, 100.0 - 8.0 * (e + 1)), 2)

    # -- event/fault codes derived from the metric state -------------------- #
    def _codes(self, asset, aid: str, abs_idx: int, m: dict, upstream_cut: bool) -> List[str]:
        codes: List[str] = []
        v, load = m["voltage_v"], m["load_pct"]
        temp, thd = m["temperature_c"], m["thd_pct"]
        soc = m.get("battery_soc_pct", "")

        if asset.type == "BREAKER" and m.get("breaker_status") == 0:
            codes.append("BREAKER_OPEN")
        if upstream_cut:
            codes.append("LOAD_LOST")

        if v < config.NOMINAL_VOLTAGE * 0.90:
            codes.append("INPUT_UNDERVOLT")
        elif v < config.NOMINAL_VOLTAGE * 0.95:
            codes.append("VOLT_SAG")
        if config.NOMINAL_VOLTAGE * 0.93 < v < config.NOMINAL_VOLTAGE * 0.955:
            codes.append("AVR_ENGAGE")

        if load > 115:
            codes.append("OUTPUT_OVERCURRENT")
        elif load > 100:
            codes.append("OVERLOAD_ALARM")
        elif load > 90:
            codes.append("LOAD_HIGH")

        if temp > 78:
            codes.append("TEMP_CRIT")
        elif temp > 60:
            codes.append("TEMP_WARN")
        if temp > 70:
            codes.append("FAN_FAULT")

        if thd > 9:
            codes.append("WAVEFORM_DISTORT")
        elif thd > 6:
            codes.append("THD_HIGH")

        if soc != "":
            if soc < 55:
                codes.append("SELFTEST_FAIL")
            elif soc < 70:
                codes.append("ON_BATTERY")
            elif soc < 85:
                codes.append("BATT_WEAK")

        # benign periodic codes so the pattern model learns real structure
        if not codes:
            if asset.type == "UPS" and (abs_idx + hash(aid) % config.SELFTEST_PERIOD) % config.SELFTEST_PERIOD == 0:
                codes.append("SELFTEST_PASS")
            elif load > 84 and _rand01(aid, abs_idx, "loadhi") > 0.5:
                codes.append("LOAD_HIGH")
            elif _rand01(aid, abs_idx, "fan") > 0.985:
                codes.append("FAN_OK")
            else:
                codes.append(config.CODE_OK)
        return codes

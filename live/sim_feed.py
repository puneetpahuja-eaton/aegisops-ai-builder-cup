"""A built-in simulated REST feed so live monitoring is demoable without a field device."""
from __future__ import annotations

import datetime
import math
import random


def simulated_reading(step: int, *, inject_anomaly: bool = False) -> dict:
    base_v = 480 + 2 * math.sin(step / 6)
    base_t = 35 + 3 * math.sin(step / 9)
    load = 60 + 8 * math.sin(step / 5) + random.uniform(-2, 2)
    voltage = base_v + random.uniform(-1.5, 1.5)
    temperature = base_t + random.uniform(-0.8, 0.8)
    current = (load / 100) * 1200 + random.uniform(-10, 10)
    codes = ["OK"]
    if inject_anomaly:
        temperature += 18
        current += 300
        codes = ["TEMP_WARN", "OVERLOAD_ALARM"]
    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "metrics": {
            "voltage_v": round(voltage, 2),
            "current_a": round(current, 2),
            "load_pct": round(load, 2),
            "temperature_c": round(temperature, 2),
        },
        "codes": codes,
        "raw": {"simulated": True, "step": step},
    }

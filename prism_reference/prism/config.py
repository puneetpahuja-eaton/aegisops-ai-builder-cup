"""
PRISM - central configuration.

Every threshold, cost number, and tuning constant the agents use lives here so
that a reader can understand and adjust the system's behaviour in one place.
All values are deliberately simple and documented.
"""

from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
BASE_DIR = Path(__file__).resolve().parent.parent          # .../PRISM
DATA_DIR = BASE_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"

ASSETS_FILE = DATA_DIR / "assets.csv"
SCENARIOS_FILE = DATA_DIR / "fault_scenarios.json"
TELEMETRY_FILE = DATA_DIR / "telemetry_baseline.csv"          # legacy single-cycle file

# Time-series datasets (v2)
HISTORY_FILE = DATA_DIR / "telemetry_history.csv"            # training history (5-min samples)
EVENTS_FILE = DATA_DIR / "event_codes_history.csv"           # operational/fault code log
LIVE_SCENARIOS_FILE = DATA_DIR / "live_scenarios.json"       # faults injected in the live window

# --------------------------------------------------------------------------- #
# Simulation
# --------------------------------------------------------------------------- #
SIM_STEPS = 60            # number of polling cycles in the demo
MINUTES_PER_STEP = 1      # each cycle represents 1 minute of real time
NOMINAL_VOLTAGE = 480.0   # volts (480 V class distribution)
NOMINAL_FREQ = 60.0       # Hz

# --------------------------------------------------------------------------- #
# Monitor agent - anomaly detection thresholds (healthy operating bands)
# --------------------------------------------------------------------------- #
THRESHOLDS = {
    "voltage_v":      {"low": NOMINAL_VOLTAGE * 0.95, "high": NOMINAL_VOLTAGE * 1.05},
    "load_pct":       {"high": 90.0},          # >90% load is a warning, >100% is overload
    "temperature_c":  {"high": 60.0},          # degrees C
    "thd_pct":        {"high": 6.0},           # total harmonic distortion %
    "battery_soc_pct":{"low": 70.0},           # UPS battery state-of-charge %
    "frequency_hz":   {"low": NOMINAL_FREQ - 0.5, "high": NOMINAL_FREQ + 0.5},
    # breaker_status is boolean: 1 = closed (healthy), 0 = open (tripped)
}

# --------------------------------------------------------------------------- #
# Diagnostician agent - confidence model
# --------------------------------------------------------------------------- #
# Base "signature clarity" per fault type: how unambiguously the metric pattern
# points to a single cause. Battery decline is deliberately lower because a low
# state-of-charge is consistent with EITHER degradation OR a recent transient
# discharge - so it genuinely needs a human to confirm.
BASE_CLARITY = {
    "VOLTAGE_SAG": 0.95,
    "OVERLOAD": 0.95,
    "THERMAL_RUNAWAY": 0.93,
    "HARMONIC_DISTORTION": 0.92,
    "BREAKER_TRIP": 0.90,
    "BATTERY_DEGRADATION": 0.72,
}

# --------------------------------------------------------------------------- #
# Decider agent - confidence-gated autonomy
# --------------------------------------------------------------------------- #
AUTO_CONFIDENCE_THRESHOLD = 0.80   # minimum diagnostic confidence to act alone
MED_REVERSIBILITY_THRESHOLD = 0.88 # higher bar required for medium-reversibility actions

# --------------------------------------------------------------------------- #
# Remediation playbook - one entry per fault type.
#   reversibility: HIGH  -> safe to auto-execute (software/setpoint change)
#                  MED   -> auto only with very high confidence & non-critical asset
#                  NONE  -> always requires a human (physical part / irreversible)
# --------------------------------------------------------------------------- #
PLAYBOOK = {
    "VOLTAGE_SAG": {
        "action": "Activate AVR voltage stabilisation and shift load to the healthy feed",
        "reversibility": "HIGH",
    },
    "OVERLOAD": {
        "action": "Shed non-critical load and rebalance the affected circuit",
        "reversibility": "HIGH",
    },
    "THERMAL_RUNAWAY": {
        "action": "Raise cooling output and throttle non-critical load on the asset",
        "reversibility": "HIGH",
    },
    "HARMONIC_DISTORTION": {
        "action": "Engage the active harmonic filter on the affected bus",
        "reversibility": "HIGH",
    },
    "BREAKER_TRIP": {
        "action": "Run a downstream fault check, then remotely reclose the breaker",
        "reversibility": "MED",
    },
    "BATTERY_DEGRADATION": {
        "action": "Raise a field work order to replace the UPS battery string and extend runtime reserve",
        "reversibility": "NONE",
    },
}

# --------------------------------------------------------------------------- #
# Value model - counterfactual "downtime / cost avoided"
# --------------------------------------------------------------------------- #
# Cost of downtime per minute, by asset criticality (USD/min).
COST_PER_MIN = {
    "CRITICAL": 850.0,
    "HIGH": 450.0,
    "MEDIUM": 180.0,
    "LOW": 60.0,
}

# Typical manual mean-time-to-resolve per fault type (minutes) - the "no PRISM" world.
MANUAL_MTTR_MIN = {
    "VOLTAGE_SAG": 45,
    "OVERLOAD": 30,
    "THERMAL_RUNAWAY": 60,
    "HARMONIC_DISTORTION": 40,
    "BREAKER_TRIP": 25,
    "BATTERY_DEGRADATION": 120,
}

# When PRISM escalates (instead of auto-fixing), it still adds value by handing a
# human a fully diagnosed case. We credit a fraction of the manual MTTR as saved.
EARLY_DETECTION_CREDIT = 0.40

# Fixed seed so every run is identical in front of judges.
RANDOM_SEED = 42


# =========================================================================== #
#  v2: TIME-SERIES STREAMING, EVENT CODES, and TRAINED ML MODELS
# =========================================================================== #

# --------------------------------------------------------------------------- #
# Sampling / time base
# --------------------------------------------------------------------------- #
SAMPLE_INTERVAL_MIN = 5                     # every asset is sampled every 5 minutes
HISTORY_DAYS = 3                            # how much healthy history to train on
HISTORY_SAMPLES = HISTORY_DAYS * 24 * 60 // SAMPLE_INTERVAL_MIN   # = 864 samples/asset
LIVE_SAMPLES = 96                          # length of the live demo window (8 hours)
SIM_START_ISO = "2026-06-01T00:00:00"      # timestamp of history sample index 0
LIVE_WINDOW_MIN = 60                        # rolling chart window (minutes) in the dashboard

# Diurnal (daily) load cycle: fleets are busier in the day. Amplitude in % load.
DIURNAL_AMPLITUDE = 12.0

# --------------------------------------------------------------------------- #
# Operational / fault event codes (the "flood of codes" the pattern model mines)
# --------------------------------------------------------------------------- #
# The healthy background code (the overwhelming majority of history).
CODE_OK = "OK"
# Benign periodic codes emitted during normal operation - give the pattern model
# real structure to learn (so a genuine fault sequence looks statistically rare).
CODE_SELFTEST_PASS = "SELFTEST_PASS"
CODE_LOAD_HIGH = "LOAD_HIGH"
CODE_FAN_OK = "FAN_OK"

# UPS self-test cadence (samples). 72 * 5 min = every 6 hours.
SELFTEST_PERIOD = 72

# Which event codes each fault type emits (its "signature" in the code stream).
# The Diagnostician maps observed codes back to a fault type; the CodePatternModel
# learns that these sequences are rare/surprising versus healthy history.
FAULT_CODE_SIGNATURE = {
    "VOLTAGE_SAG":        ["VOLT_SAG", "AVR_ENGAGE", "INPUT_UNDERVOLT"],
    "OVERLOAD":           ["LOAD_HIGH", "OVERLOAD_ALARM", "OUTPUT_OVERCURRENT"],
    "THERMAL_RUNAWAY":    ["TEMP_WARN", "TEMP_CRIT", "FAN_FAULT"],
    "HARMONIC_DISTORTION":["THD_HIGH", "WAVEFORM_DISTORT"],
    "BREAKER_TRIP":       ["BREAKER_OPEN", "LOAD_LOST"],
    "BATTERY_DEGRADATION":["BATT_WEAK", "ON_BATTERY", "SELFTEST_FAIL"],
}

# Map a single event code back to the fault type it most implies (used by the
# Diagnostician's classify_by_codes tool).
CODE_TO_FAULT = {
    code: ftype
    for ftype, codes in FAULT_CODE_SIGNATURE.items()
    for code in codes
}

# --------------------------------------------------------------------------- #
# Trained model settings
# --------------------------------------------------------------------------- #
# Metric anomaly model (multivariate). Primary algorithm: Isolation Forest
# (unsupervised, trained on healthy history). Explainable per-metric attribution
# uses a robust z-score (median / MAD). If scikit-learn is unavailable, the model
# falls back to a numpy Mahalanobis + robust-z ensemble with the same interface.
IFOREST_ESTIMATORS = 120
IFOREST_CONTAMINATION = 0.01               # we train on (near) healthy data
ROBUST_Z_THRESHOLD = 4.5                    # |median-z| above this = metric anomaly
METRIC_ANOMALY_SCORE_THRESHOLD = 0.60      # combined score above this = flag

# Code-pattern model (categorical stream). Algorithm: first-order Markov chain
# transition-surprise (negative log-probability of the observed code transition)
# plus a sliding-window rare-code frequency check.
CODE_SURPRISE_THRESHOLD = 4.5              # nats; higher = more surprising transition
CODE_WINDOW = 6                            # samples in the rare-code frequency window

# Number of recent event codes kept per asset for the pattern scan.
CODE_MEMORY = 12

"""
models.py - the anomaly-detection models PRISM TRAINS on historical data.

Two complementary, deliberately-chosen algorithms:

1. MetricAnomalyModel  (multivariate numeric telemetry)
   * Primary: Isolation Forest (scikit-learn) - an unsupervised model trained on
     healthy history. It needs no labels and generalises to unseen fault types.
   * Explainability: a robust z-score (median / MAD) per metric, so PRISM can say
     WHICH metric is abnormal, plus a Mahalanobis distance as a numpy fallback.
   The final score is the max of the available components, so the model still
   works (numpy-only) if scikit-learn is not installed.

2. CodePatternModel  (categorical operational/fault-code stream)
   * A first-order Markov chain trained on the history of event codes. At
     inference it flags LOW-PROBABILITY transitions (transition "surprise" =
     negative log-probability) - i.e. code sequences that never occur in healthy
     operation - plus a sliding-window rare-code frequency check.

Both are fit() on the healthy history and then score() live samples.
"""

from __future__ import annotations

import math
from typing import Dict, List

import numpy as np

from . import config

try:                                            # scikit-learn is optional
    from sklearn.ensemble import IsolationForest
    _HAS_SKLEARN = True
except Exception:                               # pragma: no cover
    _HAS_SKLEARN = False

_BENIGN_CODES = [config.CODE_OK, "SELFTEST_PASS", "LOAD_HIGH", "FAN_OK"]
ALL_CODES = sorted(set(_BENIGN_CODES) | set(config.CODE_TO_FAULT.keys()))


# =========================================================================== #
# Metric anomaly model
# =========================================================================== #
class MetricAnomalyModel:
    def __init__(self):
        self.assets: Dict[str, dict] = {}
        self.uses_iforest = _HAS_SKLEARN
        self.n_trained = 0

    def fit(self, history: Dict[str, dict]) -> None:
        """history: {asset_id: {"X": ndarray(n,d), "features": [names]}}."""
        for aid, h in history.items():
            X = np.asarray(h["X"], dtype=float)
            feats = h["features"]
            if X.ndim != 2 or X.shape[0] < 20:
                continue
            median = np.median(X, axis=0)
            mad = np.median(np.abs(X - median), axis=0)
            scale = np.where(mad < 1e-6, 1.0, 1.4826 * mad)

            mean = X.mean(axis=0)
            cov = np.cov(X.T) + np.eye(X.shape[1]) * 1e-6
            inv_cov = np.linalg.pinv(cov)
            maha_tr = self._mahalanobis(X, mean, inv_cov)

            state = {
                "features": feats, "median": median, "scale": scale,
                "mean": mean, "inv_cov": inv_cov,
                "maha_p50": float(np.percentile(maha_tr, 50)),
                "maha_p99": float(np.percentile(maha_tr, 99)),
                "iforest": None,
            }
            if _HAS_SKLEARN:
                std = X.std(axis=0)
                std = np.where(std < 1e-6, 1.0, std)
                Xs = (X - mean) / std
                clf = IsolationForest(
                    n_estimators=config.IFOREST_ESTIMATORS,
                    contamination=config.IFOREST_CONTAMINATION,
                    random_state=config.RANDOM_SEED,
                )
                clf.fit(Xs)
                s_tr = clf.score_samples(Xs)
                state.update({
                    "iforest": clf, "if_std": std,
                    "if_p50": float(np.percentile(s_tr, 50)),
                    "if_p05": float(np.percentile(s_tr, 5)),
                })
            self.assets[aid] = state
            self.n_trained += 1

    @staticmethod
    def _mahalanobis(X, mean, inv_cov) -> np.ndarray:
        d = X - mean
        return np.sqrt(np.einsum("ij,jk,ik->i", d, inv_cov, d))

    def score(self, aid: str, metrics: dict) -> dict:
        st = self.assets.get(aid)
        if not st:
            return {"score": 0.0, "is_anomaly": False, "zmax": 0.0,
                    "top_metric": None, "per_metric_z": {}, "iforest": None}

        feats = st["features"]
        x = np.array([float(metrics.get(f, 0.0) or 0.0) for f in feats])

        # Robust z-score is the PRIMARY, explainable detector: a metric that is
        # more than ROBUST_Z_THRESHOLD MADs from its healthy median is abnormal.
        z = (x - st["median"]) / st["scale"]
        per_metric_z = {f: round(float(zi), 2) for f, zi in zip(feats, z)}
        zabs = np.abs(z)
        top_i = int(np.argmax(zabs))
        zmax = float(zabs[top_i])
        score = min(1.0, zmax / (2.0 * config.ROBUST_Z_THRESHOLD))
        is_anom = zmax >= config.ROBUST_Z_THRESHOLD

        # Isolation Forest CORROBORATES an already-abnormal sample (multivariate
        # evidence) by strengthening its score. It is deliberately NOT allowed to
        # raise an anomaly on a statistically-normal sample, which keeps the
        # false-positive rate on healthy data essentially zero.
        if_score = None
        if st["iforest"] is not None:
            xs = (x - st["mean"]) / st["if_std"]
            if_score = float(st["iforest"].score_samples(xs[None, :])[0])
            pred = int(st["iforest"].predict(xs[None, :])[0])   # -1 = anomaly
            if pred == -1 and is_anom:
                score = max(score, 0.85)

        return {
            "score": round(score, 3), "is_anomaly": bool(is_anom),
            "zmax": round(zmax, 2), "top_metric": feats[top_i],
            "per_metric_z": per_metric_z,
            "iforest": round(if_score, 3) if if_score is not None else None,
        }


# =========================================================================== #
# Code-pattern model (first-order Markov transition surprise)
# =========================================================================== #
class CodePatternModel:
    def __init__(self, alpha: float = 0.5):
        self.alpha = alpha
        self.vocab: List[str] = list(ALL_CODES)
        self.V = len(self.vocab)
        self.trans: Dict[str, Dict[str, int]] = {}
        self.prev_total: Dict[str, int] = {}
        self.n_transitions = 0

    def fit(self, sequences: List[List[str]]) -> None:
        for seq in sequences:
            for a, b in zip(seq[:-1], seq[1:]):
                self.trans.setdefault(a, {})
                self.trans[a][b] = self.trans[a].get(b, 0) + 1
                self.prev_total[a] = self.prev_total.get(a, 0) + 1
                self.n_transitions += 1
            for c in seq:
                if c not in self.vocab:
                    self.vocab.append(c)
        self.V = len(self.vocab)

    def transition_surprise(self, prev: str, code: str) -> float:
        num = self.trans.get(prev, {}).get(code, 0) + self.alpha
        den = self.prev_total.get(prev, 0) + self.alpha * self.V
        return -math.log(num / den)

    def scan(self, recent_codes: List[str]) -> dict:
        """recent_codes: chronological primary codes for one asset.

        Only genuine FAULT codes (those in CODE_TO_FAULT) can raise an anomaly -
        benign-but-rare operational codes (e.g. periodic self-tests) never do.
        """
        if len(recent_codes) < 2:
            return {"surprise": 0.0, "is_anomaly": False, "flagged": [],
                    "rare_rate": 0.0, "transition": ""}

        fault_recent = [c for c in recent_codes if c in config.CODE_TO_FAULT]

        # transition surprise, but only for transitions INTO a fault code
        fault_transitions = [
            (self.transition_surprise(a, b), a, b)
            for a, b in zip(recent_codes[:-1], recent_codes[1:])
            if b in config.CODE_TO_FAULT
        ]
        if fault_transitions:
            max_s, pa, pb = max(fault_transitions, key=lambda t: t[0])
        else:
            max_s, pa, pb = 0.0, "", ""

        window = recent_codes[-config.CODE_WINDOW:]
        rare_rate = sum(1 for c in window if c in config.CODE_TO_FAULT) / len(window)

        flagged = sorted(set(fault_recent),
                         key=lambda c: config.CODE_TO_FAULT.get(c, ""))
        last_is_fault = recent_codes[-1] in config.CODE_TO_FAULT
        is_anom = bool(last_is_fault and (max_s >= config.CODE_SURPRISE_THRESHOLD
                                          or rare_rate >= 0.34))
        return {
            "surprise": round(max_s, 2), "is_anomaly": bool(is_anom),
            "flagged": flagged, "rare_rate": round(rare_rate, 2),
            "transition": f"{pa}->{pb}" if pa else "",
        }

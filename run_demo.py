"""End-to-end CLI: one incident -> evidence -> grounded diagnosis.

    python run_demo.py
"""
from __future__ import annotations

import json
from pathlib import Path

from diagnostician import diagnose
from evidence import build_evidence
from gemini_client import is_live

HERE = Path(__file__).parent


def main() -> None:
    incident = json.loads((HERE / "data" / "sample_incident.json").read_text())
    sop_text = (HERE / "data" / "sop.md").read_text()

    evidence = build_evidence(incident)
    diagnosis = diagnose(evidence, sop_text)

    print("=== Kairos AI — Grounded Industrial Reliability Co-pilot ===")
    print(f"Gemini live: {is_live()}  (source: {diagnosis.get('_source')})\n")
    print("-- Evidence (deterministic) --")
    for s in evidence["signals"]:
        flag = "  <== ANOMALY" if s["anomalous"] else ""
        print(f"  {s['metric']}: {s['latest']}{s['unit']}  z={s['robust_z']}{flag}")
    print(f"  event codes: {evidence['event_codes']}\n")
    print("-- Diagnosis (Gemini, grounded) --")
    print(f"  root cause : {diagnosis['root_cause']}")
    print(f"  confidence : {diagnosis['confidence']}")
    print(f"  cited SOP  : {diagnosis['cited_sop_ids']}")
    print(f"  action     : {diagnosis['recommended_action']}")
    print(f"  escalate   : {diagnosis['escalate']}")
    print(f"  reasoning  : {diagnosis['reasoning']}")


if __name__ == "__main__":
    main()

"""Verify live cloud data, Gemini, approval, and BigQuery without printing secrets."""
import argparse
import json
from pathlib import Path

import bq
from orchestrator import approve_simulation, load_scenarios, load_sop, run_case


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--audit", action="store_true")
    args = parser.parse_args()
    incidents = load_scenarios()
    cases = [run_case(incident, load_sop()) for incident in (incidents if args.all else incidents[:1])]
    for case in cases:
        print(json.dumps({
            "asset": case["evidence"]["asset_id"], "source": case["diagnosis"]["_source"],
            "decision": case["decision"]["action"], "seconds": case["elapsed_seconds"],
            "errors": case["errors"],
        }))
        if case["errors"] or not case["diagnosis"]["_source"].startswith("gemini:"):
            raise RuntimeError("Live Google AI verification failed.")
        if case["decision"]["requires_approval"]:
            approve_simulation(case, "Cloud smoke-test reviewer")
    if args.audit:
        print(f"BigQuery accepted rows: {bq.log_cases(cases)}")
        print(f"BigQuery history rows: {len(bq.recent_history())}")
    target = Path(__file__).resolve().parents[1] / "submission" / "live_results.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(cases, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

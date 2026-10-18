"""Earlier Kairos AI workflow retained for regression and comparison."""
from __future__ import annotations

import json
import logging

import streamlit as st
from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import GoogleAuthError
from pydantic import ValidationError

import bq
import storage
from gemini_client import backend, is_live
from models import Incident
from orchestrator import approve_simulation, load_scenarios, load_sop, run_case

st.set_page_config(page_title="Kairos AI | Industrial reliability", page_icon="⚙️", layout="wide")
logging.basicConfig(level=logging.INFO)
CLOUD_ERRORS = (GoogleAPICallError, GoogleAuthError, RuntimeError, ValueError, TimeoutError)


def persist(case: dict) -> None:
    if not bq.is_enabled():
        return
    key = f"{case['case_id']}:{case['approval']['approved']}"
    written = st.session_state.setdefault("audit_written", set())
    if key in written:
        return
    try:
        bq.log_cases([case])
        written.add(key)
    except CLOUD_ERRORS as error:
        st.error(f"Audit persistence failed. The result is not saved: {error}")


def render_case(case: dict) -> None:
    evidence, diagnosis = case["evidence"], case["diagnosis"]
    st.subheader(f"{evidence['asset_id']} | {evidence['asset_type']}")
    metrics = st.columns(4)
    metrics[0].metric("Criticality", evidence["asset_criticality"])
    metrics[1].metric("Model self-confidence", f"{diagnosis['confidence']:.2f}")
    metrics[2].metric("Analysis time", f"{case['elapsed_seconds']:.1f}s")
    metrics[3].metric("Verification", case["verification"]["status"].replace("_", " "))
    st.caption(f"Source: {diagnosis['_source']} | Mode: {case['mode']} | Case: {case['case_id']}")
    for error in case["errors"]:
        st.error(error)
    if case["errors"] and st.button("Retry this incident", key=f"retry-{case['case_id']}"):
        with st.spinner(f"Retrying {evidence['asset_id']}..."):
            replacement = run_case(
                case["incident"], load_sop(),
                offline=case["mode"] == "offline simulation",
            )
        st.session_state["cases"] = [
            replacement if item["case_id"] == case["case_id"] else item
            for item in st.session_state["cases"]
        ]
        st.rerun()
    with st.expander("1. Monitor | deterministic telemetry evidence"):
        st.write("Event codes:", evidence["event_codes"])
        st.dataframe(evidence["signals"], hide_index=True, width="stretch")
        st.caption("Robust-z detects deviation, not failure probability. Constant baselines use a disclosed 1% scale floor.")
    with st.expander("2. Diagnostician | grounded hypothesis", expanded=True):
        st.markdown(f"**Hypothesis:** {diagnosis['root_cause']}")
        st.write(diagnosis["reasoning"])
        for identifier, quote in diagnosis["citation_quotes"].items():
            st.info(f'{identifier}: "{quote}"')
        st.caption(diagnosis.get("_citation_check", "No accepted citations."))
        st.write("Recommendation:", diagnosis["recommended_action"])
    with st.expander("3. Decider | deterministic review gate", expanded=True):
        st.write("Decision:", case["decision"]["action"])
        for reason in case["decision"]["reasons"]:
            st.write("- " + reason)
        if case["decision"]["requires_approval"] and not case["approval"]["approved"]:
            reviewer = st.text_input("Reviewer name (demo alias allowed)", key=f"reviewer-{case['case_id']}")
            if st.button("Approve sandbox simulation", key=f"approve-{case['case_id']}"):
                try:
                    approve_simulation(case, reviewer)
                except ValueError as error:
                    st.error(str(error))
                else:
                    persist(case)
                    st.rerun()
        if case["approval"]["approved"]:
            st.success(f"Sandbox approved by {case['approval']['reviewer']}. No real equipment action.")
    with st.expander("4. Actuator | review-only output"):
        action = case["action"]
        st.write("Status:", action["status"])
        if action["type"] == "work_order":
            order = action["work_order"]
            st.markdown(f"**{order['priority']} | {order['title']}**")
            st.write(order["summary"])
            st.write("Review steps:", order["steps"])
            st.warning(" ".join(order["safety_notes"]))
            st.caption(f"Work order source: {order['_source']} | Draft only, not dispatched.")
        else:
            st.write(action["summary"])
    with st.expander("5. Verifier | explicit post-action evidence"):
        st.write(case["verification"])
    with st.expander("Business case assumptions (not measured savings)"):
        st.write(case["value"]["assumptions"])
        st.write(case["value"]["basis"])
        st.metric("Illustrative opportunity", f"${case['value']['potential_usd']:,}")
        st.caption("Realized savings: $0 measured. Opportunity is only shown after synthetic recovery.")
    persist(case)
    st.divider()


def main() -> None:
    st.title("Kairos AI")
    st.caption("Evidence -> grounded hypothesis -> human review -> sandbox action -> verification")
    st.warning("Hackathon sandbox: fictional SOPs; built-in telemetry is synthetic, uploads are chronological replay. No real equipment control or measured savings.")
    with st.sidebar:
        st.header("Run configuration")
        offline = st.toggle("Explicit offline simulation", value=not is_live())
        st.write("Selected reasoning:", "offline rules (not Google AI)" if offline else backend())
        st.write("Documents:", storage.backend())
        st.write("Audit history:", "BigQuery" if bq.is_enabled() else "session only")
        st.caption("Gemini is only marked successful after a validated response. Cloud errors are never replaced silently.")
        workspace = st.radio("Workspace", ["Fleet operations", "Single incident"], key="workspace")
    try:
        sop = load_sop()
        scenarios = load_scenarios() if workspace == "Single incident" else []
    except (GoogleAPICallError, GoogleAuthError, ValueError, OSError) as error:
        st.error(f"Data loading failed. Check storage configuration: {error}")
        return
    if workspace == "Fleet operations":
        from fleet_ui import render_fleet
        render_fleet(sop, offline=offline)
        return
    names = [incident["asset"]["id"] for incident in scenarios]
    selection = st.multiselect("Synthetic incidents", names, default=names[:1])
    uploaded = st.file_uploader("Optional synthetic incident JSON (no confidential data)", type=["json"])
    if uploaded:
        try:
            if uploaded.size > 100_000:
                raise ValueError("Incident JSON must be under 100 KB.")
            incident = Incident.model_validate_json(uploaded.getvalue()).model_dump()
            scenarios = [incident]
            selection = [incident["asset"]["id"]]
            st.info("Uploaded incident replaces the selected demo fleet for this run.")
        except (ValidationError, ValueError) as error:
            st.error(f"Invalid incident: {error}")
            return
    if st.button("Run reliability loop", type="primary", disabled=not selection):
        cases = []
        chosen = [incident for incident in scenarios if incident["asset"]["id"] in selection]
        progress = st.progress(0)
        for index, incident in enumerate(chosen):
            with st.spinner(f"Analyzing {incident['asset']['id']}..."):
                cases.append(run_case(incident, sop, offline=offline))
            progress.progress((index + 1) / len(chosen))
        progress.empty()
        st.session_state["cases"] = cases
    cases = st.session_state.get("cases", [])
    if cases:
        cols = st.columns(4)
        cols[0].metric("Incidents", len(cases))
        cols[1].metric("Accepted Gemini diagnoses", sum(c["diagnosis"]["_source"].startswith("gemini:") for c in cases))
        cols[2].metric("Engineer escalations", sum(c["decision"]["action"] == "escalate" for c in cases))
        cols[3].metric("Human-approved simulations", sum(c["approval"]["approved"] for c in cases))
        for case in cases:
            render_case(case)
        st.download_button("Download audit JSON", json.dumps(cases, indent=2), file_name="kairos-audit.json", mime="application/json")
        orders = [c["action"]["work_order"] for c in cases if c["action"]["type"] == "work_order"]
        st.download_button("Download work orders", json.dumps(orders, indent=2), file_name="work-orders.json", mime="application/json")
    else:
        st.info("Select an incident and run the loop. Try MTR-07 for supervisor approval or PMP-03 for engineer escalation.")
    with st.expander("Reference playbook"):
        st.markdown(sop)
    if bq.is_enabled():
        with st.expander("Operational audit history | BigQuery", expanded="audit_history" in st.session_state):
            if st.button("Refresh audit history"):
                try:
                    st.session_state["audit_history"] = bq.recent_history()
                except CLOUD_ERRORS as error:
                    st.error(f"History query failed: {error}")
                else:
                    st.rerun()
            if "audit_history" in st.session_state:
                st.dataframe(st.session_state["audit_history"], hide_index=True, width="stretch")
    st.caption("Cloud-enabled architecture: Cloud Run + Gemini on Vertex AI + Cloud Storage + BigQuery. Active backends are shown in the sidebar.")


if __name__ == "__main__":
    main()

"""Fleet inputs and incrementally rendered, session-isolated operational replay."""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st
from google.api_core.exceptions import GoogleAPICallError
from google.auth.exceptions import GoogleAuthError

import bq
from fleet_data import csv_template, demo_dataset, load_bundle, load_csv
from fleet_runtime import FleetEngine
from power_demo import POWER_SCENARIOS, power_demo_dataset


@st.cache_data(show_spinner=False)
def _power_demo_json() -> str:
    return power_demo_dataset().model_dump_json()


def _save(engine: FleetEngine) -> None:
    if not bq.is_enabled():
        st.error("BigQuery is not configured; download the session audit instead.")
        return
    rows = [{**case, "audit_revision": len(engine.trace) * 2 + int(case["approval"]["approved"])} for case in engine.cases]
    if not rows:
        st.info("No cases to save yet.")
        return
    try:
        bq.log_cases(rows)
    except (GoogleAPICallError, GoogleAuthError, RuntimeError, ValueError, TimeoutError) as error:
        st.session_state["fleet_audit_notice"] = (engine.run_id, False, f"Audit persistence failed; this snapshot was not confirmed saved: {error}")
    else:
        st.session_state["fleet_audit_notice"] = (engine.run_id, True, f"Saved {len(rows)} case summaries to BigQuery. Full tool traces remain in the downloadable session audit.")


def _advance(engine: FleetEngine) -> None:
    live = st.empty()
    def event(update: dict) -> None:
        with live.container():
            st.info(f"Tick {update['tick'] + 1} | {update['agent']} | {update['tool']}")
            st.json(update["result"], expanded=False)
    with st.spinner("Processing the next fleet timestamp; actual tool events appear below..."):
        engine.tick(on_event=event)
    live.empty()


def operations() -> None:
    engine: FleetEngine | None = st.session_state.get("fleet_engine")
    if engine is None:
        st.info("Load demo data or upload your replacement telemetry to begin.")
        return
    st.subheader(f"Fleet replay | {engine.data.source}")
    st.caption(
        "Processing updates are real; timestamps are replayed data, not a live factory connection. "
        "Five cooperating agents share this session's observations, code memory, cases and tool trace."
    )
    if st.session_state.get("fleet_playing") and not engine.at_end:
        _advance(engine)
        if engine.at_end or any(case["status"] in {"AWAITING_APPROVAL", "ERROR"} for case in engine.cases):
            st.session_state["fleet_playing"] = False
            st.rerun()
    controls = st.columns(3)
    if controls[0].button("Process next timestamp", disabled=engine.at_end, key="fleet_step"):
        st.session_state["fleet_playing"] = False
        _advance(engine)
        st.rerun()
    if controls[1].button("Pause replay" if st.session_state.get("fleet_playing") else "Play replay",
                          disabled=engine.at_end, key="fleet_play"):
        st.session_state["fleet_playing"] = not st.session_state.get("fleet_playing", False)
        st.rerun()
    if controls[2].button("Reset this replay", key="fleet_reset"):
        st.session_state["fleet_engine"] = FleetEngine(engine.data, engine.sop, offline=engine.offline,
                                                     evaluation_scenarios=engine.evaluation_scenarios)
        st.session_state["fleet_playing"] = False
        st.rerun()
    st.progress(engine.cursor / len(engine.frames), text=f"{engine.cursor}/{len(engine.frames)} timestamps processed")
    if engine.at_end:
        st.info("Replay complete. Unapproved or escalated cases are not resolved. Reset to replay again.")
    columns = st.columns(4)
    columns[0].metric("Fleet assets", len(engine.assets))
    columns[1].metric("Tracked cases", len(engine.cases))
    columns[2].metric("Verified recoveries", sum(case["status"] == "RESOLVED" for case in engine.cases))
    columns[3].metric("Observable tool calls", len(engine.trace))
    tabs = st.tabs(["Live operations", "Cases & approvals", "Topology & models", "Counterfactual", "Agent trace & audit"])
    with tabs[0]:
        if engine.latest:
            st.dataframe([{
                "asset_id": key, "anomaly_score": value["metrics"]["score"],
                "codes": " | ".join(value["reading"].event_codes),
                "metric_anomaly": value["metrics"]["is_anomaly"],
                "Markov_surprise": value["codes"]["transition_surprise"],
                "unknown_codes": ", ".join(value["codes"]["unknown_codes"]),
            } for key, value in engine.latest.items()], hide_index=True, width="stretch")
        asset_id = st.selectbox("Asset chart", list(engine.assets), key=f"chart-{engine.run_id}")
        metric = st.selectbox("Metric chart", engine.detectors.states[asset_id]["features"], key=f"metric-{engine.run_id}")
        if engine.samples:
            frame = pd.DataFrame(engine.samples)
            series = frame[frame.asset_id == asset_id].set_index("timestamp")[[metric]]
            st.line_chart(series)
            scores = pd.DataFrame(engine.score_history)
            st.line_chart(scores[scores.asset_id == asset_id].set_index("timestamp")[["anomaly_score"]])
        st.caption("Robust-z >= 3 flags deviation. Isolation Forest corroborates it; Mahalanobis is diagnostic only. "
                   "Metric-only cases require two consecutive anomalous samples for the same metric; fault/unknown "
                   "codes open cases immediately. Event transition surprise is not a calibrated failure probability.")
    with tabs[1]:
        if not engine.cases:
            st.info("No cases opened. Process timestamps to observe detection.")
        for case in engine.cases:
            with st.expander(f"{case['root_asset_id']} | {case['category']} | {case['status']}", expanded=True):
                st.write("Root candidate:", case["root_asset_id"], "| Correlated symptoms:", case["symptom_asset_ids"])
                st.write("Hypothesis:", case["diagnosis"]["root_cause"])
                st.caption(f"Diagnosis source: {case['diagnosis']['_source']} | Case {case['case_id']}")
                st.write(case["diagnosis"]["reasoning"])
                for identifier, quote in case["diagnosis"]["citation_quotes"].items():
                    st.info(f'{identifier}: "{quote}"')
                st.write("Safety gate:", case["decision"]["reasons"])
                for error in case["errors"]:
                    st.error(error)
                if case["status"] == "ERROR" and st.button("Retry fleet diagnosis", key=f"fleet-retry-{case['case_id']}"):
                    live_retry = st.empty()
                    engine.retry(case["case_id"], on_event=lambda event: live_retry.info(f"{event['agent']} | {event['tool']}"))
                    st.rerun()
                st.json({"action": case["action"], "verification": case["verification"]}, expanded=False)
                if case["status"] == "AWAITING_APPROVAL":
                    reviewer = st.text_input("Fleet reviewer name", key=f"fleet-reviewer-{case['case_id']}")
                    if st.button("Approve fleet sandbox", key=f"fleet-approve-{case['case_id']}", disabled=engine.at_end):
                        try:
                            engine.approve(case["case_id"], reviewer)
                        except ValueError as error:
                            st.error(str(error))
                        else:
                            st.rerun()
                if case["approval"]["approved"]:
                    st.success(f"Sandbox approved by {case['approval']['reviewer']}. No real equipment action.")
        st.caption("Uploaded measurements cannot be altered. Two consecutive healthy later snapshots are required "
                   "within three verification ticks. Failure or recurrence requires engineer review.")
    with tabs[2]:
        st.dataframe([asset.model_dump() for asset in engine.data.assets], hide_index=True, width="stretch")
        # Use stable internal graph IDs: uploaded labels cannot inject DOT structure.
        identifiers = {key: f"n{index}" for index, key in enumerate(engine.assets)}
        nodes = [f"{identifiers[key]} [label={json.dumps(key)}];" for key in engine.assets]
        edges = [f"{identifiers[asset.parent_id]} -> {identifiers[asset.id]};"
                 for asset in engine.data.assets if asset.parent_id]
        st.graphviz_chart("digraph fleet { " + " ".join(nodes + edges) + " }")
        st.dataframe(engine.training_report(), hide_index=True, width="stretch")
        st.caption("Training is frozen before replay; there is no future-data leakage or online retraining. "
                   "History must be known healthy. Constant metrics use a 1% median scale floor (minimum 0.01).")
    with tabs[3]:
        if engine.evaluation_scenarios:
            st.dataframe(engine.evaluation(), hide_index=True, width="stretch")
            st.caption("Post-hoc comparison against built-in synthetic scenario labels. Ground truth is not sent to agents "
                       "or used to choose a repair. These are not production diagnostic-accuracy results.")
        opportunity = sum(case["value"]["potential_usd"] for case in engine.cases)
        st.metric("Illustrative synthetic opportunity", f"${opportunity:,.0f}")
        st.metric("Measured production savings", "$0")
        st.warning("Not realized savings or validated prediction. Estimates apply only to verified built-in synthetic scenarios.")
        st.dataframe([{"asset_id": asset.id, "assumed_manual_mttr_minutes": asset.assumed_manual_mttr_minutes,
                       "assumed_cost_per_minute": asset.downtime_cost_per_minute} for asset in engine.data.assets],
                     hide_index=True, width="stretch")
        if engine.samples and engine.data.source == "synthetic":
            frame = pd.DataFrame(engine.samples)
            if metric in frame.columns and f"original_{metric}" in frame.columns:
                comparison = frame[frame.asset_id == asset_id].set_index("timestamp")
                st.line_chart(comparison[[metric, f"original_{metric}"]])
                st.caption("Selected metric: unchanged fault timeline versus approved synthetic intervention. "
                           "No physical counterfactual has been measured.")
    with tabs[4]:
        st.dataframe([{key: value for key, value in event.items() if key != "result"} for event in engine.trace[-100:]],
                     hide_index=True, width="stretch")
        with st.expander("Inspect tool results (observable evidence, not private model reasoning)"):
            selected_event = st.selectbox("Tool event", ["Latest", *[str(event["sequence"]) for event in engine.trace]],
                                          key=f"trace-{engine.run_id}")
            st.json(engine.trace[-1] if selected_event == "Latest" else engine.trace[int(selected_event) - 1])
        st.download_button("Download fleet audit JSON", json.dumps(engine.audit(), default=str, indent=2),
                           "aegisops-fleet-audit.json", "application/json")
        if engine.data.source == "uploaded":
            consent = st.checkbox("I authorize saving these uploaded case summaries to this project's BigQuery audit.",
                                  key=f"save-consent-{engine.run_id}")
        else:
            consent = True
        if st.button("Save fleet case summaries to BigQuery", disabled=not consent):
            _save(engine)
        notice = st.session_state.get("fleet_audit_notice")
        if notice and notice[0] == engine.run_id:
            (st.success if notice[1] else st.error)(notice[2])
        st.caption("Uploaded rows stay in this browser session's server memory unless you explicitly send them to "
                   "Vertex AI or save case summaries. Nothing is committed to the public repository. "
                   "The full tool trace is available in the audit download; BigQuery stores case summaries.")


def render_fleet(sop: str, *, offline: bool) -> None:
    st.header("Fleet operations")
    st.write("Replace the built-in data with a JSON fleet bundle or a single CSV containing your assets, "
             "healthy history and replay telemetry. A successful load replaces the entire previous fleet.")
    with st.expander("Telemetry inputs, templates and privacy", expanded=True):
        demo = demo_dataset()
        st.download_button("Download fleet CSV template", csv_template(demo), "fleet-template.csv", "text/csv")
        st.download_button("Download fleet JSON template", demo.model_dump_json(indent=2), "fleet-template.json", "application/json")
        st.caption("CSV metadata: timestamp (timezone required), asset_id, phase (history/replay), asset_type, "
                   "criticality, parent_id, event_codes (pipe-separated), followed by numeric metric columns. "
                   "At least 20 known-healthy readings per asset; complete fleet snapshots in replay. "
                   "Max 50 assets / 2 MB. Templates are synthetic, not your factory's data.")
        upload = st.file_uploader("Replacement fleet telemetry (CSV or JSON; no confidential data)", type=["csv", "json"], key="fleet_upload")
        authorize = st.checkbox("I am authorized to send this non-confidential uploaded telemetry to Google Vertex AI.",
                                key="fleet_vertex_consent")
        if st.button("Load replacement telemetry", disabled=upload is None):
            try:
                if upload.size > 2_000_000:
                    raise ValueError("Fleet uploads must be under 2 MB.")
                if not offline and not authorize:
                    raise ValueError("Authorize Google AI processing or select explicit offline simulation before loading.")
                text = upload.getvalue().decode("utf-8-sig")
                data = load_csv(text) if upload.name.lower().endswith(".csv") else load_bundle(text)
                with st.spinner("Validating topology and training historical models..."):
                    engine = FleetEngine(data, sop, offline=offline)
            except (ValueError, UnicodeDecodeError) as error:
                st.error(f"Replacement rejected; existing replay is unchanged: {error}")
            else:
                st.session_state["fleet_engine"] = engine
                st.session_state["fleet_playing"] = False
                st.success("Replacement loaded. The demo fleet is no longer used in this replay.")
        if st.button("Load built-in synthetic fleet", type="primary"):
            with st.spinner("Training per-asset models on known-healthy synthetic history..."):
                st.session_state["fleet_engine"] = FleetEngine(demo, sop, offline=offline)
            st.session_state["fleet_playing"] = False
        if st.button("Load PRISM-style power fleet (22 assets / 6 scenarios)"):
            with st.spinner("Generating three days of healthy power history and fitting 22 per-asset models..."):
                from fleet_data import FleetDataset
                data = FleetDataset.model_validate_json(_power_demo_json())
                st.session_state["fleet_engine"] = FleetEngine(data, sop, offline=offline, evaluation_scenarios=POWER_SCENARIOS)
            st.session_state["fleet_playing"] = False
        with st.expander("Power scenario schedule (synthetic ground truth, not model input)"):
            st.dataframe(POWER_SCENARIOS, hide_index=True, width="stretch")
    engine = st.session_state.get("fleet_engine")
    if engine and engine.offline != offline:
        st.warning("Reasoning mode changed. Load/reset from the inputs above to apply it; the existing replay retains its original mode.")
    cadence = st.select_slider("Replay cadence (seconds per data timestamp)", options=[0.5, 1.0, 2.0, 3.0, 5.0],
                               value=2.0, key="fleet_cadence")
    # Paused sessions must not continually rerender charts or erase feedback.
    st.fragment(run_every=cadence if st.session_state.get("fleet_playing") else None)(operations)()

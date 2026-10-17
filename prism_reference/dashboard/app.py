"""
PRISM dashboard - real-time, self-explanatory Streamlit app (v2).

A reviewer can open this with no briefing and:
  * press PLAY and watch a live 5-minute-sampled telemetry stream,
  * see the trained models score every asset in real time,
  * watch the five agents detect, diagnose, decide, act and verify - with their
    tool-calls and reasoning shown live,
  * and read the business value (downtime / cost avoided) accrue.

Launch (from the PRISM folder):  python run.py
or directly:                     streamlit run dashboard/app.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from prism import config
from prism_cloud import Engine
import prism_extensions as cloud

st.set_page_config(page_title="PRISM - Autonomous Power Reliability", layout="wide")

LEVEL_COLORS = {
    "info": "#FFFFFF", "warn": "#FFF3CD", "action": "#D1E7DD",
    "success": "#C9F2D4", "escalate": "#F8D7DA",
}
CELL_TEXT_COLOR = "#111111"          # dark text so pastel rows stay legible


# --------------------------------------------------------------------------- #
# Build the engine ONCE per session (it trains the models on startup).
# --------------------------------------------------------------------------- #
if "engine" not in st.session_state:
    with st.spinner("Training anomaly models on 3 days of historical telemetry..."):
        try:
            st.session_state.engine = cloud.create_engine()
        except cloud.CLOUD_ERRORS as error:
            st.error(f"PRISM startup failed; check the configured data source: {error}")
            st.stop()
    st.session_state.playing = False
    st.session_state.speed = 1.0

engine: Engine = st.session_state.engine


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def latest_score(aid: str) -> float:
    h = engine.score_hist.get(aid)
    return h[-1] if h else 0.0


def active_roots() -> set:
    return {c.root_asset_id for c in engine.cases
            if c.status in ("OPEN", "ACTING", "ESCALATED", "FAILED")}


def fleet_frame() -> pd.DataFrame:
    idx = engine.current_idx
    snap = engine.history.get(idx, {})
    roots = active_roots()
    rows = []
    for aid in engine.topo.all_ids():
        a = engine.topo.get(aid)
        m = snap.get(aid, {}).get("metrics", {})
        code = snap.get(aid, {}).get("primary_code", "-")
        sc = latest_score(aid)
        if aid in roots:
            state = "FAULT (root)"
        elif sc >= 0.5:
            state = "Anomalous"
        else:
            state = "Healthy"
        rows.append({
            "Asset": aid, "Type": a.type, "Crit": a.criticality, "State": state,
            "Score": round(sc, 2), "Code": code,
            "Volt": m.get("voltage_v", ""), "Load%": m.get("load_pct", ""),
            "Temp": m.get("temperature_c", ""),
        })
    return pd.DataFrame(rows)


def color_state(val):
    if "FAULT" in str(val):
        return f"background-color: #F8D7DA; color: {CELL_TEXT_COLOR}"
    if val == "Anomalous":
        return f"background-color: #FFF3CD; color: {CELL_TEXT_COLOR}"
    if val == "Healthy":
        return f"background-color: #D1E7DD; color: {CELL_TEXT_COLOR}"
    return ""


# --------------------------------------------------------------------------- #
# Sidebar - branding, agents, live controls, training report
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.title("PRISM")
    st.caption("Power Reliability Intelligence & Self-healing Management")
    st.markdown("An **agentic workflow**: five specialised agents run a live "
                "closed loop over a fleet of power assets.")
    st.markdown(
        "1. **Monitor** - trained models score telemetry + event codes\n"
        "2. **Diagnostician** - root cause via the power topology\n"
        "3. **Decider** - confidence-gated autonomy (act vs escalate)\n"
        "4. **Actuator** - execute the fix / raise a work order\n"
        "5. **Verifier** - confirm the fix (closes the loop)"
    )
    st.divider()
    st.subheader("Live controls")
    b1, b2, b3 = st.columns(3)
    if b1.button("Play", width="stretch", disabled=engine.at_end):
        st.session_state.playing = True
    if b2.button("Pause", width="stretch"):
        st.session_state.playing = False
    if b3.button("Reset", width="stretch"):
        engine.reset()
        st.session_state.playing = False
        st.rerun()
    if st.button("Step once", width="stretch", disabled=engine.at_end):
        cloud.tick(engine)
    speed_label = st.select_slider("Speed (seconds per 5-min sample)",
                                   options=["0.4", "0.7", "1.0", "1.5"], value="0.7")
    st.session_state.speed = float(speed_label)

    st.divider()
    tr = engine.train_report
    with st.expander("Trained models", expanded=True, key="prism_training_panel"):
        st.markdown(
            f"**Trained on** {tr['history_samples']:,} samples/asset "
            f"({tr['history_days']} days @ {tr['sample_interval_min']}-min).\n\n"
            f"**Metric anomaly:** {', '.join(tr['metric_algorithms'])}.\n\n"
            f"**Event codes:** {tr['code_algorithm']} "
            f"({tr['code_transitions_learned']:,} transitions, "
            f"{tr['code_vocabulary']} codes)."
        )

cloud.sidebar(engine)

# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.title("PRISM - Autonomous Power-Fault Detection, Diagnosis & Self-Healing")
st.markdown(
    "A multi-agent system that keeps power infrastructure online by "
    "**detecting, root-causing, fixing and verifying** faults on its own - "
    "escalating to a human, with full evidence, only when judgement is required."
)
st.caption("Synthetic simulator only: automatic actions do not control equipment. "
           "Downtime/cost fields are original PRISM counterfactual estimates, not measured savings. "
           "Uploaded data is observation-only; SOPs are fictional.")

tabs = st.tabs(["Live Operations", "Cases", "Counterfactual (value)",
                "Power Topology", "Models & Data", "How it works"], key="prism_tabs", on_change="rerun")

# Auto-rerun cadence: only while playing and not finished.
_run_every = st.session_state.speed if (st.session_state.playing and not engine.at_end) else None


@st.fragment(run_every=_run_every)
def live_ops():
    eng: Engine = st.session_state.engine
    if st.session_state.playing and not eng.at_end:
        cloud.tick(eng)
        if eng.at_end:                       # stop the loop cleanly at the end
            st.session_state.playing = False
            st.rerun()

    idx = eng.current_idx
    ts = eng.timestamp(idx).strftime("%Y-%m-%d %H:%M") if idx >= 0 else "--"
    status = ("STREAMING" if st.session_state.playing else
              ("COMPLETE" if eng.at_end else "PAUSED"))
    st.caption(f"**{status}**  |  sample {max(idx,0)+ (0 if idx<0 else 1)}/{eng.total_samples}"
               f"  |  simulated time {ts}")
    st.progress((idx + 1) / eng.total_samples)

    s = eng.summary()
    k = st.columns(6)
    k[0].metric("Cases", s["total_cases"])
    k[1].metric("Auto-resolved", s["auto_resolved"])
    k[2].metric("Escalated", s["escalated"])
    k[3].metric("Diagnosis acc.", f"{s['diagnosis_accuracy']*100:.0f}%" if s["diagnosis_accuracy"] is not None else "n/a")
    k[4].metric("Downtime avoided", f"{s['downtime_avoided_min']:.0f} min")
    k[5].metric("Cost avoided", f"${s['cost_avoided_usd']:,.0f}")

    left, right = st.columns([1.15, 1])

    with left:
        st.markdown("**Live telemetry & anomaly score**")
        a_ids = eng.topo.all_ids()
        default_ai = a_ids.index("UPS-3") if "UPS-3" in a_ids else 0
        ca, cm = st.columns(2)
        aid = ca.selectbox("Asset", a_ids, index=default_ai, key="live_asset")
        original_metrics = ["voltage_v", "load_pct", "temperature_c", "thd_pct", "battery_soc_pct"]
        metric_options = original_metrics if eng.source == "synthetic" else sorted(eng.metric_model.assets[aid]["features"])
        metric = cm.selectbox("Metric", metric_options, key="live_metric")
        xs, ys = eng.asset_series(aid, metric)
        if xs:
            st.line_chart(pd.DataFrame({metric: ys}, index=xs), height=180)
        else:
            st.info("Press Play to start the telemetry stream.")

        sh = eng.score_hist.get(aid, [])
        if sh:
            sdf = pd.DataFrame({"anomaly score": sh,
                                "alert threshold": [0.5] * len(sh)})
            st.line_chart(sdf, height=160)
            st.caption("Anomaly score = Isolation Forest + robust-z (0-1). "
                       "Above 0.5 (>=4.5 sigma) raises an alert.")

        st.markdown("**Fleet status**")
        df = fleet_frame()
        st.dataframe(df.style.map(color_state, subset=["State"]),
                     width="stretch", height=300, hide_index=True)

    with right:
        st.markdown("**Agent reasoning trace (live)**")
        entries = eng.log[-16:]
        if entries:
            tdf = pd.DataFrame([{"t": e.step, "Agent": e.agent, "Case": e.case_id,
                                 "Detail": e.message} for e in entries])
            levels = [e.level for e in entries]

            def _row_color(row):
                c = LEVEL_COLORS.get(levels[row.name], "#FFFFFF")
                return [f"background-color: {c}; color: {CELL_TEXT_COLOR}"] * len(row)

            st.dataframe(tdf.style.apply(_row_color, axis=1),
                         width="stretch", height=250, hide_index=True)
        else:
            st.info("No agent activity yet.")

        st.markdown("**Agent tool-calls (live)**")
        tcs = eng.tool_calls[-10:]
        if tcs:
            st.dataframe(pd.DataFrame([{"t": t.step, "Agent": t.agent, "Tool": t.tool,
                                        "Result": t.result} for t in tcs]),
                         width="stretch", height=180, hide_index=True)

        st.markdown("**Event-code stream**")
        evs = eng.events[-10:]
        if evs:
            st.dataframe(pd.DataFrame([{"t": e["idx"], "Asset": e["asset"],
                                        "Code": e["code"]} for e in reversed(evs)]),
                         width="stretch", height=160, hide_index=True)
        else:
            st.caption("Only OK codes so far.")


with tabs[0]:
    live_ops()

# --------------------------------------------------------------------------- #
# Tab 2 - Cases
# --------------------------------------------------------------------------- #
with tabs[1]:
    st.subheader("Incident cases")
    if not engine.cases:
        st.info("No cases yet. Start the stream on the Live Operations tab.")
    for c in engine.cases:
        badge = {"RESOLVED": "Auto-resolved", "ACTING": "Remediation in progress",
                 "ESCALATED": "Escalated to human", "FAILED": "Auto-fix failed - escalated",
                 "OPEN": "Diagnosed - awaiting action"}.get(c.status, c.status)
        a = engine.topo.get(c.root_asset_id)
        with st.expander(f"{c.case_id}  -  {c.fault_type} @ {c.root_asset_id} "
                         f"({a.name})  -  {badge}", key=f"prism-case-{engine.run_id}-{c.case_id}"):
            cc = st.columns(4)
            cc[0].metric("Confidence", f"{c.confidence:.2f}")
            cc[1].metric("Decision", (c.decision or "-").replace("_", " "))
            cc[2].metric("Downtime avoided", f"{c.downtime_avoided_min:.0f} min")
            cc[3].metric("Cost avoided", f"${c.cost_avoided_usd:,.0f}")
            ob = c.observations[0] if c.observations else None
            if ob:
                st.markdown(f"**Model evidence:** score {ob.model_score:.2f}, "
                            f"z={ob.zmax:.1f} on `{ob.metric}`, "
                            f"codes [{'/'.join(ob.codes) or 'none'}], "
                            f"code-surprise {ob.code_surprise:.1f}")
            st.markdown(f"**Diagnosis correct vs ground truth:** "
                        f"{'Yes' if c.diagnosis_correct else 'n/a'}")
            if c.symptom_asset_ids:
                st.markdown(f"**Downstream symptoms eliminated "
                            f"({len(c.symptom_asset_ids)}):** {', '.join(c.symptom_asset_ids)}")
            st.markdown(f"**Planned action:** {c.action}  _(reversibility: {c.reversibility})_")
            st.markdown(f"**Decision rationale:** {c.decision_reason}")
            cloud.case_panel(engine, c)
    cloud.audit_panel(engine)

# --------------------------------------------------------------------------- #
# Tab 3 - Counterfactual
# --------------------------------------------------------------------------- #
with tabs[2]:
    st.subheader("PRISM vs. 'No PRISM' - the value, visualised")
    st.caption("Blue = what actually happened (PRISM intervened). Orange = the same "
               "fault left unattended. The gap is the downtime and cost avoided.")
    st.caption("Synthetic what-if comparison and assumed value only; no measured production savings. "
               "For uploaded telemetry both series are unchanged observations, not an intervention counterfactual.")
    if engine.current_idx < 0:
        st.info("Start the stream first.")
    else:
        c1, c2 = st.columns(2)
        a_ids = engine.topo.all_ids()
        asset_id = c1.selectbox("Asset", a_ids,
                                index=a_ids.index("XFMR-1") if "XFMR-1" in a_ids else 0, key="cf_asset")
        cf_options = (["voltage_v", "temperature_c", "load_pct", "thd_pct", "battery_soc_pct"]
                      if engine.source == "synthetic" else sorted(engine.metric_model.assets[asset_id]["features"]))
        metric = c2.selectbox("Metric", cf_options, key="cf_metric")
        xs, live_ys = engine.asset_series(asset_id, metric)
        base_ys = engine.baseline_series(asset_id, metric)
        if xs:
            df = pd.DataFrame({"PRISM (live)": live_ys,
                               "No PRISM (baseline)": base_ys[:len(xs)]}, index=xs)
            if df.notna().any().any():
                st.line_chart(df)
            else:
                st.info("This asset does not report the selected metric.")
        else:
            st.info("No data yet.")

# --------------------------------------------------------------------------- #
# Tab 4 - Topology
# --------------------------------------------------------------------------- #
with tabs[3]:
    st.subheader("Power chain (causal graph)")
    st.caption("PRISM uses this physical topology to tell a root cause apart from the "
               "downstream symptoms it produces. Red = active root, amber = anomalous, "
               "green = healthy.")
    roots = active_roots()
    lines = ["digraph G { rankdir=LR; node [style=filled, shape=box, fontname=Helvetica];"]
    for aid in engine.topo.all_ids():
        a = engine.topo.get(aid)
        if aid in roots:
            fill = "#F8B4BC"
        elif latest_score(aid) >= 0.5:
            fill = "#FFE08A"
        else:
            fill = "#B7E4C7"
        import json
        lines.append(f'{json.dumps(aid)} [label={json.dumps(aid + chr(10) + a.type)}, fillcolor="{fill}"];')
        if a.parent_id:
            lines.append(f'{json.dumps(a.parent_id)} -> {json.dumps(aid)};')
    lines.append("}")
    st.graphviz_chart("\n".join(lines), width="stretch")

# --------------------------------------------------------------------------- #
# Tab 5 - Models & Data
# --------------------------------------------------------------------------- #
with tabs[4]:
    st.subheader("The trained models and the data behind them")
    tr = engine.train_report
    c1, c2, c3 = st.columns(3)
    c1.metric("History per asset", f"{tr['history_samples']:,} samples")
    c2.metric("Assets modelled", tr["assets_modelled"])
    c3.metric("Code transitions learned", f"{tr['code_transitions_learned']:,}")
    st.markdown(
        f"""
**1. Metric anomaly model (multivariate telemetry).**
Algorithms: {', '.join(tr['metric_algorithms'])}.
Each asset gets its own model, trained on {tr['history_days']} days of healthy,
diurnally-varying history sampled every {tr['sample_interval_min']} minutes. A
metric more than {config.ROBUST_Z_THRESHOLD} robust-sigma (median/MAD) from normal
raises an alert; the Isolation Forest corroborates it with multivariate evidence.

**2. Event-code pattern model (categorical stream).**
Algorithm: {tr['code_algorithm']}. It learned {tr['code_transitions_learned']:,}
code transitions over a {tr['code_vocabulary']}-code vocabulary. A rare transition
into a fault code (e.g. `OK -> BATT_WEAK -> ON_BATTERY`) is flagged as surprising.

**Fictitious datasets** (in `data/`, regenerate with `python generate_data.py`):
- `telemetry_history.csv` - the healthy training time-series.
- `event_codes_history.csv` - the operational/fault event-code log.
- `assets.csv`, `live_scenarios.json` - the fleet topology and injected faults.
        """
    )
    cloud.data_panel(engine)

# --------------------------------------------------------------------------- #
# Tab 6 - How it works
# --------------------------------------------------------------------------- #
with tabs[5]:
    st.subheader("How PRISM works")
    st.markdown(
        """
**PRISM is a real agentic workflow, not a chatbot or a set of static thresholds.**
Every 5-minute sample it runs five specialised agents over a shared **blackboard**,
and each agent invokes **tools** (shown live on the Live Operations tab):

| Step | Agent | Tools it calls |
|---|---|---|
| 1. Detect | **Monitor** | `score_metric_model` (Isolation Forest + robust-z), `scan_code_patterns` (Markov surprise) |
| 2. Diagnose | **Diagnostician** | `classify_fault` (codes -> fault), `walk_topology` (eliminate downstream symptoms) |
| 3. Decide | **Decider** | `lookup_playbook` (action + reversibility), then confidence-gated autonomy |
| 4. Act | **Actuator** | `execute_remediation` or `raise_work_order` |
| 5. Verify | **Verifier** | `recheck_asset` (re-score with the model) - closes the loop |

**Trained, not hard-coded.** The Monitor's thresholds are *learned* from historical
data, so PRISM adapts to each asset's normal behaviour instead of relying on fixed limits.

**Root cause, not alarm storms.** A single upstream fault makes many downstream
assets look unhealthy. PRISM walks the causal graph to eliminate the symptoms and
reports one root cause with the symptoms attached.

**Safe autonomy.** The Decider gates on diagnostic confidence, action reversibility
and asset criticality. Physical/irreversible fixes are escalated to a human, pre-diagnosed.

**Provable value.** Every closed case is scored against the typical manual
time-to-resolve, multiplied by a per-minute cost that scales with asset criticality.

See `docs/` for the full write-up.
        """
    )
    st.caption("Google Cloud edition: Vertex AI adds cited hypotheses and review-only work-order drafts; "
               "Cloud Storage supplies the original topology/scenarios and SOP; BigQuery stores audit revisions; "
               "Cloud Run hosts this dashboard. Original PRISM numerical confidence is heuristic, not calibrated. "
               "The simulator's original policy is preserved; real actuation is not implemented.")

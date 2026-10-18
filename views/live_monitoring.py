"""Engineer/Admin: live REST monitoring with real-time agentic analysis."""
from __future__ import annotations

import pandas as pd
import streamlit as st

import datastore
import devices
import monitor_gen
import rag
import secretmgr
import ui_common
from live import rest_adapter, sim_feed
from live.inference import suggest_field_map
from live.monitor import LiveMonitor


def _plan_builder(device: dict) -> None:
    """Chat-style generator that turns an instruction into a monitoring config."""
    device_id = device["id"]
    with st.expander("🧰 Build monitoring from an instruction (agent)"):
        st.caption("Describe what to monitor in plain language. The agent reads this device's docs to "
                   "resolve parameter IDs, polling interval, thresholds and the event-log decode. It asks "
                   "clarifying questions first — especially about how the event log is structured.")
        request = st.text_area("What should I monitor?", key=f"mp_req_{device_id}", height=90,
                               placeholder="Monitor per-phase voltages and currents every 5 minutes, and "
                                           "read the fault/event log; alarm if voltage leaves 210-250 V.")
        ref_path = st.text_input("Reference a repo file for parameters (optional path)",
                                 key=f"mp_ref_{device_id}",
                                 placeholder="source/Tools/Database/DCI Descriptors.json")
        cols = st.columns(3)
        if cols[0].button("❓ Ask clarifying questions", key=f"mp_ask_{device_id}", disabled=not request.strip()):
            with st.spinner("Reading docs and thinking..."):
                try:
                    reference = _plan_reference(device_id, ref_path)
                    st.session_state[f"mp_q_{device_id}"] = monitor_gen.clarifying_questions(
                        device_id, request, reference)
                except Exception as error:  # noqa: BLE001
                    st.error(str(error))
        if st.session_state.get(f"mp_q_{device_id}"):
            st.markdown("**Clarifying questions:**")
            st.markdown(st.session_state[f"mp_q_{device_id}"])
            st.text_area("Your answers (optional)", key=f"mp_ans_{device_id}", height=80)
        if cols[1].button("🧰 Generate plan", type="primary", key=f"mp_gen_{device_id}",
                          disabled=not request.strip()):
            with st.spinner("Resolving parameters and building the plan..."):
                try:
                    reference = _plan_reference(device_id, ref_path)
                    plan = monitor_gen.generate_plan(device_id, request, reference,
                                                     st.session_state.get(f"mp_ans_{device_id}", ""))
                except Exception as error:  # noqa: BLE001
                    st.error(f"Plan generation failed: {error}")
                else:
                    st.session_state[f"mp_plan_{device_id}"] = plan
        plan = st.session_state.get(f"mp_plan_{device_id}")
        if plan:
            st.success(f"Plan: {len(plan.get('params', []))} parameter(s), "
                       f"interval {plan.get('poll_interval_s')}s"
                       + (", event log decode included" if plan.get("event_log") else ""))
            st.dataframe([{"pid": p["pid"], "label": p.get("label", ""), "lower": p.get("lower"),
                           "upper": p.get("upper"), "unit": p.get("unit", "")}
                          for p in plan.get("params", [])], hide_index=True, width="stretch")
            if plan.get("event_log"):
                st.markdown("**Event log decode:**")
                st.json(plan["event_log"])
            if plan.get("notes"):
                st.caption(plan["notes"])
            current = _load_config(device_id)
            default_ep = current.get("endpoint") or "https://10.130.178.92/rs/param/22120/value"
            endpoint = st.text_input("Base REST endpoint for these params", value=default_ep,
                                     key=f"mp_ep_{device_id}")
            if st.button("➕ Apply to Live Monitoring", key=f"mp_apply_{device_id}"):
                cfg = _load_config(device_id)
                cfg.update(monitor_gen.plan_to_config(plan, endpoint))
                cfg["simulated"] = False
                _save_config(device_id, cfg)
                st.success("Applied. The parameters, interval and event-log decode are now set below. "
                           "Add auth/TLS, Save connection, and Start.")
                st.rerun()


def _plan_reference(device_id: str, ref_path: str) -> str:
    if not ref_path.strip():
        return ""
    import knowledge
    return knowledge.fetch_repo_file_text(device_id, ref_path.strip())["text"]



def _config_key(device_id: str) -> str:
    return f"live_cfg_{device_id}"


def _load_config(device_id: str) -> dict:
    stored = datastore.get_doc(devices.live_path(device_id), "config") or {}
    return stored


def _save_config(device_id: str, config: dict) -> None:
    datastore.set_doc(devices.live_path(device_id), "config", config)


def _monitored_list(config: dict) -> list[dict]:
    """Return the list of monitored params, migrating any legacy param_ids/thresholds."""
    monitored = [dict(item) for item in (config.get("monitored") or [])]
    if monitored:
        return monitored
    thresholds = config.get("thresholds") or {}
    for pid in config.get("param_ids") or []:
        limits = thresholds.get(f"p{pid}", {}) or {}
        monitored.append({"pid": str(pid), "lower": limits.get("lower"),
                          "upper": limits.get("upper"), "label": limits.get("label", "")})
    return monitored


def _persist_monitored(device_id: str, monitored: list[dict]) -> None:
    config = _load_config(device_id)
    config["monitored"] = monitored
    config["param_ids"] = [m["pid"] for m in monitored]
    config["thresholds"] = {
        f"p{m['pid']}": {k: v for k, v in
                         {"lower": m.get("lower"), "upper": m.get("upper"), "label": m.get("label")}.items()
                         if v not in (None, "")}
        for m in monitored if m.get("lower") is not None or m.get("upper") is not None or m.get("label")}
    _save_config(device_id, config)

def _render_config(device: dict) -> dict:
    device_id = device["id"]
    config = _load_config(device_id)
    st.subheader("Connection")
    if device["protocol"] != "rest":
        st.warning(f"This device's protocol is `{device['protocol']}`. Modbus and DLMS are **disabled** "
                   "in this edition — only REST polling is available.")

    simulated = st.toggle("Use built-in simulated feed (no device needed)",
                          value=config.get("simulated", True),
                          help="Great for the demo. Turn off to poll a real REST endpoint.")
    endpoint = st.text_input("REST endpoint (base — the param ID in the path is the template)",
                             value=config.get("endpoint", ""), disabled=simulated,
                             placeholder="https://10.130.178.92/rs/param/22120/value")
    hex_as_float = st.selectbox(
        "Hex value format", ["IEEE-754 float (32-bit)", "Unsigned integer"],
        index=0 if config.get("hex_as_float", True) else 1, disabled=simulated,
        help="How to decode 0x.. hex words. Eaton meter params are IEEE-754 floats.") == "IEEE-754 float (32-bit)"

    # Monitored parameters: a clean inline table (add rows, edit, delete) — no cluttered buttons.
    monitored = _monitored_list(config)
    if not simulated:
        st.markdown("**Monitored parameters**")
        st.caption("Add a row per parameter: ID, optional lower/upper limits, a label, and (optional) the "
                   "JSON path to its value if the response structure differs. A value below the lower or "
                   "above the upper limit raises an issue with a grounded description. Use the + row to add "
                   "and the 🗑 to remove.")
        table = pd.DataFrame(
            [{"Parameter ID": m["pid"], "Lower": m.get("lower"), "Upper": m.get("upper"),
              "Label": m.get("label", ""), "Value path": m.get("path", "")} for m in monitored],
            columns=["Parameter ID", "Lower", "Upper", "Label", "Value path"])
        edited = st.data_editor(
            table, num_rows="dynamic", hide_index=True, width="stretch", key=f"params_table_{device_id}",
            column_config={
                "Parameter ID": st.column_config.TextColumn("Parameter ID", required=True, width="small"),
                "Lower": st.column_config.NumberColumn("Lower", format="%.4f", width="small"),
                "Upper": st.column_config.NumberColumn("Upper", format="%.4f", width="small"),
                "Label": st.column_config.TextColumn("Label", width="medium"),
                "Value path": st.column_config.TextColumn("Value path (optional)", width="small",
                                                          help="Default: value. Override if a param's "
                                                               "response nests the value differently."),
            })
        new_monitored: list[dict] = []
        seen: set[str] = set()
        for _, record in edited.iterrows():
            pid = str(record["Parameter ID"]).strip() if pd.notna(record["Parameter ID"]) else ""
            if not pid or pid in seen:
                continue
            seen.add(pid)
            new_monitored.append({
                "pid": pid,
                "lower": float(record["Lower"]) if pd.notna(record["Lower"]) else None,
                "upper": float(record["Upper"]) if pd.notna(record["Upper"]) else None,
                "label": str(record["Label"]).strip() if pd.notna(record["Label"]) else "",
                "path": str(record["Value path"]).strip() if pd.notna(record["Value path"]) else "",
            })
        if new_monitored != monitored:
            _persist_monitored(device_id, new_monitored)
        monitored = new_monitored
        if monitored:
            st.caption(f"Monitoring **{len(monitored)}** parameter(s) — each tracked and charted separately.")
        else:
            st.info("No parameters added yet. Add at least one row above.")

    param_ids = [m["pid"] for m in monitored]
    thresholds = {f"p{m['pid']}": {k: v for k, v in
                                   {"lower": m.get("lower"), "upper": m.get("upper"),
                                    "label": m.get("label")}.items() if v not in (None, "")}
                  for m in monitored if m.get("lower") is not None or m.get("upper") is not None or m.get("label")}

    col1, col2, col3 = st.columns(3)
    auth_modes = ["none", "basic", "digest", "bearer"]
    auth_mode = col1.selectbox("Auth", auth_modes,
                               index=auth_modes.index(config.get("auth_mode", "none"))
                               if config.get("auth_mode", "none") in auth_modes else 0,
                               disabled=simulated,
                               help="Many embedded meter web servers use Digest auth, not Basic.")
    username = col2.text_input("Username", disabled=simulated or auth_mode not in ("basic", "digest"))
    password = col3.text_input("Password / token", type="password",
                               disabled=simulated or auth_mode == "none")
    interval = st.number_input("Poll interval (seconds)", min_value=1, max_value=86400,
                               value=int(config.get("interval", 10)), step=1, disabled=simulated,
                               help="How often to poll each parameter. Any value from 1 second upward.")

    with st.expander("🔒 TLS / certificate (for HTTPS field devices)"):
        st.caption("On-prem devices often use a self-signed or private-CA certificate. Prefer pinning the "
                   "device's CA certificate. Skipping verification is an explicit opt-in for a trusted "
                   "private-network device only.")
        ca_pem = st.text_area("Device CA certificate (PEM, optional)", value="", height=100,
                              disabled=simulated, placeholder="-----BEGIN CERTIFICATE-----\n...")
        verify_tls = not st.checkbox(
            "Skip TLS verification (insecure — private-network device only)",
            value=not config.get("verify_tls", True), disabled=simulated,
            help="Equivalent to curl -k. Only use for a device you trust on an internal network.")
        if not verify_tls:
            st.warning("TLS verification is OFF for this device. Use only on a trusted private network.")

    field_map = config.get("field_map", {})
    with st.expander("🤖 Advanced: agent field mapping (for non-/rs/param endpoints)"):
        st.caption("Optional. For a generic endpoint, paste a sample response and let the agent map fields "
                   "from the datasheet. Not needed for /rs/param devices — their values are auto-extracted.")
        sample = st.text_area("Sample response JSON", value=config.get("sample", ""), height=100,
                              disabled=simulated)
        if st.button("Ask agent to map fields", disabled=not sample.strip()):
            with st.spinner("Agent inferring field mapping from the datasheet..."):
                try:
                    suggestion = suggest_field_map(device_id, sample)
                except Exception as error:  # noqa: BLE001
                    st.error(str(error))
                else:
                    field_map = suggestion.get("field_map", {})
                    config["event_path"] = suggestion.get("event_path", "")
                    st.success("Agent proposed a field mapping.")
                    if suggestion.get("rationale"):
                        st.caption(suggestion["rationale"])
        if field_map:
            st.write("Field map (metric → JSON path):", field_map)

    if st.button("💾 Save connection"):
        secret_ref = config.get("secret_ref") or f"live_{device_id}"
        cred_saved = False
        if not simulated and auth_mode != "none" and password:
            value = f"{username}:{password}" if auth_mode in ("basic", "digest") else password
            secretmgr.put_secret(secret_ref, value)
            cred_saved = True
        ca_ref = config.get("ca_cert_ref") or f"live_ca_{device_id}"
        if not simulated and ca_pem.strip():
            secretmgr.put_secret(ca_ref, ca_pem.strip())
        config.update({"simulated": simulated, "endpoint": endpoint, "auth_mode": auth_mode,
                       "interval": interval, "field_map": field_map, "sample": sample,
                       "secret_ref": secret_ref, "verify_tls": verify_tls, "param_ids": param_ids,
                       "hex_as_float": hex_as_float, "thresholds": thresholds, "monitored": monitored,
                       "ca_cert_ref": ca_ref if (ca_pem.strip() or config.get("ca_cert_ref")) else None})
        _save_config(device_id, config)
        if not simulated and auth_mode != "none" and not cred_saved and not secretmgr.get_secret(secret_ref):
            st.warning("Saved, but no credentials are stored yet. Enter username/password and save again.")
        else:
            st.success("Saved connection configuration.")
    config["interval"] = interval
    config["simulated"] = simulated
    config["verify_tls"] = verify_tls
    config["param_ids"] = param_ids
    config["endpoint"] = endpoint
    config["hex_as_float"] = hex_as_float
    config["thresholds"] = thresholds
    config["monitored"] = monitored
    return config


def _poll(device: dict, config: dict) -> dict:
    if config.get("simulated", True):
        state = st.session_state
        step_key = f"live_step_{device['id']}"
        state[step_key] = state.get(step_key, 0) + 1
        step = state[step_key]
        # Inject an anomaly burst periodically so the demo shows detection + resolution.
        return sim_feed.simulated_reading(step, inject_anomaly=(step % 12 in (0, 1)))
    return rest_adapter.poll("rest", config)


def render() -> None:
    ui_common.require_role("engineer")
    st.title("📡 Live Monitoring")
    st.caption("Agent polls the device over REST at a configurable interval and analyzes in real time.")

    device = ui_common.device_selector("live_device")
    if not device:
        return
    device_id = device["id"]

    _plan_builder(device)

    with st.expander("⚙️ Configure connection", expanded=not _load_config(device_id)):
        config = _render_config(device)

    mon_key = f"live_monitor_{device_id}"
    hist_key = f"live_hist_{device_id}"
    on_key = f"live_on_{device_id}"
    st.session_state.setdefault(on_key, False)

    col1, col2, col3 = st.columns(3)
    if col1.button("▶ Start", type="primary", disabled=st.session_state[on_key]):
        st.session_state[mon_key] = LiveMonitor(criticality=device["criticality"],
                                                thresholds=config.get("thresholds") or {})
        st.session_state[hist_key] = []
        st.session_state[f"live_step_{device_id}"] = 0
        st.session_state[on_key] = True
        st.rerun()
    if col2.button("⏸ Stop", disabled=not st.session_state[on_key]):
        st.session_state[on_key] = False
        st.rerun()
    if col3.button("🔄 Reset"):
        for key in (mon_key, hist_key, on_key):
            st.session_state.pop(key, None)
        st.rerun()

    interval = int(config.get("interval", 3))
    placeholder = st.container()

    @st.fragment(run_every=interval if st.session_state[on_key] else None)
    def live_panel() -> None:
        monitor: LiveMonitor = st.session_state.get(mon_key)
        if monitor is None:
            return
        if st.session_state.get(on_key):
            try:
                reading = _poll(device, config)
            except Exception as error:  # noqa: BLE001
                st.error(f"Poll failed: {error}")
                st.session_state[on_key] = False
                return
            new_issues = monitor.observe(reading)
            # Enrich newly raised issues with a grounded description (once each).
            for issue in new_issues:
                try:
                    issue["description"] = rag.describe_issue(
                        device_id, param=issue.get("label") or issue["metric"], value=issue["value"],
                        reason=issue.get("reason", "anomaly"), lower=issue.get("lower"),
                        upper=issue.get("upper"))
                except Exception as error:  # noqa: BLE001
                    issue["description"] = f"(description unavailable: {error})"
            st.session_state[hist_key].append({"timestamp": reading["timestamp"], **reading["metrics"]})
            st.session_state[hist_key] = st.session_state[hist_key][-120:]
            st.session_state[f"live_lastraw_{device_id}"] = reading.get("raw")
            st.session_state[f"live_lastmetrics_{device_id}"] = reading.get("metrics")

        summary = monitor.summary()
        metric_cols = st.columns(5)
        metric_cols[0].metric("Readings", summary["readings"])
        metric_cols[1].metric("Issues", summary["issues"])
        metric_cols[2].metric("Auto-resolved", summary["auto_resolved"])
        metric_cols[3].metric("Escalated", summary["escalated"])
        metric_cols[4].metric("Cost avoided (est.)", f"${summary['cost_avoided_usd']:,.0f}")
        st.caption(f"Downtime avoided (estimated): {summary['downtime_avoided_min']} min · "
                   "estimates only, not measured savings.")

        history = st.session_state.get(hist_key, [])
        last_metrics = st.session_state.get(f"live_lastmetrics_{device_id}")
        if last_metrics is not None and not config.get("simulated", True) and not last_metrics:
            st.warning("The device responded but no numeric value was found. Expand the raw response "
                       "below, or set the value path for that parameter.")
        if history:
            frame = pd.DataFrame(history).set_index("timestamp")
            columns = [c for c in frame.columns if c != "timestamp"]
            if config.get("simulated", True):
                if columns:
                    st.line_chart(frame[columns])
            else:
                # One chart per parameter so different PIDs are never clubbed together.
                labels = {f"p{m['pid']}": (m.get("label") or f"p{m['pid']}")
                          for m in (config.get("monitored") or [])}
                groups: dict[str, list[str]] = {}
                for col in columns:
                    base = col.split(".", 1)[0]  # p<id> (multi-word words grouped with their param)
                    groups.setdefault(base, []).append(col)
                for base, cols in groups.items():
                    title = labels.get(base, base)
                    st.markdown(f"**{title}** (`{base}`)")
                    series = frame[cols].dropna(how="all")
                    latest = series[cols[0]].dropna()
                    if not latest.empty:
                        st.caption(f"latest: {latest.iloc[-1]:g}")
                    if len(series):
                        st.line_chart(series)
        if monitor.issues:
            st.subheader("Detected issues")
            _badge = {"ESCALATED": "🔴", "MONITORING": "🟠", "RESOLVED": "🟢"}
            for issue in reversed(monitor.issues):
                badge = _badge.get(issue["status"], "⚪")
                with st.container(border=True):
                    top = st.columns([3, 2, 2, 2])
                    top[0].markdown(f"{badge} **{issue.get('label', issue['metric'])}**")
                    top[1].write(f"value: {issue['value']}")
                    top[2].write(f"{issue['status']}")
                    top[3].write(f"{issue['decision']}")
                    st.caption(f"{issue.get('reason', '')}"
                               + (f" · est. cost avoided ${issue['cost_avoided_usd']:,.0f}"
                                  if issue.get("cost_avoided_usd") else ""))
                    if issue.get("description"):
                        st.write(issue["description"])
        raw = st.session_state.get(f"live_lastraw_{device_id}")
        if raw is not None and not config.get("simulated", True):
            with st.expander("🔎 Latest raw device response"):
                st.json(raw)

    with placeholder:
        live_panel()

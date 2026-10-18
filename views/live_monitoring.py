"""Engineer/Admin: live REST monitoring with real-time agentic analysis."""
from __future__ import annotations

import re

import pandas as pd
import streamlit as st

import datastore
import devices
import rag
import secretmgr
import ui_common
from live import rest_adapter, sim_feed
from live.inference import suggest_field_map
from live.monitor import LiveMonitor


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

    # Monitored parameters: add one at a time (ID, lower, upper, label), listed below.
    monitored = _monitored_list(config)
    if not simulated:
        st.markdown("**Monitored parameters**")
        st.caption("Add a parameter ID with optional lower/upper limits and a label. A value below the "
                   "lower or above the upper limit raises an issue with a grounded description.")
        head = st.columns([2, 2, 2, 3, 1])
        for col, title in zip(head, ["Parameter ID", "Lower", "Upper", "Label", ""]):
            col.caption(title)
        for index, item in enumerate(monitored):
            row = st.columns([2, 2, 2, 3, 1])
            row[0].write(f"p{item['pid']}")
            row[1].write("—" if item.get("lower") is None else f"{item['lower']:g}")
            row[2].write("—" if item.get("upper") is None else f"{item['upper']:g}")
            row[3].write(item.get("label") or "—")
            if row[4].button("Remove", key=f"rm_param_{device_id}_{item['pid']}"):
                monitored = [m for m in monitored if m["pid"] != item["pid"]]
                _persist_monitored(device_id, monitored)
                st.rerun()
        add = st.columns([2, 2, 2, 3, 1])
        new_pid = add[0].text_input("Parameter ID", key=f"newpid_{device_id}", label_visibility="collapsed",
                                    placeholder="22120")
        new_lower = add[1].number_input("Lower", key=f"newlo_{device_id}", value=None, step=1.0,
                                        format="%.4f", label_visibility="collapsed")
        new_upper = add[2].number_input("Upper", key=f"newhi_{device_id}", value=None, step=1.0,
                                        format="%.4f", label_visibility="collapsed")
        new_label = add[3].text_input("Label", key=f"newlbl_{device_id}", label_visibility="collapsed",
                                      placeholder="e.g. Phase A voltage")
        if add[4].button("➕ Add", key=f"addparam_{device_id}"):
            pid = (new_pid or "").strip()
            if not pid:
                st.warning("Enter a parameter ID to add.")
            elif any(m["pid"] == pid for m in monitored):
                st.warning(f"Parameter {pid} is already monitored.")
            else:
                monitored.append({"pid": pid,
                                  "lower": float(new_lower) if new_lower is not None else None,
                                  "upper": float(new_upper) if new_upper is not None else None,
                                  "label": (new_label or "").strip()})
                _persist_monitored(device_id, monitored)
                st.rerun()
        if monitored:
            st.caption(f"Monitoring **{len(monitored)}** parameter(s). Only each param's `value` is tracked.")
        else:
            st.info("No parameters added yet. Add at least one above.")

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
    interval = st.slider("Poll interval (seconds)", 1, 30, value=int(config.get("interval", 3)))

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

    st.subheader("What to monitor")
    st.caption("Let the agent read this device's datasheet and a sample response to map the fields.")
    sample = st.text_area("Sample response JSON (optional, for agent mapping)",
                          value=config.get("sample", ""), height=120)
    field_map = config.get("field_map", {})
    if st.button("🤖 Ask agent to map fields", disabled=not sample.strip()):
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
    st.write("Field map (metric → JSON path):", field_map or "— (simulated feed provides standard metrics)")

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
        if last_metrics is not None and not config.get("simulated", True):
            if last_metrics:
                st.caption("Latest extracted values: " + ", ".join(
                    f"{k}={v}" for k, v in list(last_metrics.items())[:10]))
            else:
                st.warning("The device responded but no numeric value was found. Expand the raw response "
                           "below and map the field, or the value may be non-numeric.")
        if history:
            frame = pd.DataFrame(history).set_index("timestamp")
            if len(frame.columns):
                st.line_chart(frame)
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

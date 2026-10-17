"""Shared: per-device analysis — renders the PRISM dashboard for the selected device."""
from __future__ import annotations

from pathlib import Path
import runpy

import streamlit as st

import device_data
import ui_common

_DASHBOARD = Path(__file__).resolve().parent.parent / "prism_reference" / "dashboard" / "app.py"


def _prepare_engine_state(device_id: str) -> None:
    """Point the embedded PRISM dashboard at the selected device's telemetry."""
    if st.session_state.get("prism_device") != device_id:
        # Device changed: rebuild the engine for this device.
        st.session_state["prism_device"] = device_id
        st.session_state.pop("engine", None)
        st.session_state["playing"] = False
        for key in ("live_asset", "live_metric", "cf_metric", "cf_asset"):
            st.session_state.pop(key, None)
        if device_data.mode(device_id) == "dataset":
            dataset = device_data.get_dataset(device_id)
            st.session_state["prism_pending_dataset"] = dataset
        else:
            st.session_state.pop("prism_pending_dataset", None)


def render() -> None:
    st.title("📊 Analysis")
    device = ui_common.device_selector("analysis_device")
    if not device:
        return
    device_id = device["id"]

    if device_data.mode(device_id) == "dataset" and device_data.get_dataset(device_id) is None:
        st.warning("This device is in dataset mode but has no telemetry. Ask an admin to simulate or "
                   "upload telemetry in **Simulate / Upload Telemetry**.")
        return

    st.caption(f"Device: **{device['name']}** · mode: **{device_data.mode(device_id)}**")
    _prepare_engine_state(device_id)

    # The PRISM dashboard calls st.set_page_config itself; suppress the duplicate call.
    original = st.set_page_config
    st.set_page_config = lambda *args, **kwargs: None
    try:
        runpy.run_path(str(_DASHBOARD), run_name="__main__")
    finally:
        st.set_page_config = original

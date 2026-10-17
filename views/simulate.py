"""Admin: generate or upload telemetry for a device."""
from __future__ import annotations

import streamlit as st

import device_data
import ui_common
from prism_cloud import replacement


def render() -> None:
    ui_common.require_role("admin")
    st.title("🧪 Simulate / Upload Telemetry")
    st.caption("Give a device telemetry to analyze — synthetic demo, generated dataset, or your own upload.")

    device = ui_common.device_selector("sim_device")
    if not device:
        return
    device_id = device["id"]
    st.write(f"Current mode: **{device_data.mode(device_id)}**")

    st.subheader("Option A — Built-in PRISM power demo (synthetic)")
    st.markdown(
        "Attaches the 22-asset, 6-scenario PRISM power simulator. This runs in **synthetic mode** with "
        "the full self-healing showcase (auto-remediation + verification)."
    )
    if st.button("Use built-in synthetic simulator", type="primary"):
        device_data.set_synthetic(device_id)
        st.success("Device set to synthetic PRISM simulator. Open **Analysis** to run it.")

    st.divider()
    st.subheader("Option B — Generate a dataset snapshot")
    st.markdown("Generates the PRISM fleet as an **uploaded dataset** (observation-only: escalates, no "
                "synthetic repairs). Useful to demonstrate the upload/replace path.")
    if st.button("Generate PRISM dataset snapshot"):
        with st.spinner("Generating telemetry dataset..."):
            dataset = device_data.build_prism_demo_dataset()
            device_data.set_dataset(device_id, dataset)
        st.success(f"Stored a {len(dataset.assets)}-asset dataset. Open **Analysis** to run it.")

    st.divider()
    st.subheader("Option C — Upload your own telemetry")
    st.markdown("Upload a **CSV or JSON** fleet file (authorized, non-confidential). Replaces this "
                "device's telemetry. Uploaded data is observation-only.")
    upload = st.file_uploader("Telemetry CSV / JSON", type=["csv", "json"], key="sim_upload")
    if st.button("Replace telemetry", disabled=upload is None):
        try:
            dataset = replacement(upload.getvalue().decode("utf-8-sig"), upload.name)
            device_data.set_dataset(device_id, dataset)
        except Exception as error:  # noqa: BLE001
            st.error(f"Rejected; telemetry unchanged: {error}")
        else:
            st.success(f"Loaded {len(dataset.assets)} assets, {len(dataset.telemetry)} readings. "
                       "Open **Analysis** to run it.")

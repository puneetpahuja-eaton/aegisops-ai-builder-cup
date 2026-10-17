"""Admin: manage devices (multi-device registry)."""
from __future__ import annotations

import streamlit as st

import devices
import ui_common


def render() -> None:
    ui_common.require_role("admin")
    st.title("🛠️ Device Manager")
    st.caption("Register and manage the equipment this platform monitors.")

    with st.expander("➕ Add a device", expanded=not devices.list_devices()):
        with st.form("add_device"):
            col1, col2 = st.columns(2)
            name = col1.text_input("Name *", placeholder="Feeder Meter 12")
            type_ = col2.text_input("Type", placeholder="POWER_METER / TRANSFORMER / UPS ...")
            col3, col4, col5 = st.columns(3)
            model = col3.text_input("Model", placeholder="PXM-2000")
            site = col4.text_input("Site", placeholder="DC-EAST")
            ip = col5.text_input("IP address (if on field)", placeholder="10.0.0.42")
            col6, col7 = st.columns(2)
            criticality = col6.selectbox("Criticality", devices.CRITICALITIES, index=1)
            protocol = col7.selectbox("Live protocol", devices.PROTOCOLS, index=0,
                                      help="REST is enabled; Modbus and DLMS are disabled in this edition.")
            submitted = st.form_submit_button("Add device", type="primary")
        if submitted:
            try:
                device = devices.create_device(
                    name=name, type=type_, model=model, site=site, ip=ip,
                    criticality=criticality, protocol=protocol,
                    created_by=ui_common.current_user()["email"],
                )
            except devices.DeviceError as error:
                st.error(str(error))
            else:
                st.success(f"Added **{device['name']}** (`{device['id']}`). Now feed it data in "
                           "**Data Sources** and **Simulate Data**.")
                st.rerun()

    st.subheader("Registered devices")
    all_devices = devices.list_devices()
    if not all_devices:
        st.info("No devices yet.")
        return
    for device in all_devices:
        with st.container(border=True):
            cols = st.columns([3, 2, 2, 2, 1])
            cols[0].markdown(f"**{device['name']}**  \n`{device['id']}`")
            cols[1].write(f"Type: {device['type']}")
            cols[1].write(f"Site: {device.get('site') or '—'}")
            cols[2].write(f"Protocol: `{device['protocol']}`")
            cols[2].write(f"Criticality: {device['criticality']}")
            cols[3].write(f"Status: `{device.get('status', 'configuring')}`")
            cols[3].write(f"Mode: {device.get('telemetry_mode', 'synthetic')}")
            if cols[4].button("Delete", key=f"del_{device['id']}"):
                devices.delete_device(device["id"])
                st.rerun()

"""Kairos AI — multi-device AI reliability platform (role-based, Google Cloud)."""
from __future__ import annotations

import streamlit as st

import netsetup

netsetup.configure_tls()

import auth
import devices
import ui_common
from views import (analysis, chat, data_sources, device_manager, integrations,
                   live_monitoring, simulate, user_admin)

ui_common.configure()


def home() -> None:
    user = ui_common.current_user()
    st.title("⚡ Kairos AI")
    st.caption("Multi-device AI reliability platform · Google Cloud AI Builder Cup")
    st.markdown(
        f"Signed in as **{user['email']}** (`{user['role']}`).\n\n"
        "Kairos AI onboards devices, learns from their documents and data (RAG), analyzes fed and "
        "**live** telemetry with an agentic engine, and answers questions in a grounded chat."
    )
    all_devices = devices.list_devices()
    cols = st.columns(3)
    cols[0].metric("Devices", len(all_devices))
    cols[1].metric("Your role", user["role"])
    cols[2].metric("Live protocol", "REST (Modbus/DLMS disabled)")
    if all_devices:
        st.subheader("Devices")
        st.dataframe([{"id": d["id"], "name": d["name"], "type": d["type"], "site": d.get("site", ""),
                       "status": d.get("status", ""), "mode": d.get("telemetry_mode", "synthetic")}
                      for d in all_devices], hide_index=True, width="stretch")
    else:
        st.info("No devices yet." + (" Add one in **Device Manager**." if user["role"] == "admin"
                                      else " Ask an admin to onboard a device."))
    if auth.can_configure(user["role"]):
        st.success("Admin: onboard devices → feed data / integrations → simulate or connect live → analyze.")
    elif auth.can_operate(user["role"]):
        st.info("Engineer: run analysis, configure live monitoring, and use the grounded chat.")
    else:
        st.info("Viewer: open **Analysis** and **Ask the device** (chat).")


def _build_navigation(role: str):
    overview = [st.Page(home, title="Home", icon="🏠", url_path="home", default=True)]
    monitor = [
        st.Page(analysis.render, title="Analysis", icon="📊", url_path="analysis"),
        st.Page(chat.render, title="Ask the device", icon="💬", url_path="chat"),
    ]
    if auth.can_operate(role):
        monitor.insert(1, st.Page(live_monitoring.render, title="Live Monitoring", icon="📡", url_path="live"))
    sections = {"Overview": overview, "Monitor": monitor}
    if auth.can_configure(role):
        sections["Admin"] = [
            st.Page(device_manager.render, title="Device Manager", icon="🛠️", url_path="devices"),
            st.Page(data_sources.render, title="Data Sources", icon="📚", url_path="data"),
            st.Page(integrations.render, title="Integrations", icon="🔗", url_path="integrations"),
            st.Page(simulate.render, title="Simulate / Upload", icon="🧪", url_path="simulate"),
            st.Page(user_admin.render, title="User Admin", icon="👤", url_path="users"),
        ]
    return st.navigation(sections)


def main() -> None:
    if not ui_common.current_user():
        ui_common.login_view()
        return
    ui_common.sidebar_account()
    _build_navigation(ui_common.current_role()).run()


main()

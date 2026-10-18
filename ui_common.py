"""Shared Streamlit helpers: page config, session, login gate, role gating."""
from __future__ import annotations

import streamlit as st

import auth
import datastore
import devices
import secretmgr
from gemini_client import backend as model_backend

PAGE_TITLE = "Kairos AI — Multi-Device AI Reliability"


def configure() -> None:
    st.set_page_config(page_title=PAGE_TITLE, layout="wide", page_icon="⚡")


def current_user() -> dict | None:
    return st.session_state.get("user")


def current_role() -> str:
    user = current_user()
    return user["role"] if user else ""


def logout() -> None:
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def login_view() -> None:
    auth.ensure_seed_admin()
    st.title("⚡ Kairos AI")
    st.caption("Multi-device AI reliability platform · Google Cloud AI Builder Cup")
    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")
    if submitted:
        try:
            user = auth.authenticate(email, password)
        except auth.AuthError as error:
            st.error(str(error))
        else:
            st.session_state["user"] = user
            st.rerun()
    with st.expander("Demo access"):
        st.markdown(
            "On first run a demo admin is seeded. Default credentials (override with "
            "`KAIROS_ADMIN_EMAIL` / `KAIROS_ADMIN_PASSWORD`):\n\n"
            "- **admin@kairos.ai** / **admin12345** (admin)\n\n"
            "Create engineer and viewer accounts from the **User Admin** page."
        )


def require_role(minimum: str) -> None:
    if not auth.at_least(current_role(), minimum):
        st.error("You do not have access to this page.")
        st.stop()


def sidebar_account() -> None:
    user = current_user()
    with st.sidebar:
        st.markdown(f"**{user['email']}**")
        st.caption(f"Role: `{user['role']}`")
        if st.button("Sign out", width="stretch"):
            logout()
        st.divider()
        st.caption("Backends")
        st.caption(f"Store: `{datastore.backend()}` · Secrets: `{secretmgr.backend()}`")
        st.caption(f"Model: `{model_backend()}`")


def device_selector(key: str = "active_device") -> dict | None:
    """Shared device picker; remembers the selection across pages."""
    all_devices = devices.list_devices()
    if not all_devices:
        st.info("No devices yet. An admin can add one from **Device Manager**.")
        return None
    labels = {d["id"]: f"{d['name']} ({d['type']})" for d in all_devices}
    ids = list(labels)
    current = st.session_state.get(key)
    index = ids.index(current) if current in ids else 0
    chosen = st.selectbox("Device", ids, index=index, format_func=lambda i: labels[i], key=f"{key}_select")
    st.session_state[key] = chosen
    return devices.get_device(chosen)

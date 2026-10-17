"""Admin: manage platform users and roles."""
from __future__ import annotations

import streamlit as st

import auth
import ui_common


def render() -> None:
    ui_common.require_role("admin")
    st.title("👤 User Admin")
    st.caption("Create engineer and viewer accounts; manage roles.")

    with st.expander("➕ Create user", expanded=True):
        with st.form("create_user"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password", help="At least 6 characters.")
            role = st.selectbox("Role", auth.ROLES, index=2)
            submitted = st.form_submit_button("Create", type="primary")
        if submitted:
            try:
                auth.create_user(email, password, role)
            except auth.AuthError as error:
                st.error(str(error))
            else:
                st.success(f"Created {email} as {role}.")
                st.rerun()

    st.subheader("Users")
    me = ui_common.current_user()["email"]
    for user in auth.list_users():
        with st.container(border=True):
            cols = st.columns([3, 2, 2, 1])
            cols[0].markdown(f"**{user['email']}**")
            new_role = cols[1].selectbox("Role", auth.ROLES, index=auth.ROLES.index(user["role"]),
                                         key=f"role_{user['email']}", label_visibility="collapsed")
            if new_role != user["role"]:
                if cols[2].button("Update role", key=f"upd_{user['email']}"):
                    auth.set_role(user["email"], new_role)
                    st.rerun()
            if user["email"] != me:
                if cols[3].button("Delete", key=f"deluser_{user['email']}"):
                    auth.delete_user(user["email"])
                    st.rerun()
            else:
                cols[3].caption("(you)")

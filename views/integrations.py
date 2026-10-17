"""Admin: GitHub and Confluence integrations to grow a device's knowledge."""
from __future__ import annotations

import streamlit as st

import secretmgr
import ui_common
from integrations import confluence, github


def render() -> None:
    ui_common.require_role("admin")
    st.title("🔗 Integrations")
    st.caption("Pull knowledge from GitHub repositories and Confluence pages (RAG).")

    with st.expander("🔑 API keys", expanded=not github.token()):
        st.caption(f"Secret store: `{secretmgr.backend()}`. Keys are stored as secrets, never in device records.")
        with st.form("keys"):
            gh = st.text_input("GitHub token", type="password",
                               help="A fine-scoped PAT with read access to the repos you want.")
            cf_base = st.text_input("Confluence base URL", placeholder="https://your-org.atlassian.net")
            cf_email = st.text_input("Confluence email")
            cf_token = st.text_input("Confluence API token", type="password")
            saved = st.form_submit_button("Save keys")
        if saved:
            if gh:
                secretmgr.put_secret("github_token", gh)
            if cf_base:
                secretmgr.put_secret("confluence_base_url", cf_base)
            if cf_email:
                secretmgr.put_secret("confluence_email", cf_email)
            if cf_token:
                secretmgr.put_secret("confluence_api_token", cf_token)
            st.success("Saved.")

    device = ui_common.device_selector("int_device")
    if not device:
        return
    device_id = device["id"]

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("GitHub repository")
        repo = st.text_input("owner/repo or URL", key="gh_repo", placeholder="eaton/prism-firmware")
        branch = st.text_input("Branch (optional)", key="gh_branch")
        if st.button("Ingest repository", disabled=not repo):
            with st.spinner("Fetching and embedding repository files..."):
                try:
                    result = github.ingest_repo(device_id, repo, branch or None)
                except Exception as error:  # noqa: BLE001
                    st.error(str(error))
                else:
                    st.success(f"Ingested {result['files']} of {result['matched']} matching files "
                               f"({result['chunks']} chunks) from {result['repo']}@{result['branch']}.")
                    if result.get("capped"):
                        st.warning(f"Only the first {result['files']} files were ingested (cap). "
                                   "Narrow with a subfolder repo or raise the cap for full coverage.")
                    if result.get("tree_truncated"):
                        st.warning("GitHub truncated the file tree (very large repo); some paths were not listed.")
    with col2:
        st.subheader("Confluence page")
        page = st.text_input("Page ID or URL", key="cf_page")
        if st.button("Ingest page", disabled=not page):
            with st.spinner("Fetching and embedding page..."):
                try:
                    result = confluence.ingest_page(device_id, page)
                except Exception as error:  # noqa: BLE001
                    st.error(str(error))
                else:
                    st.success(f"Ingested '{result['title']}' ({result['chunks']} chunks).")

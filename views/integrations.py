"""Admin: GitHub and Confluence integrations to grow a device's knowledge."""
from __future__ import annotations

import streamlit as st

import knowledge
import secretmgr
import ui_common
from integrations import github


def _key_status() -> dict:
    return {
        "GitHub token": bool(github.token()),
        "Confluence base URL": bool(secretmgr.get_secret("confluence_base_url")),
        "Confluence email": bool(secretmgr.get_secret("confluence_email")),
        "Confluence API token": bool(secretmgr.get_secret("confluence_api_token")),
    }


def render() -> None:
    ui_common.require_role("admin")
    st.title("🔗 Integrations")
    st.caption("Pull knowledge from GitHub repositories and Confluence pages (RAG). "
               "Keys and links are saved and persist across logins.")

    status = _key_status()
    with st.expander("🔑 API keys", expanded=not status["GitHub token"]):
        st.caption(f"Secret store: `{secretmgr.backend()}`. Keys are stored as secrets, never in device records.")
        st.write({name: ("saved ✅" if present else "not set") for name, present in status.items()})
        with st.form("keys"):
            gh = st.text_input("GitHub token", type="password",
                               help="A fine-scoped PAT with read access (and SSO authorization) to the repos.")
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
            st.success("Saved. These persist across logins.")
            st.rerun()

    device = ui_common.device_selector("int_device")
    if not device:
        return
    device_id = device["id"]

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("GitHub repository")
        repo = st.text_input("owner/repo or URL", key="gh_repo", placeholder="eaton/prism-firmware")
        branch = st.text_input("Branch (optional)", key="gh_branch")
        force = st.checkbox("Force full re-ingest (ignore cache)", key="gh_force",
                            help="Off = incremental: only changed files are re-embedded.")
        if st.button("Ingest & save repository", disabled=not repo):
            bar = st.progress(0.0, "Starting…")

            def _on_progress(done: int, total: int, label: str) -> None:
                frac = (done / total) if total else 1.0
                bar.progress(min(frac, 1.0), f"Embedding {done}/{total}: {label[-60:]}")

            try:
                result = knowledge.add_or_refresh(device_id, "github", repo, branch or None,
                                                  on_progress=_on_progress, force=force)
            except Exception as error:  # noqa: BLE001
                bar.empty()
                st.error(str(error))
            else:
                bar.progress(1.0, "Done")
                if result.get("skipped"):
                    st.success(f"Up to date — no changes in {result['repo']}@{result['branch']} "
                               f"({result['unchanged']} files unchanged).")
                else:
                    st.success(f"{result['repo']}@{result['branch']}: +{result.get('added', 0)} new, "
                               f"~{result.get('updated', 0)} updated, −{result.get('removed', 0)} removed, "
                               f"{result.get('unchanged', 0)} unchanged. Corpus: {result['chunks']} chunks.")
                if result.get("capped"):
                    st.warning("Matched files exceed the cap; only the first were ingested.")
                if result.get("tree_truncated"):
                    st.warning("GitHub truncated the file tree (very large repo); some paths were not listed.")
                st.rerun()
    with col2:
        st.subheader("Confluence page")
        page = st.text_input("Page ID or URL", key="cf_page")
        if st.button("Ingest & save page", disabled=not page):
            with st.spinner("Fetching and embedding page..."):
                try:
                    result = knowledge.add_or_refresh(device_id, "confluence", page)
                except Exception as error:  # noqa: BLE001
                    st.error(str(error))
                else:
                    st.success(f"Ingested '{result['title']}' ({result['chunks']} chunks). Saved.")
                    st.rerun()

    st.divider()
    st.subheader("Saved knowledge links")
    links = knowledge.list_links(device_id)
    if not links:
        st.caption("No saved links yet. Ingested repos/pages appear here and persist across logins.")
        return
    if st.button("🔁 Re-ingest all (incremental — only changed files)"):
        bar = st.progress(0.0, "Checking for changes…")

        def _all_progress(done: int, total: int, label: str) -> None:
            frac = (done / total) if total else 1.0
            bar.progress(min(frac, 1.0), label[-80:])

        outcomes = knowledge.reingest_all(device_id, on_progress=_all_progress)
        bar.progress(1.0, "Done")
        ok = sum(1 for item in outcomes if item["ok"])
        changed = sum(1 for item in outcomes if item["ok"] and not item.get("skipped"))
        st.success(f"Synced {ok}/{len(outcomes)} links · {changed} had changes, "
                   f"{ok - changed} already up to date.")
        for bad in [item for item in outcomes if not item["ok"]]:
            st.error(f"{bad['ref']}: {bad['error']}")
        st.rerun()
    for link in links:
        cols = st.columns([4, 2, 2, 1, 1])
        cols[0].markdown(f"**{link['kind']}** · `{link['ref']}`")
        cols[1].write(f"{link.get('chunk_count', 0)} chunks")
        cols[2].caption(f"Updated: {str(link.get('last_ingested', ''))[:19]}")
        if cols[3].button("Refresh", key=f"refresh_{link['id']}"):
            bar = st.progress(0.0, "Refreshing…")

            def _rp(done: int, total: int, label: str, _bar=bar) -> None:
                frac = (done / total) if total else 1.0
                _bar.progress(min(frac, 1.0), f"Embedding {done}/{total}: {label[-60:]}")

            try:
                knowledge.add_or_refresh(device_id, link["kind"], link["ref"], on_progress=_rp)
            except Exception as error:  # noqa: BLE001
                bar.empty()
                st.error(str(error))
            else:
                bar.progress(1.0, "Done")
                st.rerun()
        if cols[4].button("Remove", key=f"rmlink_{link['id']}"):
            knowledge.delete_link(device_id, link["id"])
            st.rerun()

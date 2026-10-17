"""Admin: feed a device with data (uploads) to build its RAG corpus."""
from __future__ import annotations

import streamlit as st

import ingest
import ui_common


def render() -> None:
    ui_common.require_role("admin")
    st.title("📚 Data Sources")
    st.caption("Upload documents and data so the agents learn about each device (RAG).")

    device = ui_common.device_selector("ds_device")
    if not device:
        return
    device_id = device["id"]

    st.subheader(f"Feed data to: {device['name']}")
    st.markdown(
        "Upload **PDF, Word, Excel, CSV, text, markdown, JSON or code**. Each file is extracted, "
        "chunked, embedded and stored as this device's knowledge. Datasheets, test cases, event/power "
        "logs, field data and documentation are all good inputs."
    )
    with st.form("upload_source", clear_on_submit=True):
        files = st.file_uploader("Files", accept_multiple_files=True,
                                 type=["pdf", "docx", "xlsx", "csv", "txt", "md", "json", "yaml", "yml", "py", "log"])
        kind = st.selectbox("Classify as", ingest.SOURCE_KINDS, index=0)
        submitted = st.form_submit_button("Ingest", type="primary")
    if submitted and files:
        progress = st.progress(0.0, "Starting ingestion...")
        for index, file in enumerate(files):
            progress.progress(index / len(files), f"Ingesting {file.name}...")
            try:
                record = ingest.ingest_file(device_id, file.name, file.getvalue(), kind)
            except Exception as error:  # noqa: BLE001 - surface any extraction/embedding error to the admin
                st.error(f"{file.name}: {error}")
            else:
                st.success(f"{file.name}: {record['chunk_count']} chunks embedded.")
        progress.progress(1.0, "Done.")
        st.rerun()

    st.subheader("Paste text")
    with st.form("paste_source", clear_on_submit=True):
        name = st.text_input("Source name", placeholder="Field note 2026-10")
        text = st.text_area("Text", height=150)
        kind2 = st.selectbox("Classify as", ingest.SOURCE_KINDS, index=3, key="paste_kind")
        submitted2 = st.form_submit_button("Ingest text")
    if submitted2 and text.strip():
        try:
            record = ingest.ingest_text(device_id, name=name or "pasted-text", kind=kind2, text=text)
        except Exception as error:  # noqa: BLE001
            st.error(str(error))
        else:
            st.success(f"Ingested {record['chunk_count']} chunks.")
            st.rerun()

    st.divider()
    st.subheader("Ingested sources")
    sources = ingest.list_sources(device_id)
    st.caption(f"Corpus size: **{ingest.corpus_size(device_id)}** embedded chunks across "
               f"**{len(sources)}** sources.")
    for source in sources:
        cols = st.columns([3, 2, 2, 1])
        cols[0].markdown(f"**{source['name']}**")
        cols[1].write(f"Kind: `{source['kind']}`")
        cols[2].write(f"{source['chunk_count']} chunks")
        if cols[3].button("Remove", key=f"rm_{source['id']}"):
            ingest.delete_source(device_id, source["id"])
            st.rerun()

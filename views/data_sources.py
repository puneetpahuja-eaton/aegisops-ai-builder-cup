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
    health = ingest.embedding_health(device_id)
    if health["stale"]:
        st.warning(f"{health['stale']} of {health['total']} chunks were embedded with a different model "
                   f"(dimension ≠ {health['dim']}) and are **ignored during search**. Re-embed them with the "
                   "current model to make all knowledge searchable — this reuses stored text (no re-download).")
        if st.button("🔧 Re-embed stale chunks with current model"):
            bar = st.progress(0.0, "Re-embedding…")

            def _re(done: int, total: int, label: str) -> None:
                bar.progress(min(done / total, 1.0) if total else 1.0, label)

            try:
                result = ingest.reembed_stale(device_id, on_progress=_re)
            except Exception as error:  # noqa: BLE001
                bar.empty()
                st.error(f"Re-embedding failed (likely a quota limit — retry): {error}")
            else:
                bar.progress(1.0, "Done")
                st.success(f"Re-embedded {result['reembedded']} chunks at dimension {result['dim']}. "
                           "All knowledge is now searchable.")
                st.rerun()
    else:
        st.caption(f"All chunks match the current embedding model (dimension {health['dim']}). ✅")
    for source in sources:
        cols = st.columns([3, 2, 2, 1])
        cols[0].markdown(f"**{source['name']}**")
        cols[1].write(f"Kind: `{source['kind']}`")
        cols[2].write(f"{source['chunk_count']} chunks")
        if cols[3].button("Remove", key=f"rm_{source['id']}"):
            ingest.delete_source(device_id, source["id"])
            st.rerun()

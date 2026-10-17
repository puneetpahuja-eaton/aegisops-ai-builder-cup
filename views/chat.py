"""Shared: Gemini-style RAG chat grounded in the selected device's data."""
from __future__ import annotations

import streamlit as st

import ingest
import rag
import ui_common


def _screen_context(device_id: str) -> str:
    engine = st.session_state.get("engine")
    if not engine or st.session_state.get("prism_device") != device_id:
        return ""
    try:
        cases = [c for c in engine.audit().get("cases", [])][:6]
    except Exception:  # noqa: BLE001
        return ""
    lines = [f"{c.get('case_id')}: {c.get('fault_type')} on {c.get('root_asset_id')} "
             f"-> {c.get('decision')}/{c.get('status')}" for c in cases]
    return "Active analysis cases:\n" + "\n".join(lines) if lines else ""


def render() -> None:
    st.title("💬 Ask the device")
    st.caption("Grounded in each device's ingested data (RAG). Answers cite the sources used.")
    status = rag.status()
    st.caption(f"Embeddings: `{status['embeddings']}` · Model: `{status['model']}` · "
               f"retrieves top {status.get('top_k', 24)} passages · remembers the conversation")

    device = ui_common.device_selector("chat_device")
    if not device:
        return
    device_id = device["id"]
    history_key = f"chat_history_{device_id}"
    st.session_state.setdefault(history_key, [])

    if ingest.corpus_size(device_id) == 0:
        st.info("No knowledge ingested for this device yet. Add data in **Data Sources**.")

    for message in st.session_state[history_key]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("citations"):
                st.caption("Sources: " + ", ".join(message["citations"]))

    prompt = st.chat_input("Ask about this device, its data, or the current analysis...")
    if not prompt:
        return
    st.session_state[history_key].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Retrieving and answering..."):
            result = rag.answer(device_id, prompt, screen_context=_screen_context(device_id),
                                role=ui_common.current_role(),
                                history=st.session_state[history_key][:-1])
        st.markdown(result["answer"])
        if result.get("citations"):
            st.caption("Sources: " + ", ".join(result["citations"]))
    st.session_state[history_key].append(
        {"role": "assistant", "content": result["answer"], "citations": result.get("citations", [])})

"""Shared: Gemini-style assistant grounded in the selected device's data.

Answers questions and performs generative tasks (historic datasets, test cases,
code, documentation) using the device corpus as grounding, with downloadable
artifacts.
"""
from __future__ import annotations

import streamlit as st

import ingest
import rag
import ui_common

_QUICK_ACTIONS = {
    "📊 Historic dataset": "Create a synthetic historic dataset (CSV) of the key measured parameters for "
                           "this device (e.g. voltage and current per phase) over 100 five-minute samples, "
                           "with a realistic daily pattern and a couple of labelled anomalies. Return it as "
                           "a ```csv block with a header row, and briefly describe the schema.",
    "🧪 Test cases": "Generate a set of test cases for this device's key behaviours and alarm/threshold "
                     "logic based on its documentation. Return them as a ```markdown table with columns: "
                     "ID, Scenario, Steps, Expected result. Note any assumptions.",
    "📝 Summary": "Summarise what you know about this device from the ingested documentation: its purpose, "
                 "key parameters, alarms and important operations. Cite the sources you used.",
    "🔧 Monitoring plan": "Propose a live-monitoring plan for this device: which parameters to watch, "
                         "suggested lower/upper thresholds with units, and why. Return a ```markdown table.",
}


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


def _render_artifacts(artifacts: list[dict], message_index: int) -> None:
    for art_index, artifact in enumerate(artifacts):
        st.download_button(
            f"⬇ Download {artifact['name']}", artifact["content"], artifact["name"], artifact["mime"],
            key=f"dl_{message_index}_{art_index}", on_click="ignore")
        if artifact.get("truncated"):
            st.caption("⚠ This artifact may be truncated at the model's output limit. Ask for fewer rows "
                       "or split it if you need the full set.")


def _run_assistant(device_id: str, prompt: str, history_key: str) -> None:
    st.session_state[history_key].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking and generating..."):
            result = rag.assist(device_id, prompt, screen_context=_screen_context(device_id),
                                role=ui_common.current_role(),
                                history=st.session_state[history_key][:-1])
        st.markdown(result["answer"])
        if result.get("artifacts"):
            _render_artifacts(result["artifacts"], len(st.session_state[history_key]))
        if result.get("citations"):
            st.caption("Sources: " + ", ".join(result["citations"]))
    st.session_state[history_key].append({
        "role": "assistant", "content": result["answer"],
        "citations": result.get("citations", []), "artifacts": result.get("artifacts", [])})


def render() -> None:
    st.title("💬 Ask the device")
    st.caption("A capable assistant grounded in each device's ingested data (RAG). Ask questions, or ask it "
               "to **create historic datasets, test cases, code, documentation** — artifacts are downloadable.")
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

    st.caption("Quick actions:")
    action_cols = st.columns(len(_QUICK_ACTIONS))
    pending = None
    for col, (label, instruction) in zip(action_cols, _QUICK_ACTIONS.items()):
        if col.button(label, key=f"qa_{label}", width="stretch"):
            pending = instruction

    for index, message in enumerate(st.session_state[history_key]):
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("artifacts"):
                _render_artifacts(message["artifacts"], index)
            if message.get("citations"):
                st.caption("Sources: " + ", ".join(message["citations"]))

    prompt = st.chat_input("Ask, or request a dataset / test cases / code / docs...")
    user_prompt = prompt or pending
    if not user_prompt:
        return
    _run_assistant(device_id, user_prompt, history_key)
    st.rerun()

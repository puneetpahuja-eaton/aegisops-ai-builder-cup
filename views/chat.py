"""Shared: Gemini-style assistant grounded in the selected device's data.

Answers questions and performs generative tasks (historic datasets, test cases,
code, documentation) using the device corpus as grounding, with downloadable
artifacts.
"""
from __future__ import annotations

import streamlit as st

import dataset_gen
import device_data
import devices
import ingest
import knowledge
import rag
import ui_common

_QUICK_ACTIONS = {
    "📊 Historic dataset": "Create a small synthetic historic dataset (CSV) of the key measured parameters "
                           "for this device (e.g. voltage and current per phase) over about 24 five-minute "
                           "samples, with a realistic daily pattern and one labelled anomaly. Return it as a "
                           "```csv block with a header row, and briefly describe the schema. For a larger, "
                           "loadable dataset, tell the user to use 'Build a dataset for Analysis' above.",
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


def _run_assistant(device_id: str, prompt: str, history_key: str, mode: str) -> None:
    st.session_state[history_key].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        spinner = {"ask": "Thinking…", "plan": "Planning…", "agent": "Working…"}.get(mode, "Thinking…")
        with st.spinner(spinner):
            result = rag.converse(device_id, prompt, mode=mode, screen_context=_screen_context(device_id),
                                  role=ui_common.current_role(),
                                  history=st.session_state[history_key][:-1])
        badge = {"ask": "💬 Ask", "plan": "📋 Plan", "agent": "🤖 Agent"}.get(mode, mode)
        st.caption(badge + (" · awaiting your answer" if result.get("needs_clarification")
                            else " · awaiting your confirmation" if result.get("awaiting_confirmation") else ""))
        st.markdown(result["answer"])
        if result.get("artifacts"):
            _render_artifacts(result["artifacts"], len(st.session_state[history_key]))
        if result.get("citations"):
            st.caption("Sources: " + ", ".join(result["citations"]))
    st.session_state[history_key].append({
        "role": "assistant", "content": result["answer"],
        "citations": result.get("citations", []), "artifacts": result.get("artifacts", []),
        "needs_clarification": result.get("needs_clarification", False)})


def _dataset_context(device_id: str) -> str:
    chunks = rag.retrieve(device_id, "measured parameters metrics units ranges voltage current power energy", top_k=16)
    return "\n\n".join(c.get("text", "")[:900] for c in chunks)


def _dataset_builder(device_id: str) -> None:
    is_admin = ui_common.current_role() == "admin"
    with st.expander("🧰 Build a dataset for Analysis", expanded=False):
        st.caption("Describe the dataset you want. Gemini can first ask clarifying questions, reference a "
                   "specific repo file for exact parameter names/IDs, then generate a dataset you can load "
                   "straight into the Analysis page (assets and metrics update to match).")
        ref_key = f"ds_ref_{device_id}"
        req_key = f"ds_req_{device_id}"
        request = st.text_area("What dataset do you want?", key=req_key, height=90,
                               placeholder="e.g. metering dataset with per-phase voltages, currents, active/"
                                           "reactive/apparent power and energies")
        ref_path = st.text_input("Reference a repo file for parameters (optional path)", key=ref_key,
                                 placeholder="source/Tools/RTK DCI DB Creator.xlsm",
                                 help="Pulled from this device's linked GitHub repo and used as the "
                                      "authoritative parameter list. Supports .xlsm/.xlsx/.csv/text.")
        span_cols = st.columns(2)
        days = span_cols[0].number_input("How many days of data?", min_value=1, max_value=14,
                                         value=3, step=1, key=f"ds_days_{device_id}",
                                         help="Total span of the dataset to synthesize.")
        interval_min = span_cols[1].number_input("Sample every (minutes)?", min_value=1, max_value=1440,
                                                 value=5, step=1, key=f"ds_interval_{device_id}",
                                                 help="Sampling rate — a reading every N minutes.")
        est_rows = int(days) * (24 * 60 // max(1, int(interval_min)))
        st.caption(f"≈ {est_rows:,} rows per asset at {int(interval_min)}-minute sampling over {int(days)} day(s).")
        cols = st.columns(3)
        if cols[0].button("❓ Ask clarifying questions", disabled=not request.strip(), key=f"ds_ask_{device_id}"):
            with st.spinner("Loading reference and thinking..."):
                try:
                    reference = _load_reference(device_id, ref_path)
                    questions = dataset_gen.clarifying_questions(_dataset_context(device_id), request, reference)
                except Exception as error:  # noqa: BLE001
                    st.error(str(error))
                else:
                    st.session_state[f"ds_questions_{device_id}"] = questions
        if st.session_state.get(f"ds_questions_{device_id}"):
            st.markdown("**Clarifying questions:**")
            st.markdown(st.session_state[f"ds_questions_{device_id}"])
            st.text_area("Your answers (optional)", key=f"ds_answers_{device_id}", height=80)
        if cols[1].button("🧰 Generate dataset", type="primary", disabled=not request.strip(),
                          key=f"ds_gen_{device_id}"):
            with st.spinner("Loading reference, designing the dataset, and synthesizing..."):
                try:
                    reference = _load_reference(device_id, ref_path)
                    spec = dataset_gen.generate_spec(_dataset_context(device_id), request, reference,
                                                     st.session_state.get(f"ds_answers_{device_id}", ""))
                    # User-selected span and sampling rate are authoritative.
                    spec["duration_days"] = int(days)
                    spec["sample_interval_min"] = int(interval_min)
                    spec.setdefault("history_days", max(1, int(days) // 2 or 1))
                    spec_obj = dataset_gen.DatasetSpec.model_validate(spec)
                    # Guarantee a size-scaled mix of auto-resolved + escalated faults.
                    spec_obj.anomalies = dataset_gen.ensure_anomaly_mix(spec_obj)
                    dataset = dataset_gen.build_dataset(spec_obj)
                except Exception as error:  # noqa: BLE001
                    st.error(f"Dataset generation failed: {error}")
                else:
                    st.session_state[f"ds_dataset_{device_id}"] = dataset
                    st.session_state[f"ds_spec_{device_id}"] = spec
        dataset = st.session_state.get(f"ds_dataset_{device_id}")
        if dataset is not None:
            st.success(f"Generated: {len(dataset.assets)} asset(s), "
                       f"{len(set(m for r in dataset.telemetry for m in r.metrics))} metric(s), "
                       f"{len(dataset.history)} history + {len(dataset.telemetry)} replay rows.")
            st.caption("Assets: " + ", ".join(a.id for a in dataset.assets)
                       + " · Metrics: " + ", ".join(sorted({m for r in dataset.telemetry for m in r.metrics}))[:300])
            st.download_button("⬇ Download dataset JSON", dataset.model_dump_json(indent=2),
                               "analysis-dataset.json", "application/json", on_click="ignore",
                               key=f"ds_dl_{device_id}")
            if is_admin:
                if st.button("➕ Load into Analysis", type="primary", key=f"ds_load_{device_id}"):
                    device_data.set_dataset(device_id, dataset)
                    st.session_state.pop("prism_device", None)  # Force Analysis to rebuild for this device.
                    st.success("Loaded. Open the **Analysis** page — its assets and metrics now reflect this "
                               "dataset. Press Play to run it.")
            else:
                st.info("Ask an admin to load this into Analysis, or download the JSON.")


def _load_reference(device_id: str, ref_path: str) -> str:
    if not ref_path.strip():
        return ""
    result = knowledge.fetch_repo_file_text(device_id, ref_path.strip())
    return result["text"]


def render() -> None:
    st.title("💬 Ask the device")
    st.caption("A capable assistant grounded in each device's ingested data (RAG). Three interactive modes — "
               "**Ask**, **Plan**, **Agent** — all clarify first when a request is vague.")
    status = rag.status()
    st.caption(f"Embeddings: `{status['embeddings']}` · Model: `{status['model']}` · "
               f"retrieves top {status.get('top_k', 24)} passages · remembers the conversation")

    device = ui_common.device_selector("chat_device")
    if not device:
        return
    device_id = device["id"]
    history_key = f"chat_history_{device_id}"
    mode_key = f"chat_mode_{device_id}"
    st.session_state.setdefault(history_key, [])

    mode_labels = {"💬 Ask": "ask", "📋 Plan": "plan", "🤖 Agent": "agent"}
    mode_help = ("**Ask** answers questions (clarifies if vague). **Plan** proposes an interactive plan, then "
                 "asks to implement. **Agent** clarifies, plans and executes — generating datasets, code and "
                 "docs. Switch anytime; the conversation is shared.")
    chosen = st.radio("Mode", list(mode_labels), horizontal=True, help=mode_help,
                      index=["ask", "plan", "agent"].index(st.session_state.get(mode_key, "agent")),
                      key=f"mode_radio_{device_id}")
    mode = mode_labels[chosen]
    st.session_state[mode_key] = mode
    cols = st.columns([1, 4])
    if cols[0].button("🗑 Clear chat", key=f"clear_{device_id}"):
        st.session_state[history_key] = []
        st.rerun()

    if ingest.corpus_size(device_id) == 0:
        st.info("No knowledge ingested for this device yet. Add data in **Data Sources**.")

    _dataset_builder(device_id)

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

    placeholder = {"ask": "Ask a question…", "plan": "Describe a task to plan…",
                   "agent": "Tell the agent what to do…"}[mode]
    prompt = st.chat_input(placeholder)
    user_prompt = prompt or pending
    if not user_prompt:
        return
    _run_assistant(device_id, user_prompt, history_key, mode)
    st.rerun()

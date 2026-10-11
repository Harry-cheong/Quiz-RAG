"""Chat input, answer, source expander."""
import streamlit as st
from src.graph import rag_workflow

from .sidebar import start_new_chat

def _title_from_prompt(prompt: str) -> str:
    title = " ".join(prompt.split())
    if len(title) <= 36:
        return title
    return title[:36].rstrip() + "…"

def render_chat():
    active = st.session_state.get("active_chat")

    if not active:
        st.markdown("## Welcome to RAG Bot")
        st.caption("Start a new conversation or continue from where you left off")
        messages = []
    else:
        messages = st.session_state.messages[active]
        if not messages:
            st.markdown("## What do you want to know?")
            st.caption("Ask a question. I’ll search your documents and answer from that context.")

        for message in messages:
            with st.chat_message(message["role"]):
                st.write(message["content"])

    prompt = st.chat_input(
        "Ask anything…",
        submit_mode="disable",
    )

    if prompt:
        if not active:
            start_new_chat()
            active = st.session_state.active_chat

        if st.session_state.chat_names.get(active) in (None, "New chat"):
            st.session_state.chat_names[active] = _title_from_prompt(prompt)

        st.session_state.messages[active].append({"role": "user", "content": prompt})
        # Sidebar already ran this script. Rerun so it is drawn with the new chat.
        st.rerun()

    if (
        active
        and st.session_state.messages.get(active)
        and st.session_state.messages[active][-1]["role"] == "user"
    ):
        prompt = st.session_state.messages[active][-1]["content"]
        with st.chat_message("assistant"):
            with st.spinner("Generating response...", show_time=True):
                # response = get_llm().invoke(prompt)
                response = rag_workflow().invoke({"question": prompt})
            text = response["generation"]
            st.write(text)
        st.session_state.messages[active].append({"role": "assistant", "content": text})
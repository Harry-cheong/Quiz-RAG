"""Chat input, answer, source expander."""
import streamlit as st
import requests

from .sidebar import start_new_chat

BASE_URL = "http://localhost:8000"

def _title_from_prompt(prompt: str) -> str:
    title = " ".join(prompt.split())
    if len(title) <= 36:
        return title
    return title[:36].rstrip() + "…"

def send_prompt(question):
    response = requests.post(f"{BASE_URL}/question", json={"question": question}, timeout=60)

    response.raise_for_status()
    return response.json()

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
                response = send_prompt(prompt)
            text = response["response"]["generation"]
            st.write(text)
        st.session_state.messages[active].append({"role": "assistant", "content": text})
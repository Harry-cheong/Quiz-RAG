"""Conversation list, new chat, delete — chatbot-style sidebar."""
import uuid

import streamlit as st


def _set_active_chat(chat_id: str) -> None:
    st.session_state.active_chat = chat_id

def start_new_chat() -> None:
    current = st.session_state.get("active_chat")
    if (
        current
        and current in st.session_state.messages
        and not st.session_state.messages[current]
    ):
        return

    chat_id = str(uuid.uuid4())
    st.session_state.chat_names[chat_id] = "New chat"
    st.session_state.messages[chat_id] = []
    st.session_state.chat_order = [chat_id, *st.session_state.get("chat_order", [])]
    st.session_state.active_chat = chat_id

def _delete_chat(chat_id: str) -> None:
    st.session_state.messages.pop(chat_id, None)
    st.session_state.chat_names.pop(chat_id, None)
    st.session_state.chat_order = [
        item for item in st.session_state.get("chat_order", []) if item != chat_id
    ]
    if not st.session_state.messages:
        st.session_state.active_chat = None
        return
    if st.session_state.get("active_chat") == chat_id:
        st.session_state.active_chat = st.session_state.chat_order[0]

def render_sidebar() -> None:
    with st.sidebar:
        st.logo(":material/auto_awesome:", size="large")
        st.header("RAG Bot")
        st.caption("Ask over your documents")

        st.button(
            "New chat",
            icon=":material/edit_square:",
            type="primary",
            width="stretch",
            on_click=start_new_chat,
        )

        order = st.session_state.get("chat_order") or list(st.session_state.messages)
        history_ids = [
            chat_id
            for chat_id in order
            if st.session_state.messages.get(chat_id)
        ]
        if history_ids:
            st.caption("Chats")
            for chat_id in history_ids:
                name = st.session_state.chat_names.get(chat_id, "Untitled")
                is_active = chat_id == st.session_state.get("active_chat")
                row = st.container(
                    horizontal=True,
                    gap="small",
                    wrap=False,
                    vertical_alignment="center",
                )
                with row:
                    st.button(
                        name,
                        key=f"open-{chat_id}",
                        type="secondary" if is_active else "tertiary",
                        width="stretch",
                        icon=":material/chat_bubble:",
                        on_click=_set_active_chat,
                        args=(chat_id,),
                        help=name,
                    )
                    st.button(
                        ":material/delete:",
                        key=f"delete-{chat_id}",
                        type="tertiary",
                        on_click=_delete_chat,
                        args=(chat_id,),
                        help="Delete chat",
                    )
        else:
            st.caption("No conversations yet")

        st.divider()
        st.caption("Harry")
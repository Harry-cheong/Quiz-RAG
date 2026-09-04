import uuid

import streamlit as st


def load_chats():
    if "messages" in st.session_state:
        return

    # chat_id = str(uuid.uuid4())
    # st.session_state.chat_order = [chat_id]
    # st.session_state.chat_names = {chat_id: "New chat"}
    # st.session_state.messages = {chat_id: []}
    st.session_state.chat_order = []
    st.session_state.chat_names = {}
    st.session_state.messages = {}

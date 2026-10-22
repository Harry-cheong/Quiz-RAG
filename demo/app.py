"""Streamlit entry: `streamlit run app.py`."""
import streamlit as st

from ui.chat import render_chat
from ui.sidebar import render_sidebar
from ui.documents import render_documents

from utils.db import load_chats

st.set_page_config(
    page_title="RAG Bot",
    page_icon="✨",
    layout="centered",
    initial_sidebar_state="expanded",
)

load_chats()

documents_page = st.Page(
    render_documents,
    title="Documents",
    url_path="docs",
    icon=":material/description:",
)

page = st.navigation([
    st.Page(render_chat, title="Chat", icon=":material/chat:", default=True),
    documents_page,
])

render_sidebar(documents_page)
page.run()

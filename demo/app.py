"""Streamlit entry: `streamlit run app.py`."""
import streamlit as st
from backend.rag.config import Config

from demo.ui.chat import render_chat
from demo.ui.sidebar import render_sidebar

from utils.db import load_chats

Config()

st.set_page_config(
    page_title="RAG Bot",
    page_icon="✨",
    layout="centered",
    initial_sidebar_state="expanded",
)

load_chats()
render_sidebar()
render_chat()
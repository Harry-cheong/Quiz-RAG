"""Paths, embedding model id, RRF constant, TOP_K."""
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from functools import lru_cache
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
ROOT = Path(__file__).resolve().parent.parent

class Config:
    CHROMA_PATH = ROOT / "chroma"
    EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    MAX_SEQ_LENGTH = 256
    FETCH_K = 5
    RRF_K = 60

    @classmethod
    @lru_cache(maxsize=1)
    def get_embedder(cls):
        embeddings = HuggingFaceEmbeddings(
            model_name=cls.EMBEDDING_MODEL,
            model_kwargs={"device": "mps"},  # "cpu" or "mps" on Apple Silicon, "cuda" on NVIDIA
            encode_kwargs={"normalize_embeddings": True},
        )
        return embeddings

    @classmethod
    @lru_cache(maxsize=1)
    def get_chroma(cls):
        return Chroma(
            persist_directory=cls.CHROMA_PATH,
            embedding_function=cls.get_embedder(),
        )
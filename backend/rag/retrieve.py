"""Chroma retriever + BM25 retriever + reciprocal rank fusion."""
from .config import Config

from collections import defaultdict
from typing import Any
from functools import lru_cache

from langchain_community.retrievers import BM25Retriever
from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

# RRF_K = 60   # Cormack et al. constant; dampens the gap between rank 1 and rank n
# FETCH_K = 10 # how many hits to pull from each retriever before fusing
# TOP_K = 5    # fused results returned to the graph

# Retrieve.py should not depend on splits variable which is temporarily created during ingestion

def load_indexed_doument():
    data = Config.get_chroma().get(
        include=["documents", "metadatas"]
    )

    return [
        Document(page_content=text, metadata=metadata or {})
        for text, metadata in zip(data["documents"], data["metadatas"])
    ]

@lru_cache(maxsize=1)
def get_retriever():
    vectorstore = Config.get_chroma()
    docs = load_indexed_doument()

    if not docs:
        raise RuntimeError("The index is empty. Ingest a PDF first.")
    chroma = vectorstore.as_retriever(
        search_kwargs={"k": Config.FETCH_K}
    )
    bm25 = BM25Retriever.from_documents(
        docs,
        k=Config.FETCH_K,
    )
    return ReciprocalRankFusionRetriever(
        retrievers=[chroma, bm25],
        rrf_k=Config.RRF_K,
        k=Config.FETCH_K,
    )

def reciprocal_rank_fusion(
    ranked_lists: list[list[Document]],
    k: int = Config.RRF_K,
) -> list[Document]:
    
    scores: dict[str, float] = defaultdict(float)
    first_seen: dict[str, Document] = {}
    for docs in ranked_lists:
        for rank, doc in enumerate(docs, start=1):
            key = doc.page_content
            scores[key] += 1.0 / (k + rank)
            first_seen.setdefault(key, doc)
    return [
        Document(
            page_content=key,
            metadata={**first_seen[key].metadata, "rrf_score": round(score, 6)},
        )
        for key, score in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    ]


class ReciprocalRankFusionRetriever(BaseRetriever):
    retrievers: list[Any] = Field()
    rrf_k: int = Config.RRF_K
    k: int = Config.FETCH_K
    model_config = ConfigDict(arbitrary_types_allowed=True)

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        ranked = [r.invoke(query) for r in self.retrievers]
        return reciprocal_rank_fusion(ranked, k=self.rrf_k)[: self.k]
"""PDF Load → Extract Tables, text → RecursiveSplitter → Truncate Chunk if exceed window → Chroma Documents"""
import sys
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

import pdfplumber
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

from .config import Config

@lru_cache(maxsize=1)
def _tokenizer():
    return AutoTokenizer.from_pretrained(Config.EMBEDDING_MODEL)

def _cell_text(cell: Optional[object]) -> str:
    if cell is None:
        return ""
    return str(cell).replace("\n", " ").strip()

def _table_rows(table) -> List[List[str]]:
    extracted = table.extract() or []
    rows: List[List[str]] = []
    for raw in extracted:
        if not raw:
            continue
        cells = [_cell_text(c) for c in raw]
        if any(cells):
            rows.append(cells)
    return rows

def hybrid_chunk_pdf(path: str) -> List[Document]:
    text_docs: List[Document] = []
    table_docs: List[Document] = []

    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            meta = {"source": str(path), "page": page.page_number}
            rest = page

            for table in page.find_tables():
                rest = rest.outside_bbox(table.bbox)

                rows = _table_rows(table)
                if len(rows) < 2:
                    continue

                headers = [cell if cell else f"col_{i}" for i, cell in enumerate(rows[0])]
                for row in rows[1:]:
                    row_headers = headers + [
                        f"col_{i}" for i in range(len(headers), len(row))
                    ]
                    parts = [
                        f"{header}: {cell}"
                        for header, cell in zip(row_headers, row)
                        if cell
                    ]
                    if parts:
                        table_docs.append(
                            Document(
                                page_content=" | ".join(parts),
                                metadata={**meta, "type": "table_row"},
                            )
                        )

            remaining = (rest.extract_text() or "").strip().replace("\n", " ")
            if remaining:
                text_docs.append(
                    Document(page_content=remaining, metadata={**meta, "type": "text"})
                )

    return text_docs + table_docs

def split(docs: List[Document]) -> List[Document]:
    text_docs = [d for d in docs if d.metadata.get("type") != "table_row"]
    table_docs = [d for d in docs if d.metadata.get("type") == "table_row"]
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    return splitter.split_documents(text_docs) + table_docs

def truncate_docs(docs: List[Document]) -> List[Document]:
    tok = _tokenizer()
    truncated: List[Document] = []
    for doc in docs:
        encoded = tok(
            doc.page_content,
            truncation=True,
            max_length=Config.MAX_SEQ_LENGTH,
            add_special_tokens=True,
        )
        text = tok.decode(encoded["input_ids"], skip_special_tokens=True)
        truncated.append(Document(page_content=text, metadata=doc.metadata))
    return truncated

def ingest_pdf(
    path: str,
    document_id: Optional[str] = None,
    folder_id: Optional[str] = None,
    filename: Optional[str] = None,
):
    docs = hybrid_chunk_pdf(path)

    for doc in docs:
        if document_id:
            doc.metadata["document_id"] = document_id
        if folder_id:
            doc.metadata["folder_id"] = folder_id
        if filename:
            doc.metadata["filename"] = filename

    splits = truncate_docs(split(docs))

    vectorstore = Config().get_chroma()
    vectorstore.add_documents(splits)
    
    return len(splits)

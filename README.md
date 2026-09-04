# rag-app

Streamlit RAG app. Fill in the modules; `rag.ipynb` in `my rag` is the lab for trying ideas first.

```
app.py                 # streamlit run app.py
src/
  config.py            # paths, model ids, RRF k, TOP_K
  ingest.py            # Docling + HybridChunker + Chroma
  retrieve.py          # Chroma + BM25 + reciprocal rank fusion
  generate.py          # prompt | llm | parser
  graph.py             # retrieve → grade → rewrite → generate
  llm.py               # chat model wrapper
  prompts.py
ui/
  chat.py              # question, answer, sources
  sidebar.py           # upload PDF, rebuild index
data/uploads/          # PDFs from the UI
chroma/                # vector store (gitignored)
```

Index once in `ingest.py`. Answer questions through `graph.py`. Keep Docling and `from_documents` off the chat path.

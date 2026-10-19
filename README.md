# RAG Bot

A document question-answering app with a Streamlit chat UI and a FastAPI backend. The backend retrieves relevant document chunks from Chroma and uses an LLM to generate an answer.

## Project layout

```text
backend/
  main.py             # FastAPI application
  api/chat.py         # Question and document endpoints
  rag/                # Ingestion, retrieval, RAG graph, and LLM setup
demo/
  app.py              # Streamlit entry point
  ui/                 # Chat and sidebar components
  utils/              # Chat UI utilities
data/                 # Uploaded PDF files (created as needed; gitignored)
chroma/               # Persistent Chroma index (gitignored)
```

## Setup

Use Python with `pip` and install the project dependencies from the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Set `OPENROUTER_API_KEY` and `OPENROUTER_MODEL` in `.env`. Keep the API key private; `.env` is excluded from Git.

## Run the app

Start the backend in one terminal from the repository root:

```bash
cd backend
uvicorn main:app --reload
```

The API listens at `http://localhost:8000`; interactive API documentation is at <http://localhost:8000/docs>.

Start the Streamlit UI in a second terminal from the repository root:

```bash
cd demo
streamlit run app.py
```

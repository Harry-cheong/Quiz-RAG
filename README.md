# Leetcode Question RAG Bot

An application that helps to organise attempted Leetcode questions by topics and allows users to create their own list. A RAG system works in the background to recommend new questions based on questions attempted.

## Project layout

```text
backend/
  main.py             # FastAPI application
  docker-compose.yml  # Docker Compose File
  api/
    leetcode.py       # HTTP Endpoints to create, search for questions
    health.py         # HTTP Endpoints for application health
  database/
    schema.sql        # Initialised schema
  db/
    connect.py        # Utility Functions to connect to database
    models.py         # ORM Models
  test/
    test_leetcode.py  # Unit Testing for leetcode.py endpoints
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

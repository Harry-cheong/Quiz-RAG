from langchain.agents import create_agent
from functools import cache
from langchain_openai import ChatOpenAI

import dotenv
import os

dotenv.load_dotenv()

API_KEY = os.environ.get("OPENROUTER_API_KEY")
MODEL = os.environ.get("OPENROUTER_MODEL")

@cache
def get_llm():
    return ChatOpenAI(
        model=MODEL,
        api_key=API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=0,
        default_headers={"HTTP-Referer": "http://localhost", "X-Title": "my-agent"},
    )
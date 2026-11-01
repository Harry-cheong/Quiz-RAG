from fastapi import FastAPI
from api.chat import router as chat_router
from api.leetcode import router as question_router

app = FastAPI()
app.include_router(chat_router, prefix="/chat", tags=["chat"])
app.include_router(question_router, prefix="/leetcode", tags=["leetcode"])
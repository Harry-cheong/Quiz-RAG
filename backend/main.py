from fastapi import FastAPI
from api.leetcode import router as question_router

app = FastAPI()
app.include_router(question_router, tags=["leetcode"])
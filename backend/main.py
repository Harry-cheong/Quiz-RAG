from fastapi import FastAPI
from api.questions import router as question_router
from api.auth import router as auth_router

app = FastAPI()
app.include_router(question_router, tags=["Question"])
app.include_router(auth_router, tags=["Auth"])
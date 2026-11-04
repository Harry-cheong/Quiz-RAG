from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from db.connect import SessionLocal
from db.models import User

from auth.security import verify_password, get_token, hash_password

router = APIRouter()

def get_db():
    db = SessionLocal()

    if db:
        yield db

@router.post("/login")
def login(username: str, pwd: str, db: Session=Depends(get_db)):
    user = db.scalar(select(User).where(User.username == username))

    if user is None or not verify_password(pwd, user.hashed_pwd):
        raise HTTPException(status_code=404)

    token = get_token(user.id, user.username)
    return {"token": token}

@router.post("/users/create")
def create_user(username: str, pwd: str, db: Session=Depends(get_db)):
    hashed_pwd = hash_password(pwd)

    user = User(username=username, hashed_pwd=hashed_pwd)

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"id": user.id, "username": username, "hashed_pwd": hashed_pwd}
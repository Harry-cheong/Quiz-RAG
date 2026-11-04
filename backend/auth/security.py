from dotenv import load_dotenv
import os

import jwt
from passlib.context import CryptContext
from datetime import timedelta, datetime, timezone

load_dotenv()

ALGORITHM = "HS256"
SECRET = os.getenv("SECRET_KEY")
ACCESS_TOKEN_EXPIRY_TOKEN = 60

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

def get_token(user_id: str, username: str):
    payload = {
        "id": str(user_id),
        "username": username,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRY_TOKEN)
    }
    return jwt.encode(payload, SECRET, ALGORITHM)

def verify_password(plain, hashed):
    return pwd_context.verify(plain, hashed)

def hash_password(pwd):
    return pwd_context.hash(pwd)

def decode_payload(payload):
    return jwt.decode(payload, SECRET, ALGORITHM)
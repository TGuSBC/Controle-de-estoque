
from jose import jwt
from passlib.context import CryptContext
from datetime import datetime, timedelta

SECRET = "stillus_secret"
ALGO = "HS256"

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password):
    return pwd.hash(password)

def verify(password, hashed):
    return pwd.verify(password, hashed)

def create_token(data: dict):
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=10)
    return jwt.encode(payload, SECRET, algorithm=ALGO)

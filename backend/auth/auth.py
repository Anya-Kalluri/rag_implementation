import json
import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext

from backend.config.settings import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

# 🔥 absolute path (no file issues)
DB_FILE = os.path.join(os.getcwd(), "users.json")

# 🔥 FIXED hashing (no bcrypt issues)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# -------------------------------
# LOAD USERS
# -------------------------------
if os.path.exists(DB_FILE):
    try:
        with open(DB_FILE, "r") as f:
            fake_users_db = json.load(f)
    except:
        fake_users_db = {}
else:
    fake_users_db = {}

# -------------------------------
# SAVE USERS
# -------------------------------
def save_users():
    with open(DB_FILE, "w") as f:
        json.dump(fake_users_db, f, indent=4)

# -------------------------------
# PASSWORD
# -------------------------------
def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str):
    return pwd_context.verify(plain, hashed)

# -------------------------------
# TOKEN
# -------------------------------
def create_token(data: dict):
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
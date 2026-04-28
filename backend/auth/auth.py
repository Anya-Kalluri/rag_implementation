from datetime import datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config.settings import ACCESS_TOKEN_EXPIRE_MINUTES, ALGORITHM, SECRET_KEY
from backend.db import connect, init_db


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
fake_users_db = {}


def load_users():
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT username, password, role FROM users ORDER BY username"
        ).fetchall()

    return {
        row["username"]: {
            "username": row["username"],
            "password": row["password"],
            "role": row["role"],
        }
        for row in rows
    }


def refresh_users():
    fake_users_db.clear()
    fake_users_db.update(load_users())


def save_users():
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM users")
        for username, user in fake_users_db.items():
            conn.execute(
                """
                INSERT INTO users (username, password, role)
                VALUES (?, ?, ?)
                """,
                (username, user["password"], user["role"]),
            )


def hash_password(password: str):
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str):
    return pwd_context.verify(plain, hashed)


def create_token(data: dict):
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


refresh_users()

"""Authentication primitives: password hashing, user loading, and JWT tokens."""

import os
from datetime import datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config.settings import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    ALGORITHM,
    REFRESH_TOKEN_EXPIRE_DAYS,
    SECRET_KEY,
)
from backend.db import connect, init_db


pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# The app keeps an in-memory user cache for quick auth checks, but SQLite remains
# the source of truth. refresh_users() synchronizes the cache from the database.
fake_users_db = {}
ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


def load_users():
    """Load all user records from SQLite into a dictionary keyed by username."""
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
    """Refresh the in-memory auth cache and bootstrap an admin if the DB is empty."""
    fake_users_db.clear()
    fake_users_db.update(load_users())

    if not fake_users_db:
        bootstrap_admin_user()
        fake_users_db.clear()
        fake_users_db.update(load_users())


def save_users():
    """Persist the in-memory user cache back to SQLite."""
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


def bootstrap_admin_user():
    """Create the first admin account from environment defaults when needed."""
    admin_username = os.getenv("ADMIN_USERNAME", "admin").strip()
    admin_password = os.getenv("ADMIN_PASSWORD", "admin").strip()

    if not admin_username or not admin_password:
        return

    fake_users_db[admin_username] = {
        "username": admin_username,
        "password": hash_password(admin_password),
        "role": "admin",
    }
    save_users()


def hash_password(password: str):
    """Hash a plaintext password before storing it."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str):
    """Verify a plaintext password against a stored password hash."""
    return pwd_context.verify(plain, hashed)


def create_token(
    data: dict,
    expires_delta: timedelta | None = None,
    token_type: str = ACCESS_TOKEN_TYPE,
):
    """Create a signed JWT with a token type and expiry timestamp."""
    to_encode = data.copy()
    to_encode["token_type"] = token_type
    to_encode["exp"] = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(data: dict):
    """Create a short-lived token used for normal authenticated API calls."""
    return create_token(
        data,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type=ACCESS_TOKEN_TYPE,
    )


def create_refresh_token(data: dict):
    """Create a longer-lived token used to obtain a new access token."""
    return create_token(
        data,
        expires_delta=timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        token_type=REFRESH_TOKEN_TYPE,
    )


def decode_token(token: str):
    """Decode a JWT and return None instead of raising on invalid tokens."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# Populate the auth cache at import time so route handlers can validate users.
refresh_users()

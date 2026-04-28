import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "rag_app.sqlite3"


def encode(value):
    return json.dumps(value, ensure_ascii=False)


def decode(value, default=None):
    if value is None:
        return default

    try:
        return json.loads(value)
    except Exception:
        return default


@contextmanager
def connect():
    DATA_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                role TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chats (
                user TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                title TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (user, chat_id)
            );

            CREATE TABLE IF NOT EXISTS chat_history (
                user TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                history_json TEXT NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (user, chat_id)
            );

            CREATE TABLE IF NOT EXISTS files (
                file_key TEXT PRIMARY KEY,
                file TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                role TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                path TEXT NOT NULL,
                source_file TEXT,
                source_uploaded_by TEXT,
                source_role TEXT,
                source_chat_id TEXT,
                source_path TEXT,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                text TEXT NOT NULL,
                roles_json TEXT NOT NULL,
                position INTEGER NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_chunks_chat
                ON chunks (user_id, chat_id, position);

            CREATE TABLE IF NOT EXISTS faiss_indexes (
                user_id TEXT NOT NULL,
                chat_id TEXT NOT NULL,
                index_blob BLOB NOT NULL,
                updated_at REAL NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                time REAL NOT NULL,
                data_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_events_type_time
                ON events (type, time);

            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_role TEXT NOT NULL,
                entry_json TEXT NOT NULL,
                created_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS guest_usage (
                username TEXT PRIMARY KEY,
                count INTEGER NOT NULL,
                date TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS legacy_json (
                path TEXT PRIMARY KEY,
                content_json TEXT NOT NULL,
                migrated_at REAL NOT NULL
            );
            """
        )


def get_state(key, default=None):
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT value_json FROM app_state WHERE key = ?",
            (key,),
        ).fetchone()

    return decode(row["value_json"], default) if row else default


def set_state(key, value):
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO app_state (key, value_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value_json = excluded.value_json,
                updated_at = excluded.updated_at
            """,
            (key, encode(value), time.time()),
        )


init_db()

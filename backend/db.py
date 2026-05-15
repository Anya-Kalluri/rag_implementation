"""SQLite database setup and shared persistence utilities."""

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
DB_PATH = DATA_DIR / "rag_app.sqlite3"


def encode(value):
    """Serialize Python values as JSON for SQLite text columns."""
    return json.dumps(value, ensure_ascii=False)


def decode(value, default=None):
    """Deserialize JSON text, returning default when data is missing or invalid."""
    if value is None:
        return default

    try:
        return json.loads(value)
    except Exception:
        return default


@contextmanager
def connect():
    """Open a SQLite connection with row dictionaries and auto-commit behavior."""
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
    """Create or migrate all SQLite tables used by the application."""
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
                auto_title INTEGER NOT NULL DEFAULT 1,
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
                is_shared INTEGER NOT NULL DEFAULT 1,
                shared_roles_json TEXT NOT NULL DEFAULT '["manager","analyst","viewer","guest"]',
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
        file_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(files)").fetchall()
        }
        # Lightweight migrations keep existing local databases usable when new
        # sharing columns are added.
        if "is_shared" not in file_columns:
            conn.execute(
                "ALTER TABLE files ADD COLUMN is_shared INTEGER NOT NULL DEFAULT 1"
            )
        if "shared_roles_json" not in file_columns:
            conn.execute(
                """
                ALTER TABLE files
                ADD COLUMN shared_roles_json TEXT NOT NULL
                DEFAULT '["manager","analyst","viewer","guest"]'
                """
            )

        chat_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(chats)").fetchall()
        }
        # Existing manually named chats should not be overwritten by auto-title
        # generation after the auto_title column is introduced.
        if "auto_title" not in chat_columns:
            conn.execute(
                "ALTER TABLE chats ADD COLUMN auto_title INTEGER NOT NULL DEFAULT 1"
            )
            conn.execute(
                """
                UPDATE chats
                SET auto_title = 0
                WHERE title NOT GLOB 'Chat [0-9]*'
                """
            )


def get_state(key, default=None):
    """Read a JSON value from the generic app_state table."""
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT value_json FROM app_state WHERE key = ?",
            (key,),
        ).fetchone()

    return decode(row["value_json"], default) if row else default


def set_state(key, value):
    """Write a JSON value to the generic app_state table."""
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


# Ensure the database exists before the rest of the app starts using it.
init_db()

import time

from backend.db import connect, decode, encode, init_db


def load_history(user, chat_id):
    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT history_json
            FROM chat_history
            WHERE user = ? AND chat_id = ?
            """,
            (user, chat_id),
        ).fetchone()

    return decode(row["history_json"], []) if row else []


def save_history(user, chat_id, history):
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO chat_history (user, chat_id, history_json, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user, chat_id) DO UPDATE SET
                history_json = excluded.history_json,
                updated_at = excluded.updated_at
            """,
            (user, chat_id, encode(history), time.time()),
        )

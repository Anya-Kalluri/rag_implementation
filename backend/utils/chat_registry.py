import time
import uuid

from backend.db import connect, init_db


def create_chat(user):
    init_db()
    chat_id = str(uuid.uuid4())
    now = time.time()

    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS count FROM chats WHERE user = ?",
            (user,),
        ).fetchone()
        position = int(row["count"] or 0) + 1
        conn.execute(
            """
            INSERT INTO chats (user, chat_id, title, position, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user, chat_id, f"Chat {position}", position, now, now),
        )

    return chat_id


def get_chats(user):
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT chat_id, title
            FROM chats
            WHERE user = ?
            ORDER BY position ASC, created_at ASC
            """,
            (user,),
        ).fetchall()

    return [{"chat_id": row["chat_id"], "title": row["title"]} for row in rows]


def delete_chat(user, chat_id):
    init_db()
    with connect() as conn:
        conn.execute(
            "DELETE FROM chats WHERE user = ? AND chat_id = ?",
            (user, chat_id),
        )
        conn.execute(
            "DELETE FROM chat_history WHERE user = ? AND chat_id = ?",
            (user, chat_id),
        )


def rename_chat(user, chat_id, new_title):
    init_db()
    with connect() as conn:
        conn.execute(
            """
            UPDATE chats
            SET title = ?, updated_at = ?
            WHERE user = ? AND chat_id = ?
            """,
            (new_title, time.time(), user, chat_id),
        )

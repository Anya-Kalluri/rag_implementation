"""Chat registry helpers for creating, listing, deleting, and naming chats."""

import time
import uuid

from backend.db import connect, init_db


def create_chat(user):
    """Create a new chat workspace for a user and return its chat_id."""
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
            INSERT INTO chats (user, chat_id, title, auto_title, position, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user, chat_id, f"Chat {position}", 1, position, now, now),
        )

    return chat_id


def get_chats(user):
    """List a user's chats in newest-first order."""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT chat_id, title, auto_title, position, created_at, updated_at
            FROM chats
            WHERE user = ?
            ORDER BY created_at DESC, position DESC
            """,
            (user,),
        ).fetchall()

    return [
        {
            "chat_id": row["chat_id"],
            "title": row["title"],
            "auto_title": bool(row["auto_title"]),
            "position": row["position"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
        for row in rows
    ]


def delete_chat(user, chat_id):
    """Delete a chat registry entry and its saved conversation history."""
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
    """Rename a chat manually and prevent future automatic title changes."""
    init_db()
    with connect() as conn:
        conn.execute(
            """
            UPDATE chats
            SET title = ?, auto_title = 0, updated_at = ?
            WHERE user = ? AND chat_id = ?
            """,
            (new_title, time.time(), user, chat_id),
        )


def auto_rename_chat(user, chat_id, new_title):
    """Rename a chat only while it is still marked as auto-title managed."""
    title = str(new_title or "").strip()
    if not title:
        return None

    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT title, auto_title
            FROM chats
            WHERE user = ? AND chat_id = ?
            """,
            (user, chat_id),
        ).fetchone()

        if not row or not bool(row["auto_title"]):
            return None

        if row["title"] == title:
            conn.execute(
                """
                UPDATE chats
                SET auto_title = 0, updated_at = ?
                WHERE user = ? AND chat_id = ?
                """,
                (time.time(), user, chat_id),
            )
            return title

        conn.execute(
            """
            UPDATE chats
            SET title = ?, auto_title = 0, updated_at = ?
            WHERE user = ? AND chat_id = ?
            """,
            (title, time.time(), user, chat_id),
        )

    return title

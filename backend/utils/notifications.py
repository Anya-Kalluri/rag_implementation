"""Notification persistence for admin/manager upload notices."""

from datetime import datetime
import time

from backend.db import connect, decode, encode, init_db


DEFAULT_TARGETS = ("admin", "manager")


def load_notifications():
    """Load notifications grouped by target role."""
    init_db()
    data = {target: [] for target in DEFAULT_TARGETS}

    with connect() as conn:
        rows = conn.execute(
            """
            SELECT target_role, entry_json
            FROM notifications
            ORDER BY created_at ASC
            """
        ).fetchall()

    for row in rows:
        target = row["target_role"]
        data.setdefault(target, []).append(decode(row["entry_json"], {}))

    return data


def save_notifications(data):
    """Replace all notification rows from an in-memory role mapping."""
    init_db()
    with connect() as conn:
        conn.execute("DELETE FROM notifications")
        for target, entries in (data or {}).items():
            for entry in entries or []:
                conn.execute(
                    """
                    INSERT INTO notifications (target_role, entry_json, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (target, encode(entry), time.time()),
                )


def add_notification(username, file_name):
    """Notify admin and manager roles that a user uploaded a file."""
    init_db()
    entry = {
        "user": username,
        "file": file_name,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    with connect() as conn:
        for target in DEFAULT_TARGETS:
            conn.execute(
                """
                INSERT INTO notifications (target_role, entry_json, created_at)
                VALUES (?, ?, ?)
                """,
                (target, encode(entry), time.time()),
            )

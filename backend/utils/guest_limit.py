from datetime import datetime

from backend.db import connect, init_db


def check_limit(username, limit=5):
    init_db()
    today = datetime.now().strftime("%Y-%m-%d")

    with connect() as conn:
        row = conn.execute(
            "SELECT count, date FROM guest_usage WHERE username = ?",
            (username,),
        ).fetchone()

        if not row or row["date"] != today:
            count = 0
        else:
            count = int(row["count"] or 0)

        if count >= limit:
            return False

        conn.execute(
            """
            INSERT INTO guest_usage (username, count, date)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                count = excluded.count,
                date = excluded.date
            """,
            (username, count + 1, today),
        )

    return True

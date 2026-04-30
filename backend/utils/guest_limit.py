from datetime import datetime

from backend.db import connect, init_db
from backend.config.settings import GUEST_QUERY_LIMIT


def consume_query(username, limit=None):
    init_db()
    today = datetime.now().strftime("%Y-%m-%d")

    if limit is None:
        limit = GUEST_QUERY_LIMIT

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
            return {
                "allowed": False,
                "used": count,
                "remaining": 0,
                "limit": limit,
            }

        count += 1

        conn.execute(
            """
            INSERT INTO guest_usage (username, count, date)
            VALUES (?, ?, ?)
            ON CONFLICT(username) DO UPDATE SET
                count = excluded.count,
                date = excluded.date
            """,
            (username, count, today),
        )

    return {
        "allowed": True,
        "used": count,
        "remaining": max(limit - count, 0),
        "limit": limit,
    }


def check_limit(username, limit=None):
    return consume_query(username, limit)["allowed"]

import time

from backend.db import connect, decode, encode, init_db


def log_event(event_type, data):
    init_db()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO events (type, time, data_json)
            VALUES (?, ?, ?)
            """,
            (event_type, time.time(), encode(data)),
        )


def load_events(event_type=None):
    init_db()
    query = "SELECT type, time, data_json FROM events"
    params = []

    if event_type:
        query += " WHERE type = ?"
        params.append(event_type)

    query += " ORDER BY time ASC"

    with connect() as conn:
        rows = conn.execute(query, params).fetchall()

    return [
        {
            "type": row["type"],
            "time": row["time"],
            "data": decode(row["data_json"], {}),
        }
        for row in rows
    ]

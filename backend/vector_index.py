import time

import faiss
import numpy as np

from backend.db import connect, init_db


def read_index(user_id, chat_id):
    init_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT index_blob
            FROM faiss_indexes
            WHERE user_id = ? AND chat_id = ?
            """,
            (str(user_id).strip(), str(chat_id).strip()),
        ).fetchone()

    if not row:
        return None

    data = np.frombuffer(row["index_blob"], dtype="uint8")
    return faiss.deserialize_index(data)


def write_index(user_id, chat_id, index):
    init_db()
    blob = faiss.serialize_index(index).tobytes()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO faiss_indexes (user_id, chat_id, index_blob, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, chat_id) DO UPDATE SET
                index_blob = excluded.index_blob,
                updated_at = excluded.updated_at
            """,
            (str(user_id).strip(), str(chat_id).strip(), blob, time.time()),
        )


def delete_index(user_id, chat_id):
    init_db()
    with connect() as conn:
        conn.execute(
            "DELETE FROM faiss_indexes WHERE user_id = ? AND chat_id = ?",
            (str(user_id).strip(), str(chat_id).strip()),
        )

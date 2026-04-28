import json
import sys
import time
from pathlib import Path

import faiss


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.db import connect, encode, init_db, set_state  # noqa: E402
from backend.utils.file_metadata import file_key  # noqa: E402


ROOT_JSON_FILES = [
    "chats.json",
    "file_metadata.json",
    "files.json",
    "guest_usage.json",
    "logs.json",
    "metrics.json",
    "notifications.json",
    "users.json",
]


def read_json(path, default):
    if not path.exists():
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def archive_json(path, content, conn=None):
    params = (str(path.relative_to(ROOT)), encode(content), time.time())
    query = """
        INSERT INTO legacy_json (path, content_json, migrated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            content_json = excluded.content_json,
            migrated_at = excluded.migrated_at
    """

    if conn is not None:
        conn.execute(query, params)
        return

    with connect() as archive_conn:
        archive_conn.execute(query, params)


def migrate_users():
    path = ROOT / "users.json"
    if not path.exists():
        return 0
    users = read_json(path, {})
    if not isinstance(users, dict):
        return 0

    with connect() as conn:
        for username, data in users.items():
            if not isinstance(data, dict):
                continue
            conn.execute(
                """
                INSERT INTO users (username, password, role)
                VALUES (?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password = excluded.password,
                    role = excluded.role
                """,
                (username, data.get("password", ""), data.get("role", "viewer")),
            )

    archive_json(ROOT / "users.json", users)
    return len(users)


def migrate_chats():
    path = ROOT / "chats.json"
    if not path.exists():
        return 0
    chats = read_json(path, {})
    if not isinstance(chats, dict):
        return 0

    count = 0
    now = time.time()
    with connect() as conn:
        for user, items in chats.items():
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items, start=1):
                if not isinstance(item, dict) or not item.get("chat_id"):
                    continue
                conn.execute(
                    """
                    INSERT INTO chats (user, chat_id, title, position, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(user, chat_id) DO UPDATE SET
                        title = excluded.title,
                        position = excluded.position,
                        updated_at = excluded.updated_at
                    """,
                    (
                        user,
                        item["chat_id"],
                        item.get("title") or f"Chat {index}",
                        index,
                        now,
                        now,
                    ),
                )
                count += 1

    archive_json(ROOT / "chats.json", chats)
    return count


def migrate_chat_history():
    history_dir = ROOT / "history"
    count = 0

    if not history_dir.exists():
        return count

    with connect() as conn:
        for path in history_dir.glob("*/*.json"):
            history = read_json(path, [])
            user = path.parent.name
            chat_id = path.stem
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
            archive_json(path, history, conn)
            count += 1

    return count


def migrate_files():
    path = ROOT / "file_metadata.json"
    if not path.exists():
        return 0
    files = read_json(path, [])
    if not isinstance(files, list):
        return 0

    count = 0
    with connect() as conn:
        for item in files:
            if not isinstance(item, dict):
                continue
            stored = item.copy()
            stored["file_key"] = stored.get("file_key") or file_key(stored)
            conn.execute(
                """
                INSERT INTO files (
                    file_key, file, uploaded_by, role, chat_id, path,
                    source_file, source_uploaded_by, source_role, source_chat_id,
                    source_path, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(file_key) DO UPDATE SET
                    file = excluded.file,
                    uploaded_by = excluded.uploaded_by,
                    role = excluded.role,
                    chat_id = excluded.chat_id,
                    path = excluded.path,
                    source_file = excluded.source_file,
                    source_uploaded_by = excluded.source_uploaded_by,
                    source_role = excluded.source_role,
                    source_chat_id = excluded.source_chat_id,
                    source_path = excluded.source_path
                """,
                (
                    stored["file_key"],
                    stored.get("file", ""),
                    stored.get("uploaded_by", ""),
                    stored.get("role", ""),
                    stored.get("chat_id", ""),
                    stored.get("path", ""),
                    stored.get("source_file"),
                    stored.get("source_uploaded_by"),
                    stored.get("source_role"),
                    stored.get("source_chat_id"),
                    stored.get("source_path"),
                    time.time(),
                ),
            )
            count += 1

    archive_json(ROOT / "file_metadata.json", files)
    return count


def migrate_logs():
    path = ROOT / "logs.json"
    if not path.exists():
        return 0
    logs = read_json(path, [])
    if not isinstance(logs, list):
        return 0

    with connect() as conn:
        conn.execute("DELETE FROM events")
        for entry in logs:
            if not isinstance(entry, dict):
                continue
            conn.execute(
                "INSERT INTO events (type, time, data_json) VALUES (?, ?, ?)",
                (
                    entry.get("type", "unknown"),
                    float(entry.get("time") or time.time()),
                    encode(entry.get("data", {})),
                ),
            )

    archive_json(ROOT / "logs.json", logs)
    return len(logs)


def migrate_metrics():
    path = ROOT / "metrics.json"
    if not path.exists():
        return 0
    metrics = read_json(path, None)
    if not isinstance(metrics, dict):
        return 0

    set_state("metrics", metrics)
    archive_json(ROOT / "metrics.json", metrics)
    return 1


def migrate_notifications():
    path = ROOT / "notifications.json"
    if not path.exists():
        return 0
    notifications = read_json(path, {})
    if not isinstance(notifications, dict):
        return 0

    count = 0
    with connect() as conn:
        conn.execute("DELETE FROM notifications")
        for target, entries in notifications.items():
            for entry in entries or []:
                conn.execute(
                    """
                    INSERT INTO notifications (target_role, entry_json, created_at)
                    VALUES (?, ?, ?)
                    """,
                    (target, encode(entry), time.time()),
                )
                count += 1

    archive_json(ROOT / "notifications.json", notifications)
    return count


def migrate_guest_usage():
    path = ROOT / "guest_usage.json"
    if not path.exists():
        return 0
    usage = read_json(path, {})
    if not isinstance(usage, dict):
        return 0

    count = 0
    with connect() as conn:
        for username, data in usage.items():
            if not isinstance(data, dict):
                continue
            conn.execute(
                """
                INSERT INTO guest_usage (username, count, date)
                VALUES (?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    count = excluded.count,
                    date = excluded.date
                """,
                (username, int(data.get("count", 0) or 0), data.get("date", "")),
            )
            count += 1

    archive_json(ROOT / "guest_usage.json", usage)
    return count


def migrate_chunks():
    vectorstore = ROOT / "vectorstore"
    count = 0

    if not vectorstore.exists():
        return count

    with connect() as conn:
        for path in vectorstore.glob("*/*/meta.json"):
            meta = read_json(path, [])
            if not isinstance(meta, list):
                archive_json(path, meta, conn)
                continue

            user_id = path.parent.parent.name
            chat_id = path.parent.name
            conn.execute(
                "DELETE FROM chunks WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id),
            )
            for position, item in enumerate(meta):
                if not isinstance(item, dict) or not str(item.get("text", "")).strip():
                    continue
                conn.execute(
                    """
                    INSERT INTO chunks (id, user_id, chat_id, text, roles_json, position, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.get("id") or f"{user_id}-{chat_id}-{position}",
                        user_id,
                        chat_id,
                        item.get("text", ""),
                        encode(item.get("roles", [])),
                        position,
                        time.time(),
                    ),
                )
                count += 1

            archive_json(path, meta, conn)

        for path in vectorstore.glob("*/*/history.json"):
            archive_json(path, read_json(path, []), conn)

    return count


def migrate_faiss_indexes():
    vectorstore = ROOT / "vectorstore"
    count = 0

    if not vectorstore.exists():
        return count

    with connect() as conn:
        for path in vectorstore.glob("*/*/index.faiss"):
            user_id = path.parent.parent.name
            chat_id = path.parent.name
            try:
                index = faiss.read_index(str(path))
                blob = faiss.serialize_index(index).tobytes()
            except Exception:
                continue

            conn.execute(
                """
                INSERT INTO faiss_indexes (user_id, chat_id, index_blob, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id, chat_id) DO UPDATE SET
                    index_blob = excluded.index_blob,
                    updated_at = excluded.updated_at
                """,
                (user_id, chat_id, blob, time.time()),
            )
            count += 1

    return count


def archive_unused_root_json():
    count = 0
    for filename in ROOT_JSON_FILES:
        path = ROOT / filename
        if filename in {
            "chats.json",
            "file_metadata.json",
            "guest_usage.json",
            "logs.json",
            "metrics.json",
            "notifications.json",
            "users.json",
        }:
            continue

        if path.exists():
            archive_json(path, read_json(path, None))
            count += 1

    return count


def main():
    init_db()
    results = {
        "users": migrate_users(),
        "chats": migrate_chats(),
        "chat_history": migrate_chat_history(),
        "files": migrate_files(),
        "logs": migrate_logs(),
        "metrics": migrate_metrics(),
        "notifications": migrate_notifications(),
        "guest_usage": migrate_guest_usage(),
        "chunks": migrate_chunks(),
        "faiss_indexes": migrate_faiss_indexes(),
        "unused_json_archives": archive_unused_root_json(),
    }

    for key, value in results.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()

import time
from hashlib import sha256

from backend.db import connect, decode, encode, init_db


SHARED_LIBRARY_ROLES = {"manager", "analyst", "viewer", "guest"}
DEFAULT_SHARED_ROLES = ["manager", "analyst", "viewer", "guest"]


FILE_COLUMNS = [
    "file_key",
    "file",
    "uploaded_by",
    "role",
    "chat_id",
    "path",
    "is_shared",
    "shared_roles_json",
    "source_file",
    "source_uploaded_by",
    "source_role",
    "source_chat_id",
    "source_path",
]


def file_key(item):
    raw = "|".join([
        str(item.get("path", "")),
        str(item.get("file", "")),
        str(item.get("uploaded_by", "")),
        str(item.get("chat_id", "")),
    ])
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def row_to_file(row):
    item = {column: row[column] for column in FILE_COLUMNS if column in row.keys()}
    item["shared_roles"] = normalize_shared_roles(
        decode(item.get("shared_roles_json"), DEFAULT_SHARED_ROLES)
    )
    return item


def normalize_shared_roles(roles):
    if roles is None:
        return DEFAULT_SHARED_ROLES.copy()
    if isinstance(roles, str):
        roles = roles.split(",")

    normalized = []
    for role in roles:
        value = str(role).strip().lower()
        if value in SHARED_LIBRARY_ROLES and value not in normalized:
            normalized.append(value)
    return normalized


def add_file(filename, user, role, chat_id, path, source=None, is_shared=True, shared_roles=None):
    init_db()
    user = user.strip()
    role = role.strip()
    source = source or {}
    source_path = source.get("path", path)
    if shared_roles is None and source.get("shared_roles") is not None:
        shared_roles = source.get("shared_roles")
    if shared_roles is None:
        shared_roles = DEFAULT_SHARED_ROLES if is_shared else []
    shared_roles = normalize_shared_roles(shared_roles)

    item = {
        "file": filename,
        "uploaded_by": user,
        "role": role,
        "chat_id": chat_id,
        "path": path,
        "is_shared": 1 if is_shared else 0,
        "shared_roles_json": encode(shared_roles),
        "source_file": source.get("file"),
        "source_uploaded_by": source.get("uploaded_by"),
        "source_role": source.get("role"),
        "source_chat_id": source.get("chat_id"),
        "source_path": source.get("path"),
    }
    item["file_key"] = file_key(item)

    with connect() as conn:
        conn.execute(
            """
            DELETE FROM files
            WHERE file = ?
              AND uploaded_by = ?
              AND chat_id = ?
              AND COALESCE(source_path, path) = ?
            """,
            (filename, user, chat_id, source_path),
        )
        conn.execute(
            """
            INSERT INTO files (
                file_key, file, uploaded_by, role, chat_id, path, is_shared, shared_roles_json,
                source_file, source_uploaded_by, source_role, source_chat_id,
                source_path, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["file_key"],
                item["file"],
                item["uploaded_by"],
                item["role"],
                item["chat_id"],
                item["path"],
                item["is_shared"],
                item["shared_roles_json"],
                item["source_file"],
                item["source_uploaded_by"],
                item["source_role"],
                item["source_chat_id"],
                item["source_path"],
                time.time(),
            ),
        )


def get_files(user=None, chat_id=None):
    init_db()
    query = "SELECT * FROM files"
    clauses = []
    params = []

    if user:
        clauses.append("uploaded_by = ?")
        params.append(user.strip())

    if chat_id:
        clauses.append("chat_id = ?")
        params.append(chat_id)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY created_at DESC"

    with connect() as conn:
        rows = conn.execute(query, params).fetchall()

    return [row_to_file(row) for row in rows]


def get_file_by_key(key):
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM files WHERE file_key = ?",
            (key,),
        ).fetchone()

    return row_to_file(row) if row else None

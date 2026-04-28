import json
import os
from hashlib import sha256


FILE_DB = "file_metadata.json"


def load_data():
    if not os.path.exists(FILE_DB):
        return []

    try:
        with open(FILE_DB, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_data(data):
    with open(FILE_DB, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def file_key(item):
    raw = "|".join([
        str(item.get("path", "")),
        str(item.get("file", "")),
        str(item.get("uploaded_by", "")),
        str(item.get("chat_id", "")),
    ])
    return sha256(raw.encode("utf-8")).hexdigest()[:16]


def with_file_keys(files):
    keyed = []
    for item in files:
        if not isinstance(item, dict):
            continue

        copy = item.copy()
        copy["file_key"] = copy.get("file_key") or file_key(copy)
        keyed.append(copy)

    return keyed


def add_file(filename, user, role, chat_id, path, source=None):
    data = load_data()
    user = user.strip()
    role = role.strip()
    source = source or {}
    source_path = source.get("path", path)

    data = [
        f for f in data
        if not (
            f.get("file") == filename
            and f.get("uploaded_by") == user
            and f.get("chat_id") == chat_id
            and f.get("source_path", f.get("path")) == source_path
        )
    ]

    item = {
        "file": filename,
        "uploaded_by": user,
        "role": role,
        "chat_id": chat_id,
        "path": path,
    }

    if source:
        item.update({
            "source_file": source.get("file"),
            "source_uploaded_by": source.get("uploaded_by"),
            "source_role": source.get("role"),
            "source_chat_id": source.get("chat_id"),
            "source_path": source.get("path"),
        })

    item["file_key"] = file_key(item)
    data.append(item)
    save_data(data)


def get_files(user=None, chat_id=None):
    data = load_data()

    if user:
        user = user.strip()

    if user and chat_id:
        return with_file_keys([
            f for f in data
            if f.get("uploaded_by") == user and f.get("chat_id") == chat_id
        ])

    if user:
        return with_file_keys([
            f for f in data
            if f.get("uploaded_by") == user
        ])

    if chat_id:
        return with_file_keys([
            f for f in data
            if f.get("chat_id") == chat_id
        ])

    return with_file_keys(data)


def get_file_by_key(key):
    for item in get_files():
        if item.get("file_key") == key:
            return item

    return None

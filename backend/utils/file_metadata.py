import json
import os

FILE_DB = "file_metadata.json"


def load_data():
    if not os.path.exists(FILE_DB):
        return []

    try:
        with open(FILE_DB, "r") as f:
            return json.load(f)
    except:
        # 🔥 Prevent crash if file is corrupted
        return []


def save_data(data):
    with open(FILE_DB, "w") as f:
        json.dump(data, f, indent=2)


def add_file(filename, user, role, chat_id, path):
    data = load_data()

    user = user.strip()
    role = role.strip()

    # 🔥 Prevent duplicate entries (same file in same chat)
    data = [
        f for f in data
        if not (
            f["file"] == filename and
            f["uploaded_by"] == user and
            f["chat_id"] == chat_id
        )
    ]

    data.append({
        "file": filename,
        "uploaded_by": user,
        "role": role,
        "chat_id": chat_id,
        "path": path
    })

    save_data(data)


def get_files(user=None, chat_id=None):
    data = load_data()

    # 🔥 Normalize
    if user:
        user = user.strip()

    # 🔥 Flexible filtering
    if user and chat_id:
        return [
            f for f in data
            if f["uploaded_by"] == user and f["chat_id"] == chat_id
        ]

    elif user:
        return [
            f for f in data
            if f["uploaded_by"] == user
        ]

    elif chat_id:
        return [
            f for f in data
            if f["chat_id"] == chat_id
        ]

    return data
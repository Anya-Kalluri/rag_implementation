import json
import os
import uuid

FILE = "chats.json"


def load():
    if os.path.exists(FILE):
        return json.load(open(FILE))
    return {}


def save(data):
    with open(FILE, "w") as f:
        json.dump(data, f, indent=4)


def create_chat(user):
    data = load()

    chat_id = str(uuid.uuid4())

    if user not in data:
        data[user] = []

    data[user].append({
        "chat_id": chat_id,
        "title": f"Chat {len(data[user]) + 1}"
    })

    save(data)
    return chat_id


def get_chats(user):
    data = load()
    return data.get(user, [])


# 🔥 NEW: DELETE CHAT
def delete_chat(user, chat_id):
    data = load()

    if user in data:
        data[user] = [c for c in data[user] if c["chat_id"] != chat_id]

    save(data)


# 🔥 NEW: RENAME CHAT
def rename_chat(user, chat_id, new_title):
    data = load()

    if user in data:
        for c in data[user]:
            if c["chat_id"] == chat_id:
                c["title"] = new_title

    save(data)
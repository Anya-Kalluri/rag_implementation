import os
import json

BASE = "history"


def get_path(user, chat_id):
    path = os.path.join(BASE, user)
    os.makedirs(path, exist_ok=True)
    return os.path.join(path, f"{chat_id}.json")


def load_history(user, chat_id):
    path = get_path(user, chat_id)

    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)

    return []


def save_history(user, chat_id, history):
    path = get_path(user, chat_id)

    with open(path, "w") as f:
        json.dump(history, f, indent=4)
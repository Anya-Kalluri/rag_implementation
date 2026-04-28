import json
import os
from datetime import datetime

NOTIF_FILE = "notifications.json"


def load_notifications():
    if os.path.exists(NOTIF_FILE):
        with open(NOTIF_FILE, "r") as f:
            return json.load(f)
    return {"admin": [], "manager": []}


def save_notifications(data):
    with open(NOTIF_FILE, "w") as f:
        json.dump(data, f, indent=4)


def add_notification(username, file_name):
    data = load_notifications()

    entry = {
        "user": username,
        "file": file_name,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    data["admin"].append(entry)
    data["manager"].append(entry)

    save_notifications(data)
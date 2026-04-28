import json
import os
from datetime import datetime

FILE = "guest_usage.json"


def load():
    if os.path.exists(FILE):
        with open(FILE) as f:
            return json.load(f)
    return {}


def save(data):
    with open(FILE, "w") as f:
        json.dump(data, f, indent=4)


def check_limit(username, limit=5):
    data = load()

    today = datetime.now().strftime("%Y-%m-%d")

    user = data.get(username, {"count": 0, "date": today})

    if user["date"] != today:
        user = {"count": 0, "date": today}

    if user["count"] >= limit:
        return False

    user["count"] += 1
    data[username] = user

    save(data)

    return True
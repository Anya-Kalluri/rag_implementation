import time
import json
import os

LOG_FILE = "logs.json"

def log_event(event_type, data):

    entry = {
        "type": event_type,
        "time": time.time(),
        "data": data
    }

    if not os.path.exists(LOG_FILE):
        logs = []
    else:
        with open(LOG_FILE, "r") as f:
            try:
                logs = json.load(f)
            except:
                logs = []

    logs.append(entry)

    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)


def load_events(event_type=None):
    if not os.path.exists(LOG_FILE):
        return []

    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)
    except Exception:
        return []

    if not isinstance(logs, list):
        return []

    if event_type:
        return [entry for entry in logs if entry.get("type") == event_type]

    return logs

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
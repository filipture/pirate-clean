import os
import json
import hashlib
import uuid

def get_device_id():
    path = os.path.expanduser("~/.reddit_commander/device_id.json")

    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)["device_id"]

    mac = uuid.getnode()
    device_id = hashlib.sha256(str(mac).encode()).hexdigest()

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump({"device_id": device_id}, f)

    return device_id

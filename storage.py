import json
import os
import threading

_LOCK = threading.Lock()


def read_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return default


def write_json(path, data):
    with _LOCK:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        os.replace(tmp, path)

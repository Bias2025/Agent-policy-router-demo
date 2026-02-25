import json, time, uuid
from typing import Any, Dict

AUDIT_PATH = "audit_log.jsonl"

def log_event(event_type: str, payload: Dict[str, Any]) -> None:
    record = {
        "event_id": str(uuid.uuid4()),
        "ts_epoch": time.time(),
        "event_type": event_type,
        **payload,
    }
    with open(AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

def tail_events(limit: int = 20):
    try:
        with open(AUDIT_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()[-limit:]
        return [json.loads(x) for x in lines]
    except FileNotFoundError:
        return []

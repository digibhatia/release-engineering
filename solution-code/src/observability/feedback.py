"""Human feedback (underwriter overrides of the agent's recommendation)
+ annotation queue. Inherited base."""

import time

from src.observability.online_eval import recent_judged

_feedback: list[dict] = []


def record_feedback(underwriting_id: str, rating: str, note: str = "") -> dict:
    entry = {"underwriting_id": underwriting_id, "rating": rating, "note": note, "ts": time.time()}
    _feedback.append(entry)
    return entry


def recent_feedback(limit: int = 20) -> list[dict]:
    return list(_feedback[-limit:])


def annotation_queue() -> list[dict]:
    queue = []
    seen_ids = set()
    for entry in _feedback:
        if entry["rating"] == "down" and entry["underwriting_id"] not in seen_ids:
            queue.append({"source": "human_feedback", **entry})
            seen_ids.add(entry["underwriting_id"])
    for entry in recent_judged():
        if entry["verdict"] == "fail":
            queue.append({"source": "online_eval", **entry})
    return queue

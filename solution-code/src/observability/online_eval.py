"""Sampled model-graded (LLM-as-judge) evaluation of underwriting
recommendation notes against the evidence actually gathered. Every judged
entry carries the release `variant` (stable/canary/shadow) it came from —
this is the signal quality_gate.py reads to decide whether a canary
prompt/model change is regressing quality, independent of error rate."""

import os
import random
import re
from collections import deque

from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

from src.observability.metrics import record_eval_score

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

SAMPLE_RATE = float(os.environ.get("SAKH_EVAL_SAMPLE_RATE", "0.5"))
PASS_THRESHOLD = 4

JUDGE_SYSTEM_PROMPT = """You are grading an underwriting recommendation
note against the evidence that was actually gathered for the
application. Score 1-5: does the note accurately reflect the
affordability (DTI) and policy-compliance findings present in the
evidence, with a clear, policy-consistent recommendation and no
fabricated or missing findings? Respond in exactly this format:
SCORE: <1-5>
REASON: <one sentence>
"""

_RECENT_JUDGED: deque = deque(maxlen=200)
_client = None


def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    return _client


def _parse_judge_reply(text: str) -> tuple[int, str]:
    score_match = re.search(r"SCORE:\s*(\d)", text)
    reason_match = re.search(r"REASON:\s*(.+)", text)
    score = int(score_match.group(1)) if score_match else 0
    reason = reason_match.group(1).strip() if reason_match else "(no reason parsed)"
    return score, reason


def maybe_grade(gathered_evidence: dict, recommendation_note: str, variant: str = "stable") -> dict | None:
    if random.random() > SAMPLE_RATE:
        return None
    client = _get_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": f"Evidence: {gathered_evidence}\n\nRecommendation note: {recommendation_note}"},
        ],
    )
    score, reason = _parse_judge_reply(response.choices[0].message.content or "")
    verdict = "pass" if score >= PASS_THRESHOLD else "fail"
    entry = {"score": score, "reason": reason, "verdict": verdict, "variant": variant}
    _RECENT_JUDGED.append(entry)
    record_eval_score(score, variant=variant)
    return entry


def recent_judged(variant: str | None = None) -> list[dict]:
    if variant is None:
        return list(_RECENT_JUDGED)
    return [e for e in _RECENT_JUDGED if e["variant"] == variant]


def rolling_average_score(variant: str | None = None, window: int = 30) -> float | None:
    entries = recent_judged(variant)[-window:]
    if not entries:
        return None
    return round(sum(e["score"] for e in entries) / len(entries), 2)

"""OTel metric instruments. Includes Module 8's release-variant
breakdown — every request/cost/eval metric also carries a `variant`
attribute (stable/canary/shadow) so a canary's quality can be compared
against stable's on the SAME dashboard, which is what quality_gate.py's
decision is ultimately checked against."""

from src.observability.otel_setup import get_meter

_meter = get_meter("sakh.metrics")

request_counter = _meter.create_counter("sakh.requests.total", description="Total finished underwriting sessions")
duration_histogram = _meter.create_histogram("sakh.request.duration_ms", unit="ms")
cost_histogram = _meter.create_histogram("sakh.request.cost_usd", unit="usd")
eval_score_histogram = _meter.create_histogram("sakh.eval.score")
drift_score_histogram = _meter.create_histogram("sakh.drift.score")
rollback_counter = _meter.create_counter("sakh.release.rollback.total", description="Automated quality-triggered rollbacks")


def record_underwriting_turn(model: str, duration_ms: float, cost_usd: float, variant: str) -> None:
    request_counter.add(1, {"model": model, "variant": variant})
    duration_histogram.record(duration_ms, {"model": model, "variant": variant})
    cost_histogram.record(cost_usd, {"model": model, "variant": variant})


def record_subagent_duration(duration_ms: float, variant: str = "stable") -> None:
    duration_histogram.record(duration_ms, {"model": "underwriting_subagent", "variant": variant})


def record_eval_score(score: float, variant: str = "stable") -> None:
    eval_score_histogram.record(score, {"variant": variant})


def record_drift_score(score: float, dimension: str) -> None:
    drift_score_histogram.record(score, {"dimension": dimension})


def record_rollback(reason: str) -> None:
    rollback_counter.add(1, {"reason": reason})

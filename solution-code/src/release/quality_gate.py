"""
Automated quality-triggered rollback — Module 8.

The key distinction this module exists to teach: a canary rollback
triggered by a QUALITY regression (the underwriting note's LLM-judged
score dropping) is a DIFFERENT signal from an error-rate-triggered
rollback (HTTP 5xxs, exceptions). A prompt or model change can serve
200 OK on every single request and still be meaningfully worse — vaguer
recommendations, policy-inconsistent language, a tone regression — and
an error-rate-only gate (the default in most off-the-shelf canary
tooling) will never catch that. This module reads eval scores recorded
by src/observability/online_eval.py, broken out by release variant, and
makes a promote/hold/rollback decision from THAT signal specifically.

In production this decision would be read by Argo Rollouts' AnalysisRun
(see k8s/rollout/analysis-template.yaml, which runs the equivalent
PromQL query against the sakh.eval.score metric) to automatically abort
a canary rollout. Here, evaluate_quality_gate() is the same decision
logic, callable directly from CI (see .github/workflows/) or from a
scheduled check against the running system.
"""

from dataclasses import dataclass

from src.observability.online_eval import rolling_average_score, recent_judged
from src.observability.metrics import record_rollback

MIN_SAMPLES_PER_VARIANT = 5
# A canary whose rolling average score is more than this many points
# below stable's is considered a quality regression, not noise.
REGRESSION_THRESHOLD_POINTS = 0.5

_rollback_log: list[dict] = []


@dataclass
class GateDecision:
    decision: str  # "promote" | "hold" | "rollback"
    reason: str
    stable_avg_score: float | None
    canary_avg_score: float | None
    stable_sample_size: int
    canary_sample_size: int


def evaluate_quality_gate() -> GateDecision:
    stable_samples = recent_judged(variant="stable")
    canary_samples = recent_judged(variant="canary")
    stable_avg = rolling_average_score(variant="stable")
    canary_avg = rolling_average_score(variant="canary")

    if len(stable_samples) < MIN_SAMPLES_PER_VARIANT or len(canary_samples) < MIN_SAMPLES_PER_VARIANT:
        return GateDecision(
            decision="hold",
            reason=(f"Not enough judged samples yet to decide "
                    f"(stable={len(stable_samples)}, canary={len(canary_samples)}, "
                    f"need >= {MIN_SAMPLES_PER_VARIANT} each)."),
            stable_avg_score=stable_avg, canary_avg_score=canary_avg,
            stable_sample_size=len(stable_samples), canary_sample_size=len(canary_samples),
        )

    regression = (stable_avg - canary_avg) if (stable_avg is not None and canary_avg is not None) else 0.0

    if regression >= REGRESSION_THRESHOLD_POINTS:
        decision = GateDecision(
            decision="rollback",
            reason=(f"Canary's rolling average eval score ({canary_avg}) is "
                    f"{round(regression, 2)} points below stable's ({stable_avg}), "
                    f"past the {REGRESSION_THRESHOLD_POINTS}-point threshold — "
                    f"this is a QUALITY regression, independent of error rate."),
            stable_avg_score=stable_avg, canary_avg_score=canary_avg,
            stable_sample_size=len(stable_samples), canary_sample_size=len(canary_samples),
        )
        trigger_rollback(decision.reason)
        return decision

    return GateDecision(
        decision="promote",
        reason=f"Canary ({canary_avg}) is within {REGRESSION_THRESHOLD_POINTS} points of stable ({stable_avg}).",
        stable_avg_score=stable_avg, canary_avg_score=canary_avg,
        stable_sample_size=len(stable_samples), canary_sample_size=len(canary_samples),
    )


def trigger_rollback(reason: str) -> dict:
    """Record an automated rollback event. In a real deployment this is
    also where you'd call the Argo Rollouts API (or let the
    AnalysisRun's own abort action do it) to flip traffic back to 100%
    stable — see k8s/rollout/argo-rollout.yaml's analysis step."""
    event = {"reason": reason, "action": "rollback_to_stable"}
    _rollback_log.append(event)
    record_rollback(reason="quality_regression")
    return event


def rollback_log() -> list[dict]:
    return list(_rollback_log)

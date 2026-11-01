"""Alert rules — inherited base. Checks model mismatch, cost, eval drop,
and drift for the serving (stable) variant. Module 8's quality_gate.py is
a SEPARATE, purpose-built check comparing canary against stable — it is
not folded into this general-purpose alert list, because a canary
regression needs a rollback decision, not just a logged alert."""

from src.observability import drift
from src.observability.online_eval import rolling_average_score

COST_CEILING_USD_PER_CALL = 0.05

_alerts: list[dict] = []


def observe_and_alert(requested_model: str, served_model: str, cost_usd: float,
                       recommendation_note: str, service_sequence: list[str], variant: str = "stable") -> list[dict]:
    fired = []

    if requested_model != served_model:
        fired.append({"alert": "model_version_mismatch",
                       "detail": f"Requested {requested_model} but served {served_model}", "variant": variant})

    if cost_usd > COST_CEILING_USD_PER_CALL:
        fired.append({"alert": "cost_ceiling_exceeded",
                       "detail": f"Single call cost ${cost_usd:.4f}, ceiling ${COST_CEILING_USD_PER_CALL}", "variant": variant})

    drift_result = drift.observe(recommendation_note, service_sequence)
    if drift_result.get("baseline_ready") and (
        drift_result.get("narrative_drift_flagged") or drift_result.get("tool_mix_drift_flagged")
    ):
        fired.append({"alert": "narrative_or_service_mix_drift", "detail": drift_result, "variant": variant})

    avg = rolling_average_score(variant=variant)
    if avg is not None and avg < 3.0:
        fired.append({"alert": "eval_score_drop", "detail": f"Rolling average eval score dropped to {avg}", "variant": variant})

    _alerts.extend(fired)
    return fired


def recent_alerts(limit: int = 30) -> list[dict]:
    return list(_alerts[-limit:])


def clear_alerts() -> None:
    _alerts.clear()

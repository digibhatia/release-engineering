"""
FastAPI app for Sakh. Separated from agent orchestration (src/agent/),
business-logic services (src/services/), and release engineering
(src/release/) entirely — this file only translates HTTP requests into
calls against those layers and HTTP responses back.
"""

from fastapi import FastAPI, HTTPException

from src.agent.orchestrator import run_underwriting_session
from src.observability import alerting, feedback, online_eval, drift
from src.release import model_registry, quality_gate, promotion
from src.data.mock_store import APPLICANTS, TENANT_REGISTRY

app = FastAPI(title="Sakh — Credit Underwriting Agent with M8 Release Engineering")


@app.get("/applicants")
def list_applicants():
    return {"applicants": list(APPLICANTS.keys())}


@app.get("/underwrite")
def underwrite(applicant_id: str, environment: str = "dev", tenant_id: str | None = None,
                canary_traffic_pct: float = 10.0, shadow: bool = False):
    if applicant_id not in APPLICANTS:
        raise HTTPException(status_code=404, detail=f"Unknown applicant_id {applicant_id}")
    try:
        return run_underwriting_session(
            applicant_id, environment=environment, tenant_id=tenant_id,
            canary_traffic_pct=canary_traffic_pct, shadow=shadow, verbose=False,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc))


# ---- Module 8: release engineering ----
@app.get("/release/manifest")
def release_manifest(environment: str = "dev"):
    env_manifest = model_registry.RELEASE_MANIFEST.get(environment)
    if env_manifest is None:
        raise HTTPException(status_code=404, detail=f"Unknown environment {environment}")
    return {"environment": environment, "manifest": env_manifest}


@app.get("/release/integrity")
def release_integrity(environment: str = "dev"):
    """"The update you did not deploy" check — flags a prompt file whose
    on-disk content no longer matches the checksum that was promoted."""
    return {"findings": model_registry.verify_deployment_integrity(environment)}


@app.get("/release/quality-gate")
def release_quality_gate():
    decision = quality_gate.evaluate_quality_gate()
    return {
        "decision": decision.decision,
        "reason": decision.reason,
        "stable_avg_score": decision.stable_avg_score,
        "canary_avg_score": decision.canary_avg_score,
        "stable_sample_size": decision.stable_sample_size,
        "canary_sample_size": decision.canary_sample_size,
    }


@app.get("/release/rollback-log")
def release_rollback_log():
    return {"rollbacks": quality_gate.rollback_log()}


@app.post("/release/promote")
def release_promote(from_environment: str, to_environment: str, variant: str = "canary"):
    result = promotion.promote(from_environment, to_environment, variant)
    if not result.allowed:
        raise HTTPException(status_code=409, detail=result.reason)
    return {"allowed": result.allowed, "reason": result.reason}


@app.get("/release/tenants")
def release_tenants():
    return {"tenants": TENANT_REGISTRY}


# ---- inherited endpoints ----
@app.get("/eval/recent")
def eval_recent(variant: str | None = None):
    return {"recent": online_eval.recent_judged(variant), "rolling_average_score": online_eval.rolling_average_score(variant)}


@app.get("/drift/status")
def drift_status():
    return drift.status()


@app.post("/drift/reset-baseline")
def drift_reset():
    drift.reset_baseline()
    return {"reset": True}


@app.get("/alerts")
def alerts():
    return {"alerts": alerting.recent_alerts()}


@app.post("/alerts/clear")
def clear_alerts():
    alerting.clear_alerts()
    return {"cleared": True}


@app.post("/feedback")
def submit_feedback(underwriting_id: str, rating: str, note: str = ""):
    return feedback.record_feedback(underwriting_id, rating, note)


@app.get("/annotation-queue")
def annotation_queue():
    return {"queue": feedback.annotation_queue()}

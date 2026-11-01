"""
Environment promotion, secrets/key rotation, and multi-tenant isolation
— Module 8.

Three separate concerns, each with its own function group below:

1. PROMOTION — moving a pinned (prompt_version, model) config from one
   environment to the next (dev -> staging -> prod) only after the
   quality gate for the SOURCE environment says "promote" and the
   source's own deployment-integrity check is clean. This mirrors a
   real CI/CD pipeline's environment-gating (see
   .github/workflows/ci-cd-quality-gate.yml's `promote` job, which calls
   the equivalent of this function between each environment stage).

2. SECRETS / KEY ROTATION — this repo never stores a real API key; it
   reads one from an environment variable whose NAME is resolved per
   tenant (see TENANT_REGISTRY in src/data/mock_store.py). What this
   module adds on top of "read an env var" is rotation bookkeeping: when
   a key was last rotated, and whether it's overdue — the operational
   half of key management that a bare `os.environ.get()` call never
   represents.

3. MULTI-TENANT ISOLATION — Lloyds Retail Lending and Lloyds Business
   Banking are modeled as separate tenants sharing this one deployment.
   enforce_tenant_isolation() is the one place that check happens,
   called from the orchestration layer before any cross-tenant data
   access is even attempted, so an isolation bug is a loud exception at
   the boundary, not a silent leak three calls deep.
"""

import os
import time
from dataclasses import dataclass

from src.release import model_registry
from src.release.quality_gate import evaluate_quality_gate
from src.data.mock_store import TENANT_REGISTRY

ENVIRONMENT_ORDER = ["dev", "staging", "prod"]

# Rotation bookkeeping — in a real deployment this would live in a
# secrets manager (AWS Secrets Manager, Vault, Kubernetes External
# Secrets) and be read, not hand-maintained here. Modeled in-memory for
# the lab.
_rotation_log: dict[str, float] = {}
MAX_SECRET_AGE_DAYS = 90


# ---- 1. environment promotion ----

@dataclass
class PromotionResult:
    allowed: bool
    reason: str
    from_environment: str
    to_environment: str


def promote(from_environment: str, to_environment: str, variant: str = "canary") -> PromotionResult:
    """
    Gate a promotion of `variant`'s pin from from_environment to
    to_environment. Requires: (a) environments are adjacent in
    ENVIRONMENT_ORDER (no skipping staging straight to prod), (b) the
    quality gate for the variant currently says "promote", and (c) the
    source environment's deployment-integrity check is clean (no
    undeployed drift — see model_registry.verify_deployment_integrity).
    Does not mutate RELEASE_MANIFEST itself here — in the real pipeline
    that write happens to the config store/Git, which model_registry.py
    would then read on next resolution; that write step is represented
    by returning the decision rather than performed in-process, since
    this is a gate, not a deploy mechanism.
    """
    try:
        from_idx = ENVIRONMENT_ORDER.index(from_environment)
        to_idx = ENVIRONMENT_ORDER.index(to_environment)
    except ValueError:
        return PromotionResult(False, "Unknown environment name.", from_environment, to_environment)

    if to_idx != from_idx + 1:
        return PromotionResult(
            False, f"Cannot promote directly from {from_environment} to {to_environment} — "
                   f"environments must be promoted in order: {' -> '.join(ENVIRONMENT_ORDER)}.",
            from_environment, to_environment,
        )

    integrity = model_registry.verify_deployment_integrity(from_environment)
    drifted = [f for f in integrity if not f["matches_pin"]]
    if drifted:
        return PromotionResult(
            False, f"{from_environment} has undeployed drift on: "
                   f"{[f['variant'] for f in drifted]} — fix before promoting.",
            from_environment, to_environment,
        )

    gate = evaluate_quality_gate()
    if gate.decision != "promote":
        return PromotionResult(
            False, f"Quality gate for {from_environment} says '{gate.decision}', not 'promote': {gate.reason}",
            from_environment, to_environment,
        )

    return PromotionResult(True, f"Promotion of {variant} from {from_environment} to {to_environment} is cleared.",
                            from_environment, to_environment)


# ---- 2. secrets / key rotation ----

def resolve_secret(tenant_id: str) -> str:
    """Look up the OpenAI API key for this tenant by its registered
    secret-reference NAME, then read that env var. Never hardcodes or
    logs the key value itself."""
    tenant = TENANT_REGISTRY.get(tenant_id)
    if tenant is None:
        raise KeyError(f"Unknown tenant_id {tenant_id!r}")
    secret_ref = tenant["secret_ref"]
    value = os.environ.get(secret_ref) or os.environ.get("OPENAI_API_KEY")
    if not value:
        raise RuntimeError(f"Secret {secret_ref!r} is not set for tenant {tenant_id!r} "
                            f"(and no OPENAI_API_KEY fallback either).")
    return value


def mark_rotated(secret_ref: str) -> None:
    _rotation_log[secret_ref] = time.time()


def is_rotation_overdue(secret_ref: str, max_age_days: int = MAX_SECRET_AGE_DAYS) -> dict:
    last_rotated = _rotation_log.get(secret_ref)
    if last_rotated is None:
        return {"secret_ref": secret_ref, "overdue": True, "reason": "never rotated (no record)"}
    age_days = (time.time() - last_rotated) / 86400
    return {"secret_ref": secret_ref, "overdue": age_days > max_age_days, "age_days": round(age_days, 1)}


# ---- 3. multi-tenant isolation ----

def enforce_tenant_isolation(request_tenant_id: str, resource_tenant_id: str) -> None:
    """Raise if a request made on behalf of one tenant is about to touch
    a resource (an applicant record, a cost/eval rollup, a secret) that
    belongs to a different tenant. Called at the orchestration boundary
    — before any service call runs, not after."""
    if request_tenant_id != resource_tenant_id:
        raise PermissionError(
            f"Tenant isolation violation: request is scoped to tenant "
            f"{request_tenant_id!r} but the resource belongs to tenant {resource_tenant_id!r}."
        )


def get_tenant_config(tenant_id: str) -> dict:
    tenant = TENANT_REGISTRY.get(tenant_id)
    if tenant is None:
        raise KeyError(f"Unknown tenant_id {tenant_id!r}")
    return tenant

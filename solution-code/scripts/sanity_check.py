"""Quick, no-API-key sanity check that the repo's modules import cleanly
and the Module 8 release-engineering logic behaves correctly. Run before
anything that needs a live OPENAI_API_KEY."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main():
    from src.agent import pricing, llm_provider  # noqa: F401
    from src.observability import otel_setup, conventions, metrics  # noqa: F401
    from src.services import applicant_profile_service, credit_assessment_service, policy_service
    from src.release import model_registry, rollout_controller, quality_gate, promotion
    from src.data import mock_store

    # Deployment integrity: on a clean checkout, pinned prompt checksums
    # must match the files on disk.
    findings = model_registry.verify_deployment_integrity("dev")
    assert findings, "expected at least one pinned variant for dev"
    for f in findings:
        assert f["matches_pin"], f"deployment drift detected unexpectedly: {f}"
    print(f"[ok] deployment integrity clean for dev: {[f['variant'] for f in findings]}")

    # Rollout routing is deterministic per route_key.
    v1 = rollout_controller.decide_variant("APP-30027", canary_traffic_pct=50)
    v2 = rollout_controller.decide_variant("APP-30027", canary_traffic_pct=50)
    assert v1 == v2
    print(f"[ok] rollout_controller routing is deterministic: APP-30027 -> {v1}")

    # Policy service produces a decision hint.
    affordability = credit_assessment_service.compute_affordability("APP-30027")
    assert affordability["post_loan_debt_to_income_pct"] > 0
    policy = policy_service.check_policy_compliance("APP-30027")
    assert policy["decision_hint"] in ("approve", "refer", "decline")
    print(f"[ok] policy_service decision_hint for APP-30027: {policy['decision_hint']}")

    # Tenant isolation enforcement.
    try:
        promotion.enforce_tenant_isolation("lloyds-retail", "lloyds-business-banking")
        raise AssertionError("expected PermissionError for cross-tenant access")
    except PermissionError:
        print("[ok] tenant isolation blocks cross-tenant access")

    print("\nAll imports and sanity checks passed. Repo is ready.")


if __name__ == "__main__":
    main()

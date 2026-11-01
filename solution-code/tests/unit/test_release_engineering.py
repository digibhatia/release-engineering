"""
Deterministic tests — no OPENAI_API_KEY / network needed. Covers Module
8's release-engineering logic (version pinning/drift detection, canary
routing determinism, quality-gate decisioning, tenant isolation) plus
the underlying policy/affordability business logic.

Run: pytest tests/unit/test_release_engineering.py -v
"""

import pytest

from src.release import model_registry, rollout_controller, promotion
from src.release.quality_gate import GateDecision
from src.services.credit_assessment_service import compute_affordability
from src.services.policy_service import check_policy_compliance


def test_deployment_integrity_clean_on_checkout():
    findings = model_registry.verify_deployment_integrity("dev")
    assert findings
    assert all(f["matches_pin"] for f in findings)


def test_deployment_integrity_detects_undeployed_edit(tmp_path, monkeypatch):
    """Simulate "the update you did not deploy": edit the pinned prompt
    file's content without updating RELEASE_MANIFEST's checksum, and
    confirm verify_deployment_integrity() flags the mismatch."""
    import src.release.model_registry as mr

    original_read = mr._read_prompt_file
    monkeypatch.setattr(mr, "_read_prompt_file", lambda version: original_read(version) + "\nUNDEPLOYED EDIT")

    findings = mr.verify_deployment_integrity("dev")
    assert any(not f["matches_pin"] for f in findings), "expected drift to be detected after an undeployed edit"


def test_rollout_controller_routing_is_deterministic():
    results = {rollout_controller.decide_variant("APP-30027", canary_traffic_pct=50) for _ in range(20)}
    assert len(results) == 1, "same route_key must always resolve to the same variant"


def test_rollout_controller_zero_percent_canary_is_always_stable():
    for route_key in ["APP-30010", "APP-30027", "APP-30054", "anything"]:
        assert rollout_controller.decide_variant(route_key, canary_traffic_pct=0) == "stable"


def test_quality_gate_holds_with_insufficient_samples():
    from src.release import quality_gate
    quality_gate._rollback_log.clear()
    import src.observability.online_eval as oe
    oe._RECENT_JUDGED.clear()

    decision = quality_gate.evaluate_quality_gate()
    assert decision.decision == "hold"


def test_quality_gate_promotes_when_canary_matches_stable():
    from src.release import quality_gate
    import src.observability.online_eval as oe
    oe._RECENT_JUDGED.clear()
    quality_gate._rollback_log.clear()

    for _ in range(6):
        oe._RECENT_JUDGED.append({"score": 4, "reason": "ok", "verdict": "pass", "variant": "stable"})
        oe._RECENT_JUDGED.append({"score": 4, "reason": "ok", "verdict": "pass", "variant": "canary"})

    decision = quality_gate.evaluate_quality_gate()
    assert decision.decision == "promote"


def test_quality_gate_rolls_back_on_regression():
    from src.release import quality_gate
    import src.observability.online_eval as oe
    oe._RECENT_JUDGED.clear()
    quality_gate._rollback_log.clear()

    for _ in range(6):
        oe._RECENT_JUDGED.append({"score": 5, "reason": "ok", "verdict": "pass", "variant": "stable"})
        oe._RECENT_JUDGED.append({"score": 2, "reason": "bad", "verdict": "fail", "variant": "canary"})

    decision = quality_gate.evaluate_quality_gate()
    assert decision.decision == "rollback"
    assert quality_gate.rollback_log(), "expected a rollback event to be logged"


def test_promotion_requires_adjacent_environments():
    result = promotion.promote("dev", "prod", variant="canary")
    assert not result.allowed
    assert "order" in result.reason.lower()


def test_tenant_isolation_blocks_cross_tenant_access():
    with pytest.raises(PermissionError):
        promotion.enforce_tenant_isolation("lloyds-retail", "lloyds-business-banking")


def test_tenant_isolation_allows_matching_tenant():
    promotion.enforce_tenant_isolation("lloyds-retail", "lloyds-retail")  # should not raise


def test_policy_decision_hint_matches_affordability():
    affordability = compute_affordability("APP-30027")
    policy = check_policy_compliance("APP-30027")
    assert policy["decision_hint"] in ("approve", "refer", "decline")
    if affordability["post_loan_debt_to_income_pct"] > 45.0:
        assert policy["decision_hint"] in ("refer", "decline")

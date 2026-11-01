"""Underwriting policy compliance checks — pure business logic. Called
by src/agent/orchestrator.py."""

from src.data.mock_store import APPLICANTS, POLICY_THRESHOLDS
from src.services.credit_assessment_service import compute_affordability


def check_policy_compliance(applicant_id: str) -> dict:
    """
    Evaluate an applicant against the firm's underwriting policy
    thresholds: max post-loan DTI, minimum credit bureau score, and max
    loan-to-annual-income multiple. Returns a decision_hint of "approve",
    "refer", or "decline" — the FINAL recommendation is still drafted by
    the underwriting sub-agent in prose; this is a deterministic,
    auditable policy check that the sub-agent's note must be consistent
    with.
    """
    applicant = APPLICANTS.get(applicant_id)
    if applicant is None:
        return {"error": f"No applicant found with id {applicant_id}"}

    affordability = compute_affordability(applicant_id)
    score = applicant["credit_bureau_score"]

    violations = []
    if affordability["post_loan_debt_to_income_pct"] > POLICY_THRESHOLDS["max_debt_to_income_pct"]:
        violations.append("post_loan_dti_exceeds_policy_max")
    if score < POLICY_THRESHOLDS["min_credit_bureau_score"]:
        violations.append("credit_bureau_score_below_policy_floor")
    if affordability["loan_to_annual_income_multiple"] > POLICY_THRESHOLDS["max_loan_to_annual_income_multiple"]:
        violations.append("loan_to_income_multiple_exceeds_policy_max")

    if "credit_bureau_score_below_policy_floor" in violations:
        decision_hint = "decline"
    elif violations:
        decision_hint = "refer"
    elif score < POLICY_THRESHOLDS["refer_band_credit_bureau_score"]:
        decision_hint = "refer"
    else:
        decision_hint = "approve"

    return {
        "applicant_id": applicant_id,
        "policy_thresholds": POLICY_THRESHOLDS,
        "violations": violations,
        "decision_hint": decision_hint,
    }

"""Affordability / debt-to-income assessment — pure business logic.
Called by src/agent/orchestrator.py."""

from src.data.mock_store import APPLICANTS


def compute_affordability(applicant_id: str) -> dict:
    """Compute debt-to-income ratio, new-loan monthly instalment (flat
    estimate), and post-loan DTI for an applicant."""
    applicant = APPLICANTS.get(applicant_id)
    if applicant is None:
        return {"error": f"No applicant found with id {applicant_id}"}

    income = applicant["monthly_income_gbp"]
    existing_debt = applicant["existing_monthly_debt_gbp"]
    loan_amount = applicant["requested_loan_amount_gbp"]
    tenure_months = applicant["requested_tenure_months"]

    # Flat estimate for lab purposes — no interest-rate amortization model.
    estimated_new_instalment = round(loan_amount / tenure_months, 2)

    current_dti_pct = round(100 * existing_debt / income, 2)
    post_loan_dti_pct = round(100 * (existing_debt + estimated_new_instalment) / income, 2)
    annual_income = income * 12
    loan_to_annual_income_multiple = round(loan_amount / annual_income, 2)

    return {
        "applicant_id": applicant_id,
        "monthly_income_gbp": income,
        "current_debt_to_income_pct": current_dti_pct,
        "estimated_new_instalment_gbp": estimated_new_instalment,
        "post_loan_debt_to_income_pct": post_loan_dti_pct,
        "loan_to_annual_income_multiple": loan_to_annual_income_multiple,
    }

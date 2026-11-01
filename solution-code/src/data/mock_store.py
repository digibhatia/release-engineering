"""
Mock data for the credit/loan underwriting scenario. Lloyds Lending
(training scenario) — three applicants and the firm's underwriting
policy thresholds. No real data.
"""

APPLICANTS = {
    "APP-30010": {
        "applicant_id": "APP-30010",
        "name": "K. Osei",
        "employment_type": "salaried",
        "monthly_income_gbp": 4200.00,
        "existing_monthly_debt_gbp": 650.00,
        "requested_loan_amount_gbp": 18000.00,
        "requested_tenure_months": 48,
        "credit_bureau_score": 712,
        "tenant_id": "lloyds-retail",
    },
    "APP-30027": {
        "applicant_id": "APP-30027",
        "name": "D. Marchetti",
        "employment_type": "self_employed",
        "monthly_income_gbp": 3100.00,
        "existing_monthly_debt_gbp": 1450.00,
        "requested_loan_amount_gbp": 25000.00,
        "requested_tenure_months": 60,
        "credit_bureau_score": 588,
        "tenant_id": "lloyds-retail",
    },
    "APP-30054": {
        "applicant_id": "APP-30054",
        "name": "H. Prajapati",
        "employment_type": "salaried",
        "monthly_income_gbp": 5600.00,
        "existing_monthly_debt_gbp": 400.00,
        "requested_loan_amount_gbp": 12000.00,
        "requested_tenure_months": 36,
        "credit_bureau_score": 745,
        "tenant_id": "lloyds-business-banking",
    },
}

# Firm-wide underwriting policy thresholds — used by policy_service.py,
# not by the model directly.
POLICY_THRESHOLDS = {
    "max_debt_to_income_pct": 45.0,
    "min_credit_bureau_score": 620,
    "max_loan_to_annual_income_multiple": 4.0,
    "refer_band_credit_bureau_score": 650,  # below this but above the hard floor -> refer, not auto-decline
}

# Per-tenant isolation reference — which business unit's requests may use
# which API-key placeholder. Read by src/release/promotion.py.
TENANT_REGISTRY = {
    "lloyds-retail": {"display_name": "Lloyds Retail Lending", "secret_ref": "LLOYDS_RETAIL_OPENAI_KEY"},
    "lloyds-business-banking": {"display_name": "Lloyds Business Banking", "secret_ref": "LLOYDS_BIZ_OPENAI_KEY"},
}

"""Applicant profile lookup — pure business logic, no agent or
orchestration awareness. Called by src/agent/orchestrator.py."""

from src.data.mock_store import APPLICANTS


def lookup_applicant_profile(applicant_id: str) -> dict:
    """Return the application-intake fields for an applicant_id."""
    profile = APPLICANTS.get(applicant_id)
    if profile is None:
        return {"error": f"No applicant found with id {applicant_id}"}
    return profile

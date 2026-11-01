"""Underwriting-recommendation-note drafting — a second, separate model
call, delegated once the main session has gathered evidence. This is the
ONE call site in the repo whose prompt and model are resolved through
src/release/model_registry.py rather than hardcoded — it's the piece
Module 8's version pinning, shadow/canary routing, and quality gate are
all built around."""

from typing import Optional

from src.agent.llm_provider import chat_raw
from src.observability.otel_setup import get_tracer
from src.release.model_registry import get_pinned_config


def run_underwriting_subagent(applicant_id: str, environment: str, variant: str,
                               evidence: Optional[dict] = None) -> dict:
    tracer = get_tracer("sakh.subagent")
    with tracer.start_as_current_span("underwriting_subagent") as span:
        span.set_attribute("sakh.subagent.applicant_id", applicant_id)
        span.set_attribute("sakh.subagent.environment", environment)
        span.set_attribute("sakh.subagent.variant", variant)

        pin = get_pinned_config(environment, variant)
        span.set_attribute("sakh.subagent.prompt_version", pin.prompt_version)
        span.set_attribute("sakh.subagent.deployment_matches_pin", pin.deployment_matches_pin)

        evidence_text = f"Evidence gathered for this application:\n{evidence}"

        result = chat_raw(
            messages=[
                {"role": "system", "content": pin.prompt_text},
                {"role": "user", "content": f"applicant_id: {applicant_id}\n\n{evidence_text}"},
            ],
            model=pin.model,
            variant=variant,
            prompt_version=pin.prompt_version,
        )
        span.set_attribute("sakh.subagent.cost_usd", result.cost_usd)

        return {
            "applicant_id": applicant_id,
            "variant": variant,
            "prompt_version": pin.prompt_version,
            "deployment_matches_pin": pin.deployment_matches_pin,
            "recommendation_note": result.content,
            "requested_model": result.requested_model,
            "served_model": result.served_model,
            "duration_ms": result.duration_ms,
            "cost_usd": result.cost_usd,
        }

"""
The full pipeline, one underwriting session at a time:
  tenant isolation check -> tool loop (src/services/) -> variant routing
  (src/release/rollout_controller.py) -> underwriting sub-agent
  delegation, under shadow OR canary routing -> online eval (tagged by
  variant) -> drift/alerting

Every module built across M2-M8 is called from exactly one place: here.
"""

import json
import uuid

from src.agent.llm_provider import chat_raw
from src.agent.underwriting_subagent import run_underwriting_subagent
from src.observability.otel_setup import get_tracer
from src.observability import metrics, online_eval, alerting
from src.release.rollout_controller import decide_variant, run_shadow
from src.release.promotion import enforce_tenant_isolation
from src.services.applicant_profile_service import lookup_applicant_profile
from src.services.credit_assessment_service import compute_affordability
from src.services.policy_service import check_policy_compliance
from src.data.mock_store import APPLICANTS

SYSTEM_PROMPT = """You are Sakh, an underwriting assistant for Lloyds
Lending (training scenario). Given an applicant_id, use the available
tools to gather evidence: the applicant's profile, an affordability
(debt-to-income) assessment, and a policy compliance check. Summarize
your findings in a short internal note once done — a specialist will
draft the formal underwriting recommendation from your findings.
"""

MAX_TURNS = 6

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_applicant_profile",
            "description": "Look up an applicant's intake profile (income, existing debt, requested loan, credit bureau score) by applicant_id.",
            "parameters": {
                "type": "object",
                "properties": {"applicant_id": {"type": "string", "description": "e.g. APP-30027"}},
                "required": ["applicant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_affordability",
            "description": "Compute debt-to-income ratio and loan-to-income multiple for an applicant.",
            "parameters": {
                "type": "object",
                "properties": {"applicant_id": {"type": "string"}},
                "required": ["applicant_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_policy_compliance",
            "description": "Run the firm's underwriting policy checks (DTI cap, credit score floor, loan-to-income cap) for an applicant.",
            "parameters": {
                "type": "object",
                "properties": {"applicant_id": {"type": "string"}},
                "required": ["applicant_id"],
            },
        },
    },
]

TOOL_FUNCTIONS = {
    "lookup_applicant_profile": lookup_applicant_profile,
    "compute_affordability": compute_affordability,
    "check_policy_compliance": check_policy_compliance,
}


def _gather_evidence(applicant_id: str, verbose: bool) -> tuple[dict, list, float]:
    """The tool loop: gather KYC/affordability/policy evidence. Shared by
    every variant — ONLY the final recommendation-note drafting call
    differs by release variant (see run_underwriting_session)."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Underwrite applicant_id: {applicant_id}"},
    ]
    call_log = []
    gathered_evidence = {}
    total_cost = 0.0

    for turn in range(1, MAX_TURNS + 1):
        result = chat_raw(messages, tools=TOOL_SCHEMAS)
        total_cost += result.cost_usd
        metrics.record_underwriting_turn(result.served_model, result.duration_ms, result.cost_usd, variant="stable")

        call_log.append({
            "turn": turn, "finish_reason": result.finish_reason,
            "served_model": result.served_model, "cost_usd": round(result.cost_usd, 6),
            "tool_calls_requested": [tc.name for tc in result.tool_calls],
        })
        if verbose:
            print(f"[turn {turn}] tool_calls={[tc.name for tc in result.tool_calls]} cost_usd={result.cost_usd:.6f}")

        if result.finish_reason == "tool_calls" and result.tool_calls:
            messages.append({
                "role": "assistant", "content": result.content,
                "tool_calls": [{"id": tc.id, "type": "function",
                                 "function": {"name": tc.name, "arguments": tc.arguments}}
                                for tc in result.tool_calls],
            })
            for tc in result.tool_calls:
                fn = TOOL_FUNCTIONS.get(tc.name)
                try:
                    args = json.loads(tc.arguments)
                    tool_result = fn(**args) if fn else {"error": f"unknown tool {tc.name}"}
                except Exception as exc:  # noqa: BLE001
                    tool_result = {"error": str(exc)}
                gathered_evidence[tc.name] = tool_result
                messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(tool_result)})
            continue
        break

    return gathered_evidence, call_log, total_cost


def run_underwriting_session(applicant_id: str, environment: str = "dev", tenant_id: str | None = None,
                              canary_traffic_pct: float = 10.0, shadow: bool = False,
                              verbose: bool = True) -> dict:
    tracer = get_tracer("sakh.orchestrator")
    underwriting_id = str(uuid.uuid4())[:8]

    with tracer.start_as_current_span("underwriting_session") as parent_span:
        parent_span.set_attribute("sakh.underwriting_id", underwriting_id)
        parent_span.set_attribute("sakh.applicant_id", applicant_id)
        parent_span.set_attribute("sakh.environment", environment)

        applicant = APPLICANTS.get(applicant_id)
        if applicant is None:
            return {"error": f"No applicant found with id {applicant_id}"}

        if tenant_id is not None:
            enforce_tenant_isolation(tenant_id, applicant["tenant_id"])

        gathered_evidence, call_log, tool_loop_cost = _gather_evidence(applicant_id, verbose)
        total_cost = tool_loop_cost

        if shadow:
            # SHADOW pattern: stable serves the user; canary runs in
            # parallel purely for comparison logging.
            comparison = run_shadow(
                route_key=applicant_id,
                stable_fn=lambda: run_underwriting_subagent(applicant_id, environment, "stable", gathered_evidence),
                shadow_fn=lambda: run_underwriting_subagent(applicant_id, environment, "canary", gathered_evidence),
            )
            recommendation = comparison.served_output
            served_variant = "stable"
            if comparison.shadow_output:
                total_cost += comparison.shadow_output.get("cost_usd", 0.0)
                online_eval.maybe_grade(gathered_evidence, comparison.shadow_output["recommendation_note"], variant="canary")
        else:
            # CANARY pattern: a deterministic slice of real traffic is
            # actually served by the canary variant.
            served_variant = decide_variant(applicant_id, canary_traffic_pct=canary_traffic_pct)
            recommendation = run_underwriting_subagent(applicant_id, environment, served_variant, gathered_evidence)

        total_cost += recommendation.get("cost_usd", 0.0)
        metrics.record_subagent_duration(recommendation.get("duration_ms", 0.0), variant=served_variant)

        eval_result = online_eval.maybe_grade(gathered_evidence, recommendation["recommendation_note"], variant=served_variant)

        fired_alerts = alerting.observe_and_alert(
            requested_model=recommendation.get("requested_model", ""),
            served_model=recommendation.get("served_model", ""),
            cost_usd=total_cost,
            recommendation_note=recommendation["recommendation_note"],
            service_sequence=list(gathered_evidence.keys()),
            variant=served_variant,
        )

        return {
            "underwriting_id": underwriting_id,
            "applicant_id": applicant_id,
            "environment": environment,
            "served_variant": served_variant,
            "gathered_evidence": gathered_evidence,
            "recommendation": recommendation,
            "total_cost_usd": round(total_cost, 6),
            "call_log": call_log,
            "eval_result": eval_result,
            "alerts_fired": fired_alerts,
        }

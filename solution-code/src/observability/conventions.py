"""
OpenTelemetry GenAI semantic convention attribute names, plus this repo's
own sakh.* namespace for everything the standard doesn't cover.
Centralized here so every module spells an attribute name the same way.
"""

# --- standard GenAI semantic conventions ---
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"

# --- cost ---
SAKH_COST_USD = "sakh.cost_usd"

# --- eval / drift / alerting (inherited base) ---
SAKH_EVAL_SAMPLED = "sakh.eval.sampled"
SAKH_EVAL_SCORE = "sakh.eval.score"
SAKH_EVAL_VERDICT = "sakh.eval.verdict"
SAKH_DRIFT_SCORE = "sakh.drift.score"
SAKH_DRIFT_FLAGGED = "sakh.drift.flagged"

# --- Module 8: release engineering ---
SAKH_RELEASE_VARIANT = "sakh.release.variant"            # "stable" | "canary" | "shadow"
SAKH_RELEASE_PROMPT_VERSION = "sakh.release.prompt_version"
SAKH_RELEASE_MODEL_PIN = "sakh.release.model_pin"
SAKH_RELEASE_TENANT_ID = "sakh.release.tenant_id"
SAKH_RELEASE_ENVIRONMENT = "sakh.release.environment"
SAKH_RELEASE_GATE_DECISION = "sakh.release.gate_decision"  # "promote" | "hold" | "rollback"


def safe_prompt_attribute(text: str, max_len: int = 300) -> str:
    """Truncate + flag long prompt text before it goes into a span attribute."""
    if text is None:
        return ""
    text = str(text)
    return text if len(text) <= max_len else text[:max_len] + "...[truncated]"

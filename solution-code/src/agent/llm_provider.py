"""
The model-call primitive. One OTel span per call, token usage and cost
recorded as attributes, plus — new for Module 8 — the release variant
(stable/canary/shadow), prompt version, and model pin that produced this
specific response, so every span can be traced back to exactly which
release config served it.

NOTE: .env is loaded explicitly, by path, before anything reads
OPENAI_API_KEY.
"""

import os
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv
from openai import OpenAI, RateLimitError

from src.observability.otel_setup import get_tracer
from src.observability.conventions import (
    GEN_AI_SYSTEM, GEN_AI_OPERATION_NAME, GEN_AI_REQUEST_MODEL,
    GEN_AI_RESPONSE_MODEL, GEN_AI_RESPONSE_FINISH_REASONS,
    GEN_AI_USAGE_INPUT_TOKENS, GEN_AI_USAGE_OUTPUT_TOKENS,
    SAKH_COST_USD, SAKH_RELEASE_VARIANT, SAKH_RELEASE_PROMPT_VERSION,
    SAKH_RELEASE_MODEL_PIN, safe_prompt_attribute,
)
from src.agent.pricing import estimate_cost_usd

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(dotenv_path=ENV_FILE)

DEFAULT_MODEL = "gpt-4o-mini"
REQUEST_TIMEOUT_SECONDS = 20.0
MAX_RETRIES = 3

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(f"OPENAI_API_KEY is not set. Check your .env file at: {ENV_FILE}")
        _client = OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT_SECONDS)
    return _client


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass
class ModelCallResult:
    content: Optional[str]
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = ""
    requested_model: str = ""
    served_model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: float = 0.0
    retries: int = 0


def chat_raw(messages: list[dict], tools: Optional[list] = None,
             model: str = DEFAULT_MODEL, temperature: Optional[float] = None,
             variant: str = "stable", prompt_version: str = "unversioned") -> ModelCallResult:
    tracer = get_tracer("sakh.model")
    client = _get_client()

    with tracer.start_as_current_span("model_call") as span:
        span.set_attribute(GEN_AI_SYSTEM, "openai")
        span.set_attribute(GEN_AI_OPERATION_NAME, "chat")
        span.set_attribute(GEN_AI_REQUEST_MODEL, model)
        span.set_attribute(SAKH_RELEASE_VARIANT, variant)
        span.set_attribute(SAKH_RELEASE_PROMPT_VERSION, prompt_version)
        span.set_attribute(SAKH_RELEASE_MODEL_PIN, model)
        if messages:
            last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
            span.set_attribute("gen_ai.prompt.last_user_message", safe_prompt_attribute(last_user))

        kwargs = {"model": model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature

        t0 = time.perf_counter()
        response = None
        retries = 0
        last_exc: Optional[Exception] = None
        while retries <= MAX_RETRIES:
            try:
                response = client.chat.completions.create(**kwargs)
                break
            except RateLimitError as exc:
                last_exc = exc
                retries += 1
                span.set_attribute("sakh.llm_provider.retry_count", retries)
                time.sleep(min(2 ** retries, 8))  # bounded exponential backoff
        if response is None:
            span.set_attribute("sakh.llm_provider.retries_exhausted", True)
            raise RuntimeError(f"chat_raw: exhausted {MAX_RETRIES} retries") from last_exc
        duration_ms = (time.perf_counter() - t0) * 1000

        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", 0) if usage else 0
        output_tokens = getattr(usage, "completion_tokens", 0) if usage else 0
        cost = estimate_cost_usd(response.model, input_tokens, output_tokens)

        span.set_attribute(GEN_AI_RESPONSE_MODEL, response.model)
        span.set_attribute(GEN_AI_RESPONSE_FINISH_REASONS, [choice.finish_reason])
        span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, input_tokens)
        span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, output_tokens)
        span.set_attribute(SAKH_COST_USD, cost)

        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments)
            for tc in (choice.message.tool_calls or [])
        ]

        return ModelCallResult(
            content=choice.message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            requested_model=model,
            served_model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
            retries=retries,
        )

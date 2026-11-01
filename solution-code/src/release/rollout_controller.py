"""
Shadow, canary, and A/B release-pattern routing — Module 8.

Three patterns, in the order a real prompt/model change should move
through them:

1. SHADOW — the new (candidate) variant runs ALONGSIDE the stable
   variant on real traffic, but its output is never served to the user;
   it's only logged for comparison. Zero user-facing risk. This is
   where you'd first put a new prompt version.
2. CANARY — once shadow comparisons look healthy, a small percentage of
   REAL traffic is actually served by the candidate variant, chosen
   deterministically per request so the same request always lands on
   the same variant (useful for debugging a specific case). This is
   where quality_gate.py's automated rollback matters — a canary serves
   real users, so a regression has real impact until it's caught.
3. A/B — a longer-running, larger-split comparison (not just a
   promotion gate) used when the question is "which is better" rather
   than "is the new one safe" — same routing mechanism as canary, just
   used with a different traffic split and a longer observation window.
"""

import hashlib
from dataclasses import dataclass
from typing import Callable


def decide_variant(route_key: str, canary_traffic_pct: float = 10.0) -> str:
    """
    Deterministically route a request to "stable" or "canary" based on a
    stable hash of route_key (e.g. applicant_id or a request id) — the
    SAME route_key always lands on the SAME variant, which matters for
    reproducing a specific user's reported issue. canary_traffic_pct is
    the percentage of route_keys that should land on canary; this
    function makes no network or state calls, so it's cheap to call on
    every request.
    """
    digest = hashlib.sha256(route_key.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100  # 0-99
    return "canary" if bucket < canary_traffic_pct else "stable"


@dataclass
class ShadowComparison:
    route_key: str
    served_variant: str
    served_output: dict
    shadow_variant: str
    shadow_output: dict | None
    shadow_error: str | None = None


def run_shadow(route_key: str, stable_fn: Callable[[], dict], shadow_fn: Callable[[], dict]) -> ShadowComparison:
    """
    Always serve stable_fn()'s result to the caller. ALSO run shadow_fn()
    (the candidate variant) for the SAME request, but never let its
    output reach the user — only return it alongside the served result
    for comparison/logging. A shadow_fn() failure must never break the
    served response, so it's caught and recorded rather than raised.
    """
    served_output = stable_fn()

    shadow_output = None
    shadow_error = None
    try:
        shadow_output = shadow_fn()
    except Exception as exc:  # noqa: BLE001
        shadow_error = str(exc)

    return ShadowComparison(
        route_key=route_key,
        served_variant="stable",
        served_output=served_output,
        shadow_variant="canary",
        shadow_output=shadow_output,
        shadow_error=shadow_error,
    )

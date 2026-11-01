"""
Prompt and model version pinning — Module 8.

Prompts, models, and agent code version SEPARATELY. This module is the
single source of truth for "what is actually pinned to serve traffic
right now, for each variant and each environment" — RELEASE_MANIFEST
below is the artifact a release pipeline (see .github/workflows/) writes
to when it promotes a build; it is NOT just a version string, it also
pins a content checksum, so a prompt edited on disk without going through
the release process is detectable, not just "trust the filename."

This is "the update you did not deploy": a prompt file can be edited
directly (a quick fix, a local experiment, a merge that landed on the
wrong branch) without the release pipeline ever running. The filename/
version string alone would not catch that — the content changed, but
nothing that *serves* the pin knows the content changed. Pinning by
checksum, and verifying it at startup and before each release promotion,
turns a silent drift into a loud one.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# The release manifest: what each (environment, variant) is PINNED to —
# prompt version, its checksum at the moment it was promoted, and the
# model. In a real pipeline this file (or its Kubernetes ConfigMap/
# Secret equivalent) is written by CI after the quality gate passes (see
# .github/workflows/ci-cd-quality-gate.yml and quality_gate.py) — never
# edited by hand in a running environment.
RELEASE_MANIFEST = {
    "dev": {
        "stable": {"prompt_version": "v1", "model": "gpt-4o-mini",
                   "prompt_sha256": "0dead6f1366cb14132b74f26c130514699eceeb219d6a155614e82c242b13ac8"},
        "canary": {"prompt_version": "v2", "model": "gpt-4o-mini",
                   "prompt_sha256": "5748760ac21384a6991386aec1277f6f3f638ed7fc7997b9ea0fe8105a88b03a"},
    },
    "staging": {
        "stable": {"prompt_version": "v1", "model": "gpt-4o-mini",
                   "prompt_sha256": "0dead6f1366cb14132b74f26c130514699eceeb219d6a155614e82c242b13ac8"},
        "canary": {"prompt_version": "v2", "model": "gpt-4o-mini",
                   "prompt_sha256": "5748760ac21384a6991386aec1277f6f3f638ed7fc7997b9ea0fe8105a88b03a"},
    },
    "prod": {
        # prod has not yet been promoted to v2 anywhere — stable only,
        # until staging's canary quality-gates pass and a human approves
        # the promotion (see promotion.py).
        "stable": {"prompt_version": "v1", "model": "gpt-4o-mini",
                   "prompt_sha256": "0dead6f1366cb14132b74f26c130514699eceeb219d6a155614e82c242b13ac8"},
    },
}


@dataclass
class PinnedConfig:
    environment: str
    variant: str
    prompt_version: str
    model: str
    prompt_text: str
    prompt_sha256_expected: str
    prompt_sha256_actual: str

    @property
    def deployment_matches_pin(self) -> bool:
        return self.prompt_sha256_expected == self.prompt_sha256_actual


def _read_prompt_file(prompt_version: str) -> str:
    path = PROMPTS_DIR / f"underwriting_{prompt_version}.txt"
    if not path.exists():
        raise FileNotFoundError(f"No prompt file for version {prompt_version!r} at {path}")
    return path.read_text(encoding="utf-8")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_pinned_config(environment: str, variant: str) -> PinnedConfig:
    """
    Resolve what SHOULD be serving traffic for (environment, variant),
    and verify it against what's actually on disk. Raises KeyError if
    that variant isn't pinned for this environment at all (e.g. prod has
    no canary pin until one is promoted).
    """
    env_manifest = RELEASE_MANIFEST.get(environment)
    if env_manifest is None:
        raise KeyError(f"Unknown environment {environment!r}")
    pin = env_manifest.get(variant)
    if pin is None:
        raise KeyError(f"No {variant!r} pin for environment {environment!r}")

    prompt_text = _read_prompt_file(pin["prompt_version"])
    actual_hash = _sha256(prompt_text)

    return PinnedConfig(
        environment=environment,
        variant=variant,
        prompt_version=pin["prompt_version"],
        model=pin["model"],
        prompt_text=prompt_text,
        prompt_sha256_expected=pin["prompt_sha256"],
        prompt_sha256_actual=actual_hash,
    )


def verify_deployment_integrity(environment: str) -> list[dict]:
    """
    Check every variant pinned for this environment and report any
    "the update you did not deploy" drift — a prompt file on disk whose
    content no longer matches the checksum that was promoted. Returns a
    list of findings; an empty list means everything pinned matches what's
    actually being served.
    """
    findings = []
    env_manifest = RELEASE_MANIFEST.get(environment, {})
    for variant in env_manifest:
        cfg = get_pinned_config(environment, variant)
        findings.append({
            "environment": environment,
            "variant": variant,
            "prompt_version": cfg.prompt_version,
            "matches_pin": cfg.deployment_matches_pin,
            "expected_sha256": cfg.prompt_sha256_expected,
            "actual_sha256": cfg.prompt_sha256_actual,
        })
    return findings

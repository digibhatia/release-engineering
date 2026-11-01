
# Sakh — Credit Underwriting Agent with Module 8 Release Engineering

A working, fully traced credit/loan underwriting assistant for Lloyds
Lending (training scenario), built on the layered repo structure
(`src/agent/`, `src/services/`, `src/observability/`, `src/interfaces/`,
`src/data/`) — plus a new `src/release/` layer implementing Module 8:
continuous delivery for prompts, models, and agent code as three things
that version separately.

This is a **solution** repo (no seeded bugs) — see the companion outline
document for the full architecture, problem/solution framing, a
per-file/per-call walkthrough, and an assignment.

## What Module 8 adds

| Topic | Where |
|---|---|
| Prompt and model version pinning, and "the update you did not deploy" | `src/release/model_registry.py` — pins a checksum, not just a filename, so an edited-but-unpromoted prompt is detectable. |
| Shadow, canary, and A/B release patterns | `src/release/rollout_controller.py` — deterministic canary routing + a shadow-comparison runner. |
| Automated quality-triggered rollback | `src/release/quality_gate.py` — compares canary vs. stable rolling eval scores, NOT error rate. Mirrored in-cluster by `k8s/rollout/analysis-template.yaml`. |
| Environment promotion, secrets/key rotation, multi-tenant isolation | `src/release/promotion.py` — gates dev→staging→prod promotion; tenant-scoped secret resolution; rotation bookkeeping; `enforce_tenant_isolation()`. |
| CI/CD | `.github/workflows/ci-cd-quality-gate.yml` — test → shadow-eval-batch → quality-gate → staged promotion. |
| Kubernetes / Argo Rollouts | `k8s/base/` (plain Deployment), `k8s/rollout/` (canary Rollout + AnalysisTemplate). |

## Scenario

Sakh gathers an applicant's profile, computes affordability (debt-to-
income), and runs the firm's policy checks (DTI cap, credit-score floor,
loan-to-income cap) — all deterministic, auditable business logic in
`src/services/`. It then delegates to an underwriting sub-agent that
drafts a short recommendation note, consistent with the deterministic
policy decision_hint. That sub-agent call is the ONE place in the repo
whose prompt and model are resolved through the release layer rather
than hardcoded — which is exactly the call a bad prompt change would
affect, and exactly the call Module 8's tooling is built to protect.

## Layered structure

| Layer | Folder |
|---|---|
| Agent orchestration | `src/agent/` — model-call primitive, cost calc, sub-agent, orchestration loop |
| Business services | `src/services/` — applicant profile, affordability, policy. No agent/OTel/release awareness. |
| Observability | `src/observability/` — tracing/metrics setup, eval (tagged by release variant), drift, alerting, feedback |
| Release engineering | `src/release/` — version pinning, shadow/canary routing, quality gate, environment promotion |
| Interfaces | `src/interfaces/` — FastAPI app only |
| Data | `src/data/` — mock applicants, policy thresholds, tenant registry |

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in OPENAI_API_KEY (and per-tenant keys)
docker compose up -d   # jaeger, otel-collector, prometheus, grafana
python scripts/sanity_check.py
pytest tests/unit/ -v
python demo.py                           # shadow -> canary -> quality gate decision
python scripts/run_shadow_batch.py --environment dev --n 20   # what CI runs
uvicorn app:app --reload --port 8000
```

Jaeger UI: http://localhost:16686 · Prometheus: http://localhost:9090 · Grafana: http://localhost:3000

## Key endpoints

- `GET /underwrite?applicant_id=APP-30027&shadow=true` — run a session with the canary prompt shadowed.
- `GET /underwrite?applicant_id=APP-30027&canary_traffic_pct=30` — run with 30% of traffic on canary.
- `GET /release/integrity?environment=dev` — "the update you did not deploy" check.
- `GET /release/quality-gate` — current promote/hold/rollback decision.
- `POST /release/promote?from_environment=dev&to_environment=staging` — gated promotion.

## File map

| File | What it does |
|---|---|
| `src/release/model_registry.py` | Version pinning + checksum-based deployment-drift detection |
| `src/release/prompts/underwriting_v{1,2}.txt` | Stable (v1) and candidate canary (v2) prompts |
| `src/release/rollout_controller.py` | Shadow + canary traffic routing |
| `src/release/quality_gate.py` | Quality-regression-triggered rollback decision |
| `src/release/promotion.py` | Environment promotion gate, secret resolution, tenant isolation |
| `src/agent/llm_provider.py` | Model-call primitive (bounded retries, timeout, cost + release attributes) |
| `src/agent/underwriting_subagent.py` | Recommendation-note drafting, resolved via model_registry |
| `src/agent/orchestrator.py` | Tool loop + variant routing + eval + alerting |
| `src/services/applicant_profile_service.py` | Applicant intake lookup |
| `src/services/credit_assessment_service.py` | DTI / affordability calculation |
| `src/services/policy_service.py` | Deterministic policy decision_hint |
| `src/observability/*.py` | Tracing, metrics, eval (variant-tagged), drift, alerting, feedback |
| `src/interfaces/api.py` | FastAPI app |
| `.github/workflows/ci-cd-quality-gate.yml` | Test → shadow-eval → quality-gate → staged promotion |
| `k8s/base/*.yaml` | Plain Deployment/Service/ConfigMap |
| `k8s/rollout/argo-rollout.yaml` | Canary Rollout (20% → 50% → 100%, paused + analyzed at each step) |
| `k8s/rollout/analysis-template.yaml` | PromQL quality-regression check, mirrors `quality_gate.py` |
| `k8s/secrets/secret-example.yaml` | Secret shape + rotation policy (template only) |
| `environments/{dev,staging,prod}.env.example` | Per-environment config, increasingly strict gates |

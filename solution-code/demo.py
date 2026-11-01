"""
Demo runner (needs a real OPENAI_API_KEY — makes live model calls).

Walks through all three release patterns on the same applicant:
  1. shadow  — canary prompt runs silently alongside stable
  2. canary  — a slice of real traffic actually served by canary
  3. quality gate — the promote/hold/rollback decision read off the
     eval scores those sessions just produced

Run: python demo.py
"""

from src.agent.orchestrator import run_underwriting_session
from src.release.quality_gate import evaluate_quality_gate
from src.release import model_registry


def main():
    applicant_id = "APP-30027"  # lower credit score -> more interesting note to compare

    print("=== Deployment integrity (dev) ===")
    for finding in model_registry.verify_deployment_integrity("dev"):
        print(" ", finding)

    print("\n=== Shadow run (canary prompt compared silently) ===")
    for i in range(6):
        outcome = run_underwriting_session(applicant_id, environment="dev", shadow=True, verbose=False)
        print(f"  run {i+1}: served_variant={outcome['served_variant']} cost=${outcome['total_cost_usd']}")

    print("\n=== Canary run (10% of real traffic actually served by canary) ===")
    for i in range(10):
        outcome = run_underwriting_session(applicant_id, environment="dev", canary_traffic_pct=30, verbose=False)
        print(f"  run {i+1}: served_variant={outcome['served_variant']} cost=${outcome['total_cost_usd']}")

    print("\n=== Quality gate decision ===")
    decision = evaluate_quality_gate()
    print(f"  decision={decision.decision}")
    print(f"  reason={decision.reason}")
    print(f"  stable_avg={decision.stable_avg_score} (n={decision.stable_sample_size})  "
          f"canary_avg={decision.canary_avg_score} (n={decision.canary_sample_size})")


if __name__ == "__main__":
    main()

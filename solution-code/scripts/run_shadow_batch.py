"""CI entry point (see .github/workflows/ci-cd-quality-gate.yml's
shadow-eval-batch job): run N shadow sessions against `environment` so
the quality gate has enough judged samples for both variants before the
next job evaluates it. Needs a real OPENAI_API_KEY in CI's environment
secrets."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.agent.orchestrator import run_underwriting_session
from src.data.mock_store import APPLICANTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", default="dev")
    parser.add_argument("--n", type=int, default=20)
    args = parser.parse_args()

    applicant_ids = list(APPLICANTS.keys())
    for i in range(args.n):
        applicant_id = applicant_ids[i % len(applicant_ids)]
        outcome = run_underwriting_session(applicant_id, environment=args.environment, shadow=True, verbose=False)
        print(f"[{i+1}/{args.n}] applicant={applicant_id} served_variant={outcome['served_variant']} "
              f"cost=${outcome['total_cost_usd']}")


if __name__ == "__main__":
    main()

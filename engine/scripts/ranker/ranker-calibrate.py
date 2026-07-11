"""ranker-calibrate.py — threshold calibration harness (ADVISORY STUB, D32).

Tranche A returns the uncalibrated stub immediately. The real sweep is deferred to
the calibration tranche.

TODO (calibration tranche — full sweep):
    1. Load labeled holdout corpus: [{artifact_path, ac_contract_ref, oracle_verdict}]
    2. Grid sweep over (orm_threshold, diversity_threshold, prm_finalist_gap):
       for each combination:
         a. Run ranker-staged-prune.py on each artifact
         b. Compare selected_id oracle_pass vs holdout oracle_verdict (pass/fail)
         c. Compute precision, recall, F1 on the selection decision
    3. Reward-hacking detection (2511.08325 §4.3 / D20):
       - Track (prm_aggregate, oracle_pass) per artifact across ≥20 runs
       - If PRM-aggregate > oracle-pass gap exceeds 10 pp on average →
         emit CALIBRATION_DRIFT warning and freeze ranker (oracle is always final gate;
         PRM only picks finalists — drift = PRM gaming)
    4. Emit calibration.yaml: optimal thresholds + drift_flag + confidence_interval + run_date

CLI:
    python ranker-calibrate.py [--corpus-json <path>] [--output-yaml <path>]

Exit code: 0 (stub always succeeds — no corpus evaluated in this tranche).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_UNCALIBRATED_RESULT: dict[str, Any] = {
    "status": "uncalibrated",
    "note": "advisory — golden corpus deferred to calibration tranche",
    "current_thresholds": {
        "orm_prune": 0.50,
        "diversity": 0.85,
        "prm_finalist_gap": 0.15,
    },
    "reward_hacking_check": "deferred",
    "calibration_drift": None,
    "confidence_interval": None,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Ranker threshold calibration harness "
            "(advisory stub — golden corpus deferred to calibration tranche, D32)"
        )
    )
    parser.add_argument(
        "--corpus-json",
        metavar="PATH",
        help="Labeled holdout corpus JSON (deferred — not consumed in this tranche)",
    )
    parser.add_argument(
        "--output-yaml",
        metavar="PATH",
        help="Write calibration result YAML (stub emitted as JSON in this tranche)",
    )
    args = parser.parse_args(argv)

    if args.corpus_json:
        print(
            "WARN: --corpus-json provided but calibration sweep is deferred to "
            "calibration tranche (D32). Returning uncalibrated stub.",
            file=sys.stderr,
        )

    result = dict(_UNCALIBRATED_RESULT)
    output = json.dumps(result, indent=2)

    if args.output_yaml:
        out_path = Path(args.output_yaml)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output + "\n", encoding="utf-8")
        print(f"Written (stub): {out_path}")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    sys.exit(main())

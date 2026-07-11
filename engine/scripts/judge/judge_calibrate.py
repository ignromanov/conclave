#!/usr/bin/env python3
"""judge_calibrate.py — calibration advisory stub (spec 089, D32).

ADVISORY STUB: real calibration requires a ≥100-item golden corpus
(60/40 PASS/FAIL, 50 code Iris-labeled + 50 prose dual-human κ≥0.70, 4 mutation types).
That corpus does not yet exist. Until it is built and this stub is replaced, calibration
state = uncalibrated and verdicts carry calibration_note advisory.

TODO (Forge evolve / model bump trigger per D32): replace this stub with real computation of:
  - FPR (false positive rate) — target ≤0.10
  - FNR (false negative rate) — target ≤0.15
  - ECE (expected calibration error) — target ≤0.15
  - Cohen's κ (inter-rater agreement) — target ≥0.60
  - Per-mutation-type FPR (missing-AC, uncited-claim, intent-thin-stub, subtle-logic-bug)

Golden corpus spec (D32):
  - ≥100 items total: 60 PASS / 40 FAIL
  - 50 code items (Iris-labeled)
  - 50 prose items (dual-human κ≥0.70)
  - 4 mutation types: missing-AC, uncited-claim, intent-thin-stub, subtle-logic-bug
  - At least ≥40 items from the broken set (FPR ≤0.10 = catches ≥36/40 per AC14)
  - Re-triggered: Forge evolve event, model bump, false_pass_rate drift >1.5× floor (D32)

This stub always returns 0 (never blocks a run). Cat13 checks current.yaml `threshold_met`
before promoting/gating a judge.

Usage:
    python judge_calibrate.py [--model-id <model>] [--out <path>]
    python judge_calibrate.py --help

Exit codes (ADR-0003): 0 always (stub never blocks)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

_CALIBRATION_NOTE = (
    "advisory — confidence advisory; golden corpus deferred (D32 TODO: "
    "build ≥100-item corpus 60/40 PASS/FAIL, 50 code + 50 prose, 4 mutation types)"
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Calibration advisory stub — returns uncalibrated status (D32). "
            "Replace with real FPR/FNR/ECE/κ computation once golden corpus is built."
        )
    )
    ap.add_argument("--model-id", default="claude-sonnet-4-6",
                    help="Model ID being calibrated (informational only)")
    ap.add_argument("--out", type=Path, default=None,
                    help="Write calibration result JSON to this path (prints to stdout if omitted)")
    args = ap.parse_args(argv)

    result = {
        "status": "uncalibrated",
        "calibration_note": _CALIBRATION_NOTE,
        "model_id": args.model_id,
        "threshold_met": False,
        "fpr": None,
        "fnr": None,
        "ece": None,
        "kappa": None,
        "corpus_size": 0,
        "mutation_fpr": {
            "missing_ac": None,
            "uncited_claim": None,
            "intent_thin_stub": None,
            "subtle_logic_bug": None,
        },
        "todo": (
            "Build ≥100-item golden corpus (60 PASS / 40 FAIL; "
            "50 code Iris-labeled + 50 prose dual-human κ≥0.70; "
            "4 mutation types: missing-AC, uncited-claim, intent-thin-stub, subtle-logic-bug). "
            "Triggered by Forge evolve / model bump / false_pass_rate drift >1.5× floor per D32."
        ),
    }

    output = json.dumps(result, indent=2)
    if args.out:
        args.out.write_text(output)
        print(f"Calibration stub written to {args.out} (status=uncalibrated, threshold_met=false)")
    else:
        print(output)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

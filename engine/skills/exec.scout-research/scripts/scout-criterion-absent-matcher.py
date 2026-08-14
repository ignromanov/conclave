#!/usr/bin/env python3
"""scout_criterion_absent_matcher.py — P7 futility-hook condition (spec 089, D31 / AC24).

One of the four P7 re-research conditions: the failing criterion is a KNOWLEDGE-gap, not an
execution-gap, when it is **absent from the P1 scout artifact** (the research wave never covered
it). Combined (spec 089's retired autopilot spine protocol, §8, never shipped) with: ≥1 atlas
attempt, non-mechanical category, last-2 n-gram ≥0.80.

I/O:
  --criterion "<failing AC text or id>"   the criterion the artifact keeps failing
  --p1-artifact <scout-*.yaml>            the P1 scout output to search
  [--threshold 0.34]                      min term-overlap to count as "covered"
Stdout: {absent: bool, coverage: float}
Exit (ADR-0003): 0 criterion PRESENT in P1 (mechanical/execution gap → no re-research) ·
                 3 criterion ABSENT from P1 (knowledge gap → P7 hook candidate) · 1/2 errors.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def terms(s: str) -> set[str]:
    return {t.lower() for t in re.findall(r"\w{4,}", s)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--criterion", required=True)
    ap.add_argument("--p1-artifact", required=True, type=Path)
    ap.add_argument("--threshold", type=float, default=0.34)
    args = ap.parse_args(argv)

    if not args.p1_artifact.is_file():
        print(f"ERROR: missing P1 artifact: {args.p1_artifact}", file=sys.stderr)
        return 2

    crit_terms = terms(args.criterion)
    if not crit_terms:
        print('{"absent": true, "coverage": 0.0}')
        return 3

    artifact_terms = terms(args.p1_artifact.read_text(errors="ignore"))
    overlap = len(crit_terms & artifact_terms) / len(crit_terms)
    absent = overlap < args.threshold
    print(f'{{"absent": {str(absent).lower()}, "coverage": {overlap:.3f}}}')
    return 3 if absent else 0


if __name__ == "__main__":
    raise SystemExit(main())

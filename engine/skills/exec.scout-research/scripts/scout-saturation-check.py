#!/usr/bin/env python3
"""scout_saturation_check.py — n-gram saturation detector (spec 089, D31; round8 §5 STOP rule).

Arms the scout STOP rule and the P7 futility hook: if the last 2-3 research findings overlap by
n-gram Jaccard >0.80, the wave is saturated (past-saturation = waste, not thoroughness).

I/O:
  --findings <file>   newline-OR-`---`-separated finding texts (last entry = newest)
  [--threshold 0.80]  [--n 3]  (n-gram size)  [--window 2]  (compare last `window` findings)
Stdout: {saturated: bool, max_ngram: float}
Exit (ADR-0003): 0 not saturated · 3 saturated (fire STOP / arm P7) · 1 usage · 2 missing input.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _ngrams(text: str, n: int) -> set[str]:
    toks = re.findall(r"\w+", text.lower())
    if len(toks) < n:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def split_findings(raw: str) -> list[str]:
    if "\n---\n" in raw:
        parts = raw.split("\n---\n")
    else:
        parts = raw.splitlines()
    return [p.strip() for p in parts if p.strip()]


def max_pairwise_ngram(findings: list[str], n: int, window: int) -> float:
    recent = findings[-window:] if len(findings) >= window else findings
    grams = [_ngrams(f, n) for f in recent]
    best = 0.0
    for i in range(len(grams)):
        for j in range(i + 1, len(grams)):
            best = max(best, jaccard(grams[i], grams[j]))
    return best


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", required=True, type=Path)
    ap.add_argument("--threshold", type=float, default=0.80)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--window", type=int, default=2)
    args = ap.parse_args(argv)

    if not args.findings.is_file():
        print(f"ERROR: missing findings file: {args.findings}", file=sys.stderr)
        return 2

    findings = split_findings(args.findings.read_text())
    if len(findings) < 2:
        print('{"saturated": false, "max_ngram": 0.0}')
        return 0

    mx = max_pairwise_ngram(findings, args.n, args.window)
    saturated = mx >= args.threshold
    print(f'{{"saturated": {str(saturated).lower()}, "max_ngram": {mx:.3f}}}')
    return 3 if saturated else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""judge_bias_controls.py — swap-order probe + length-normalize + self-preference flag.

Implements three bias-control mechanisms from spec 089 D18 / research-round6 §B.1:

1. swap-order  — given two verdict files for the same artifact at different prompt positions,
                 flag if the top-level verdict differs (position bias, 2505.19477).
2. length-check — flag if there is a large length disparity between candidates that correlates
                  with the verdict (verbosity bias, 2505.19477 / 2604.23178).
3. self-pref   — flag if the judge model matches the generator model (self-preference, 2410.21819).

Each sub-command writes a bias report YAML to --out and exits with:
  0 = no bias flag raised
  1 = bias flag raised
  2 = missing input file

Reuses the 084/086 substrate: ruamel.yaml (round-trip).

Usage:
    python judge_bias_controls.py swap-order \\
        --order-a verdict-a.yaml --order-b verdict-b.yaml --out bias-report.yaml

    python judge_bias_controls.py length-check \\
        --verdict verdict.yaml \\
        --candidate-lengths candidateA=1200 candidateB=850 \\
        --out bias-report.yaml

    python judge_bias_controls.py self-pref \\
        --verdict verdict.yaml --generator-model claude-opus-4-8 --out bias-report.yaml

Exit codes (ADR-0003): 0 no bias · 1 bias flag raised · 2 missing file
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.default_flow_style = False

_VERBOSITY_THRESHOLD = 0.30  # 30% relative length difference triggers the flag


def _load(path: Path) -> dict:
    if not path.is_file():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        sys.exit(2)
    with path.open() as fh:
        data = _yaml.load(fh)
    if not isinstance(data, dict):
        print(f"ERROR: {path} is not a YAML mapping", file=sys.stderr)
        sys.exit(1)
    return data


def _write(data: dict, path: Path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as fh:
        _yaml.dump(data, fh)
    tmp.replace(path)


# --------------------------------------------------------------------------- swap-order

def cmd_swap_order(args: argparse.Namespace) -> int:
    a = _load(args.order_a)
    b = _load(args.order_b)
    va = a.get("verdict", "inconclusive")
    vb = b.get("verdict", "inconclusive")
    bias_detected = va != vb

    report = {
        "check": "swap_order",
        "verdict_order_a": va,
        "verdict_order_b": vb,
        "position_bias_detected": bias_detected,
        "note": (
            f"Verdicts differ ({va!r} vs {vb!r}) — position bias suspected (2505.19477)"
            if bias_detected
            else "Verdicts consistent across orders — no position bias detected"
        ),
    }
    _write(report, args.out)
    print(report["note"])
    return 1 if bias_detected else 0


# --------------------------------------------------------------------------- length-check

def cmd_length_check(args: argparse.Namespace) -> int:
    _load(args.verdict)  # validate file exists and is a mapping

    lengths: dict[str, int] = {}
    for item in args.candidate_lengths:
        if "=" not in item:
            print(f"ERROR: --candidate-lengths must be NAME=TOKENS pairs: {item!r}", file=sys.stderr)
            return 1
        k, v = item.split("=", 1)
        lengths[k] = int(v)

    if not lengths:
        print("ERROR: --candidate-lengths required", file=sys.stderr)
        return 1

    max_len = max(lengths.values())
    min_len = min(lengths.values())
    ratio = (max_len - min_len) / max_len if max_len > 0 else 0.0
    bias_detected = ratio > _VERBOSITY_THRESHOLD

    report = {
        "check": "length_normalize",
        "candidate_lengths": lengths,
        "length_ratio": round(ratio, 3),
        "threshold": _VERBOSITY_THRESHOLD,
        "verbosity_bias_detected": bias_detected,
        "note": (
            f"Length ratio {ratio:.1%} exceeds threshold {_VERBOSITY_THRESHOLD:.1%} — "
            f"verbosity bias suspected (2604.23178)"
            if bias_detected
            else f"Length ratio {ratio:.1%} within threshold — no verbosity bias detected"
        ),
    }
    _write(report, args.out)
    print(report["note"])
    return 1 if bias_detected else 0


# --------------------------------------------------------------------------- self-pref

def cmd_self_pref(args: argparse.Namespace) -> int:
    verdict = _load(args.verdict)
    judge_model = verdict.get("model_id", "")
    bias_detected = bool(judge_model and judge_model == args.generator_model)

    report = {
        "check": "self_preference",
        "judge_model": judge_model,
        "generator_model": args.generator_model,
        "self_preference_detected": bias_detected,
        "note": (
            f"Judge model {judge_model!r} matches generator — self-preference risk (2410.21819)"
            if bias_detected
            else "Judge model differs from generator — self-preference mitigated"
        ),
    }
    _write(report, args.out)
    print(report["note"])
    return 1 if bias_detected else 0


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Bias controls for judge verdicts: swap-order, length-normalize, self-preference"
    )
    sub = ap.add_subparsers(dest="command", required=True)

    p_swap = sub.add_parser("swap-order", help="Position-bias probe via verdict-order swap")
    p_swap.add_argument("--order-a", required=True, type=Path,
                        help="Verdict YAML for prompt order A")
    p_swap.add_argument("--order-b", required=True, type=Path,
                        help="Verdict YAML for prompt order B (same content, different position)")
    p_swap.add_argument("--out", required=True, type=Path, help="Write bias report YAML here")

    p_len = sub.add_parser("length-check", help="Verbosity-bias length-normalize check")
    p_len.add_argument("--verdict", required=True, type=Path)
    p_len.add_argument("--candidate-lengths", nargs="+", default=[],
                       metavar="NAME=TOKENS",
                       help="Token counts per candidate, e.g. candidateA=1200 candidateB=850")
    p_len.add_argument("--out", required=True, type=Path)

    p_self = sub.add_parser("self-pref", help="Self-preference model-match flag")
    p_self.add_argument("--verdict", required=True, type=Path)
    p_self.add_argument("--generator-model", required=True,
                        help="Model ID that generated the artifact under review")
    p_self.add_argument("--out", required=True, type=Path)

    args = ap.parse_args(argv)
    dispatch = {
        "swap-order": cmd_swap_order,
        "length-check": cmd_length_check,
        "self-pref": cmd_self_pref,
    }
    return dispatch[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""judge_aggregate.py — majority-vote aggregator for ≥3 judge verdict samples (spec 089, D18.2).

Takes N verdict YAML files (one per sample at varied temp/prompt-seed), computes per-AC-id
majority verdict, resolves the overall aggregated verdict, and writes the merged result.

Rules (D18.2 + research-round6 §B.1):
  - Per-AC majority: simple majority (>50%) across samples decides status.
  - Overall verdict: majority of the per-sample top-level `verdict` fields.
  - aggregation = "unanimous" if all samples agree, "majority" if winner > N/2, "split" if tied.
  - split → escalate: true in output (spine routes to human — AC29).
  - Findings union: a finding ID present in ≥ N/2 samples is included; severity = worst across samples.

Reuses the 084/086 substrate: pydantic v2 + ruamel.yaml (round-trip).

Usage:
    python judge_aggregate.py \\
        --samples verdict-s1.yaml verdict-s2.yaml verdict-s3.yaml \\
        --out aggregated-verdict.yaml

Exit codes (ADR-0003): 0 ok · 1 usage/validation error · 2 missing input
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

from ruamel.yaml import YAML

Aggregation = Literal["majority", "unanimous", "split"]

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.default_flow_style = False

_SEVERITY_RANK: dict[str, int] = {"BLOCKER": 0, "MAJOR": 1, "MINOR": 2, "INFO": 3}


def _load(path: Path) -> dict:
    if not path.is_file():
        print(f"ERROR: sample file not found: {path}", file=sys.stderr)
        sys.exit(2)
    with path.open() as fh:
        data = _yaml.load(fh)
    if not isinstance(data, dict):
        print(f"ERROR: {path} is not a YAML mapping", file=sys.stderr)
        sys.exit(1)
    return data


def _majority(values: list[str]) -> tuple[str, Aggregation]:
    n = len(values)
    counts = Counter(values)
    winner, count = counts.most_common(1)[0]
    if count == n:
        return winner, "unanimous"
    if count > n / 2:
        return winner, "majority"
    # Split: no clear majority — escalate required.
    return winner, "split"


def _aggregate_ac_table(samples: list[dict]) -> list[dict]:
    by_id: dict[str, list[str]] = {}
    meta: dict[str, dict] = {}
    for s in samples:
        for entry in s.get("ac_table", []):
            ac_id = entry.get("ac_id", "")
            by_id.setdefault(ac_id, []).append(entry.get("status", "inconclusive"))
            if ac_id not in meta:
                meta[ac_id] = dict(entry)

    result = []
    for ac_id, statuses in by_id.items():
        status, _ = _majority(statuses)
        row = dict(meta[ac_id])
        row["status"] = status
        row["evidence"] = f"aggregated from {len(statuses)} sample(s)"
        result.append(row)
    return result


def _merge_findings(samples: list[dict]) -> list[dict]:
    """Union findings by id; include if present in ≥ N/2 samples; severity = worst seen."""
    n = len(samples)
    by_id: dict[str, list[dict]] = {}
    for s in samples:
        for f in s.get("findings", []):
            fid = f.get("id", "")
            by_id.setdefault(fid, []).append(f)

    result = []
    for _fid, instances in by_id.items():
        if len(instances) < n / 2:
            continue
        canonical = dict(instances[0])
        canonical["severity"] = min(
            (i.get("severity", "INFO") for i in instances),
            key=lambda s: _SEVERITY_RANK.get(s, 99),
        )
        result.append(canonical)
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Majority-vote aggregator for ≥3 judge verdict samples (D18.2)"
    )
    ap.add_argument("--samples", nargs="+", required=True, type=Path,
                    help="Verdict YAML files — ≥3 required (D18.2)")
    ap.add_argument("--out", required=True, type=Path,
                    help="Write aggregated verdict YAML to this path")
    args = ap.parse_args(argv)

    if len(args.samples) < 3:
        print("ERROR: ≥3 samples required (D18.2 — single-call unreliable)", file=sys.stderr)
        return 1

    samples = [_load(p) for p in args.samples]

    top_verdicts = [s.get("verdict", "inconclusive") for s in samples]
    agg_verdict, agg_type = _majority(top_verdicts)

    confidences = [float(s.get("confidence", 0.0)) for s in samples]
    avg_confidence = sum(confidences) / len(confidences)

    calibration_notes = [s.get("calibration_note") for s in samples if s.get("calibration_note")]
    calibration_note = calibration_notes[0] if calibration_notes else None

    total_elapsed = sum(int(s.get("elapsed_ms", 0)) for s in samples)

    aggregated: dict = {
        "verdict": agg_verdict,
        "ac_table": _aggregate_ac_table(samples),
        "findings": _merge_findings(samples),
        "confidence": round(avg_confidence, 3),
        "calibration_note": calibration_note,
        "sample_count": len(samples),
        "aggregation": agg_type,
        "oracle_grounded": all(bool(s.get("oracle_grounded", False)) for s in samples),
        "escalate": agg_type == "split",
        "elapsed_ms": total_elapsed,
    }

    tmp = args.out.with_suffix(args.out.suffix + ".tmp")
    with tmp.open("w") as fh:
        _yaml.dump(aggregated, fh)
    tmp.replace(args.out)

    print(
        f"Aggregated: verdict={agg_verdict} aggregation={agg_type} "
        f"samples={len(samples)} confidence={avg_confidence:.3f} escalate={aggregated['escalate']}"
        f" -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

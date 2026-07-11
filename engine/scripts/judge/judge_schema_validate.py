#!/usr/bin/env python3
"""judge_schema_validate.py — validate a judge verdict YAML against the spec 089 schema.

Called by the spine before consuming judge-verdict.yaml (spine §4, p6-judge sub-seal).
Validates field-for-field against the JudgeVerdict schema (research-round6 §B.1).
Also enforces verdict-consistency invariants:
  pass     = no BLOCKER, no unresolved MAJOR
  partial  = no BLOCKER but ≥1 unresolved MAJOR
  fail     = ≥1 BLOCKER
  inconclusive = D18 condition violation or calibration absent

Reuses the 084/086 substrate: pydantic v2 + ruamel.yaml (round-trip).

Usage:
    python judge_schema_validate.py --verdict <path-to-judge-verdict.yaml>
    python judge_schema_validate.py --verdict <path> [--strict]

Exit codes (ADR-0003): 0 valid · 1 schema or consistency error · 2 missing file
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator
from ruamel.yaml import YAML

Verdict = Literal["pass", "partial", "fail", "inconclusive"]
Severity = Literal["BLOCKER", "MAJOR", "MINOR", "INFO"]
Aggregation = Literal["majority", "unanimous", "split"]

_yaml = YAML()
_yaml.preserve_quotes = True


class AcTableEntry(BaseModel):
    ac_id: str
    text: str
    status: Literal["pass", "fail", "inconclusive"]
    evidence: str
    severity: Severity


class Finding(BaseModel):
    id: str
    severity: Severity
    ac_ref: str
    description: str
    citation: str = Field(min_length=1)
    critic_addressed: bool
    remediation: str


class JudgeVerdict(BaseModel):
    verdict: Verdict
    ac_table: list[AcTableEntry] = []
    findings: list[Finding] = []
    confidence: float = Field(ge=0.0, le=1.0)
    calibration_note: str | None = None
    sample_count: int = Field(ge=3)
    aggregation: Aggregation = "majority"
    oracle_grounded: bool
    escalate: bool
    elapsed_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _verdict_consistency(self) -> JudgeVerdict:
        blockers = [f for f in self.findings if f.severity == "BLOCKER"]
        majors = [f for f in self.findings if f.severity == "MAJOR"]

        if self.verdict == "fail" and not blockers:
            raise ValueError("verdict=fail requires ≥1 BLOCKER finding")
        if self.verdict == "pass" and blockers:
            raise ValueError("verdict=pass must have no BLOCKER findings")
        if self.verdict == "pass" and majors:
            raise ValueError("verdict=pass must have no MAJOR findings")
        if self.verdict == "partial" and blockers:
            raise ValueError("verdict=partial must have no BLOCKER findings")
        if self.aggregation == "split" and not self.escalate:
            raise ValueError("aggregation=split requires escalate=true")
        return self


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Validate judge verdict YAML against spec 089 schema (spine pre-consume gate)"
    )
    ap.add_argument("--verdict", required=True, type=Path,
                    help="Path to judge-verdict.yaml")
    ap.add_argument("--strict", action="store_true",
                    help="Fail if calibration_note is present (enforce calibration gate)")
    args = ap.parse_args(argv)

    data = _load(args.verdict)
    try:
        verdict = JudgeVerdict(**data)
    except ValidationError as exc:
        print(f"INVALID: {args.verdict}\n{exc}", file=sys.stderr)
        return 1

    if args.strict and verdict.calibration_note:
        print(
            f"INVALID (--strict): calibration_note present: {verdict.calibration_note!r}",
            file=sys.stderr,
        )
        return 1

    print(
        f"VALID: verdict={verdict.verdict} sample_count={verdict.sample_count} "
        f"aggregation={verdict.aggregation} escalate={verdict.escalate} "
        f"oracle_grounded={verdict.oracle_grounded}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""oracle_signal_merge.py — the single named merge owner for oracle-signal.yaml (spec 089, D23).

Resolves the round-10 audit's real contradiction: Iris writes pipeline-verdict.yaml and the judge
writes its verdict, but nothing owned the merge. This is the ONLY writer of oracle-signal.yaml —
the artifact spec 090 consumes (D15). Schema mirrors the 089 pipeline schema record (§6, internal design).

Reuses the 084/086 substrate: pydantic v2 + ruamel.yaml (round-trip).

Usage:
    python oracle_signal_merge.py \
        --pipeline-verdict <spec-dir>/pipeline-verdict.yaml \
        --judge-verdict    <spec-dir>/judge-verdict.yaml \
        --run-id           <run_id> \
        --out              <spec-dir>/oracle-signal.yaml \
        [--model-id claude-opus-4-8] [--prompt-hash <sha256>]

Exit codes (ADR-0003 convention): 0 ok · 1 usage/validation error · 2 missing required input.
"""
from __future__ import annotations

import argparse
import hashlib
import platform
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator
from ruamel.yaml import YAML

Verdict = Literal["pass", "partial", "fail", "inconclusive"]

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.default_flow_style = False


# --------------------------------------------------------------------------- models
class JudgeVerdict(BaseModel):
    verdict: Verdict
    ac_table: list[dict] = []
    findings: list[dict] = []
    confidence: float = Field(ge=0.0, le=1.0)
    calibration_note: str | None = None
    sample_count: int = Field(ge=3)
    aggregation: Literal["majority", "unanimous", "split"] = "majority"


class IrisVerdictRef(BaseModel):
    ref: str
    inline_verdict: Verdict


class OracleSignal(BaseModel):
    schema_version: Literal[1] = 1
    run_id: str
    iris_verdict: IrisVerdictRef
    judge_verdict: JudgeVerdict
    combined_verdict: Verdict
    escalate: bool
    model_id: str
    prompt_hash: str
    tool_versions: dict[str, str]

    @model_validator(mode="after")
    def _floor_not_overturned(self) -> OracleSignal:
        # The deterministic floor (Iris) cannot be overturned by the judge (glossary / merge rule 1).
        if self.iris_verdict.inline_verdict == "fail" and self.combined_verdict != "fail":
            raise ValueError("combined_verdict must be 'fail' when the Iris floor is 'fail'")
        return self


# --------------------------------------------------------------------------- merge rule
def compute_combined(iris: IrisVerdictRef, judge: JudgeVerdict) -> tuple[Verdict, bool]:
    """Return (combined_verdict, escalate) per schemas.md § 6 merge rule (deterministic)."""
    escalate = judge.aggregation == "split"

    # Rule 1 — deterministic FAIL is final; judge cannot overturn.
    if iris.inline_verdict == "fail":
        return "fail", escalate

    # Rule 2 — otherwise the judge verdict carries, with inconclusive/disagreement guards.
    combined: Verdict = judge.verdict
    if judge.verdict == "inconclusive":
        combined = "inconclusive"
        escalate = True
    # Rule 3 — floor passes but judge fails → disagreement, escalate.
    if iris.inline_verdict == "pass" and judge.verdict == "fail":
        escalate = True
    return combined, escalate


def _tool_versions() -> dict[str, str]:
    import pydantic
    import ruamel.yaml as ry

    return {
        "python": platform.python_version(),
        "pydantic": pydantic.VERSION,
        "ruamel.yaml": getattr(ry, "__version__", "unknown"),
    }


def _load_yaml(path: Path) -> dict:
    if not path.is_file():
        print(f"ERROR: required input missing: {path}", file=sys.stderr)
        sys.exit(2)
    with path.open() as fh:
        data = _yaml.load(fh)
    if not isinstance(data, dict):
        print(f"ERROR: {path} is not a mapping", file=sys.stderr)
        sys.exit(1)
    return data


def merge(pipeline_verdict_path: Path, judge_verdict_path: Path, run_id: str,
          model_id: str, prompt_hash: str | None) -> OracleSignal:
    pv = _load_yaml(pipeline_verdict_path)
    jv_raw = _load_yaml(judge_verdict_path)

    # Iris pipeline-verdict.yaml carries a top-level `verdict:` field (exec.iris-test contract).
    iris_inline = pv.get("verdict")
    if iris_inline not in ("pass", "partial", "fail", "inconclusive"):
        print(f"ERROR: pipeline-verdict.yaml has no valid top-level verdict ({iris_inline!r})",
              file=sys.stderr)
        sys.exit(1)
    iris = IrisVerdictRef(ref=str(pipeline_verdict_path), inline_verdict=iris_inline)

    try:
        judge = JudgeVerdict(**jv_raw)
    except ValidationError as exc:
        print(f"ERROR: judge verdict failed schema validation:\n{exc}", file=sys.stderr)
        sys.exit(1)

    combined, escalate = compute_combined(iris, judge)

    if prompt_hash is None:
        # Deterministic placeholder so the seed field is always populated (audit D8).
        prompt_hash = hashlib.sha256(f"{model_id}:{run_id}".encode()).hexdigest()

    return OracleSignal(
        run_id=run_id,
        iris_verdict=iris,
        judge_verdict=judge,
        combined_verdict=combined,
        escalate=escalate,
        model_id=model_id,
        prompt_hash=prompt_hash,
        tool_versions=_tool_versions(),
    )


def write(signal: OracleSignal, out_path: Path) -> None:
    # Atomic write (temp + replace) — last-write-wins, no half-written oracle-signal.yaml.
    tmp = out_path.with_suffix(out_path.suffix + ".tmp")
    with tmp.open("w") as fh:
        _yaml.dump(signal.model_dump(mode="json"), fh)
    tmp.replace(out_path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Merge Iris + judge verdicts into oracle-signal.yaml")
    ap.add_argument("--pipeline-verdict", required=True, type=Path)
    ap.add_argument("--judge-verdict", required=True, type=Path)
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--model-id", default="claude-opus-4-8")
    ap.add_argument("--prompt-hash", default=None)
    args = ap.parse_args(argv)

    signal = merge(args.pipeline_verdict, args.judge_verdict, args.run_id,
                   args.model_id, args.prompt_hash)
    write(signal, args.out)
    print(f"oracle-signal.yaml written: combined_verdict={signal.combined_verdict} "
          f"escalate={signal.escalate} -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

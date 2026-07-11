#!/usr/bin/env python3
"""critic_refute.py — scaffold and write critic-refutation.yaml (spec 089, D21/D22).

Validates refutation entries against the critic schema (research-round6 §B.2), ensures ≥1 entry
per red-team technique (T1–T5), and writes the file via ruamel round-trip. The output is the
one-way file the Judge (exec.themis-judge / themis) consumes before issuing its verdict.

Reuses the 084/086 substrate: pydantic v2 + ruamel.yaml.

Usage:
    python critic_refute.py \\
        --artifact  <path-to-artifact>          \\
        --contract  <path-to-contract.md>       \\
        --out       <spec-dir>/critic-refutation.yaml \\
        --run-id    <task_slug>-<YYYYMMDD-HHMMSS>     \\
        [--refutations-json <path-to-refutations.json>] \\
        [--elapsed-ms <int>]

    If --refutations-json is omitted and --out already exists the script re-validates
    the existing file and rewrites it (idempotent mode).

Exit codes (ADR-0003 convention): 0 ok · 1 validation/schema error · 2 missing required input.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError, model_validator
from ruamel.yaml import YAML

# ---------------------------------------------------------------------------
# Schema (mirrors research-round6 §B.2)
# ---------------------------------------------------------------------------

RefutationType = Literal[
    "unverifiable_claim",
    "assumption_violation",
    "scope_overstep",
    "ac_gaming",
    "missing_edge_case",
    "factual_error",
]

StrengthLevel = Literal["high", "medium", "low"]

# T1–T5 technique → acceptable types mapping (for coverage gate)
_TECHNIQUE_TYPES: dict[str, list[str]] = {
    "T1": ["missing_edge_case", "factual_error"],
    "T2": ["unverifiable_claim"],
    "T3": ["assumption_violation"],
    "T4": ["ac_gaming"],
    "T5": ["scope_overstep"],
}


class RefutationEntry(BaseModel):
    id: str = Field(pattern=r"^R-\d{3,}$")
    type: RefutationType
    location: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    strength: StrengthLevel
    ac_ref: str
    description: str = Field(min_length=1)
    suggested_judge_question: str = Field(min_length=1)

    @model_validator(mode="after")
    def high_strength_needs_evidence(self) -> RefutationEntry:
        if self.strength == "high" and len(self.evidence.strip()) < 10:
            raise ValueError(
                f"strength:high requires substantive tool-grounded evidence (entry {self.id})"
            )
        return self


class CriticRefutationDoc(BaseModel):
    schema_version: int = 1
    artifact_ref: str
    ac_contract_ref: str
    refutations: list[RefutationEntry]
    unverifiable_count: int = Field(ge=0)
    assumption_count: int = Field(ge=0)
    scope_overstep_count: int = Field(ge=0)
    elapsed_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def counts_match_entries(self) -> CriticRefutationDoc:
        unverifiable = sum(1 for r in self.refutations if r.type == "unverifiable_claim")
        assumptions = sum(1 for r in self.refutations if r.type == "assumption_violation")
        overstepped = sum(1 for r in self.refutations if r.type == "scope_overstep")
        if unverifiable != self.unverifiable_count:
            raise ValueError(
                f"unverifiable_count mismatch: declared {self.unverifiable_count}, "
                f"found {unverifiable}"
            )
        if assumptions != self.assumption_count:
            raise ValueError(
                f"assumption_count mismatch: declared {self.assumption_count}, "
                f"found {assumptions}"
            )
        if overstepped != self.scope_overstep_count:
            raise ValueError(
                f"scope_overstep_count mismatch: declared {self.scope_overstep_count}, "
                f"found {overstepped}"
            )
        return self

    @model_validator(mode="after")
    def each_technique_covered(self) -> CriticRefutationDoc:
        present_types = {r.type for r in self.refutations}
        missing: list[str] = []
        for technique, types in _TECHNIQUE_TYPES.items():
            if not any(t in present_types for t in types):
                missing.append(f"{technique} ({'/'.join(types)})")
        if missing:
            raise ValueError(
                "Each of the 5 red-team techniques must have ≥1 entry. "
                f"Missing: {', '.join(missing)}"
            )
        return self


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _yaml() -> YAML:
    y = YAML()
    y.default_flow_style = False
    y.width = 120
    return y


def _load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return _yaml().load(f) or {}


def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        _yaml().dump(data, f)


def _doc_to_dict(doc: CriticRefutationDoc) -> dict:
    return {
        "schema_version": doc.schema_version,
        "artifact_ref": doc.artifact_ref,
        "ac_contract_ref": doc.ac_contract_ref,
        "refutations": [
            {
                "id": r.id,
                "type": r.type,
                "location": r.location,
                "evidence": r.evidence,
                "strength": r.strength,
                "ac_ref": r.ac_ref,
                "description": r.description,
                "suggested_judge_question": r.suggested_judge_question,
            }
            for r in doc.refutations
        ],
        "unverifiable_count": doc.unverifiable_count,
        "assumption_count": doc.assumption_count,
        "scope_overstep_count": doc.scope_overstep_count,
        "elapsed_ms": doc.elapsed_ms,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Scaffold and write critic-refutation.yaml (spec 089 D21/D22).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "If --refutations-json is omitted and --out already exists the script "
            "re-validates the existing file (idempotent mode)."
        ),
    )
    p.add_argument("--artifact", required=True, help="Path to the artifact under review")
    p.add_argument("--contract", required=True, help="Path to the sealed AC-contract")
    p.add_argument("--out", required=True, help="Output path for critic-refutation.yaml")
    p.add_argument(
        "--run-id", required=True, help="Run identifier (task_slug-YYYYMMDD-HHMMSS)"
    )
    p.add_argument(
        "--refutations-json",
        default=None,
        help="JSON file with a list of refutation dicts (for programmatic use)",
    )
    p.add_argument("--elapsed-ms", type=int, default=0, help="Wall-clock elapsed ms")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    artifact_path = Path(args.artifact)
    contract_path = Path(args.contract)
    out_path = Path(args.out)

    if not artifact_path.exists():
        print(f"ERROR: artifact not found: {artifact_path}", file=sys.stderr)
        return 2
    if not contract_path.exists():
        print(f"ERROR: ac_contract not found: {contract_path}", file=sys.stderr)
        return 2

    # Determine refutation source
    refutations_raw: list[dict]
    if args.refutations_json:
        rj_path = Path(args.refutations_json)
        if not rj_path.exists():
            print(f"ERROR: refutations JSON not found: {rj_path}", file=sys.stderr)
            return 2
        with rj_path.open("r", encoding="utf-8") as f:
            refutations_raw = json.load(f)
    elif out_path.exists():
        existing = _load_yaml(out_path)
        refutations_raw = existing.get("refutations", [])
    else:
        print(
            "ERROR: --refutations-json not provided and --out does not exist yet.\n"
            "Pass --refutations-json with a list of refutation dicts.",
            file=sys.stderr,
        )
        return 1

    # Derive counts from the raw list
    unverifiable = sum(1 for r in refutations_raw if r.get("type") == "unverifiable_claim")
    assumptions = sum(1 for r in refutations_raw if r.get("type") == "assumption_violation")
    overstepped = sum(1 for r in refutations_raw if r.get("type") == "scope_overstep")

    doc_data = {
        "schema_version": 1,
        "artifact_ref": str(artifact_path),
        "ac_contract_ref": str(contract_path),
        "refutations": refutations_raw,
        "unverifiable_count": unverifiable,
        "assumption_count": assumptions,
        "scope_overstep_count": overstepped,
        "elapsed_ms": args.elapsed_ms,
    }

    try:
        doc = CriticRefutationDoc.model_validate(doc_data)
    except ValidationError as exc:
        print(f"ERROR: schema validation failed:\n{exc}", file=sys.stderr)
        return 1

    _write_yaml(out_path, _doc_to_dict(doc))
    print(f"OK: wrote {out_path} ({len(doc.refutations)} refutations)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

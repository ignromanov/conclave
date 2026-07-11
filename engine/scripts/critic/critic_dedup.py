#!/usr/bin/env python3
"""critic_dedup.py — deduplicate critic-refutation.yaml by (location, type) fingerprint.

Reads an existing critic-refutation.yaml, removes duplicate entries that share the same
(location, type) pair — keeping the first occurrence — and rewrites the file. Run BEFORE
the Judge handoff (spine p6-critic phase) to avoid biasing the Judge with repeated
identical claims.

Reuses 084/086 substrate: pydantic v2 + ruamel.yaml.

Usage:
    python critic_dedup.py --input <critic-refutation.yaml> [--dry-run]

Exit codes (ADR-0003): 0 ok (dedup done or nothing to remove) · 1 error.
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

from pydantic import ValidationError

# Sibling-module imports with fallback for direct invocation.
try:
    from critic_refute import CriticRefutationDoc, _doc_to_dict, _load_yaml, _write_yaml
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from critic_refute import CriticRefutationDoc, _doc_to_dict, _load_yaml, _write_yaml


def _fingerprint(entry: dict) -> str:
    key = f"{entry.get('location', '')}::{entry.get('type', '')}"
    return hashlib.sha256(key.encode()).hexdigest()


def dedup(input_path: Path, dry_run: bool = False) -> int:
    if not input_path.exists():
        print(f"ERROR: file not found: {input_path}", file=sys.stderr)
        return 1

    raw = _load_yaml(input_path)
    original_entries: list[dict] = raw.get("refutations", [])

    seen: set[str] = set()
    deduped: list[dict] = []
    removed = 0
    for entry in original_entries:
        fp = _fingerprint(entry)
        if fp in seen:
            removed += 1
        else:
            seen.add(fp)
            deduped.append(entry)

    if removed == 0:
        print(f"OK: no duplicates found in {input_path} ({len(original_entries)} entries)")
        return 0

    print(
        f"Found {removed} duplicate(s): "
        f"{len(original_entries)} entries → {len(deduped)} remain."
    )

    if dry_run:
        print("(dry-run — file not modified)")
        return 0

    raw["refutations"] = deduped
    raw["unverifiable_count"] = sum(
        1 for r in deduped if r.get("type") == "unverifiable_claim"
    )
    raw["assumption_count"] = sum(
        1 for r in deduped if r.get("type") == "assumption_violation"
    )
    raw["scope_overstep_count"] = sum(
        1 for r in deduped if r.get("type") == "scope_overstep"
    )

    try:
        doc = CriticRefutationDoc.model_validate(raw)
    except ValidationError as exc:
        print(f"ERROR: post-dedup validation failed:\n{exc}", file=sys.stderr)
        return 1

    _write_yaml(input_path, _doc_to_dict(doc))
    print(f"OK: rewrote {input_path}")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Deduplicate critic-refutation.yaml by (location, type) fingerprint. "
            "Run before Judge handoff."
        )
    )
    p.add_argument("--input", required=True, help="Path to critic-refutation.yaml")
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Report duplicates without modifying the file",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    return dedup(Path(args.input), dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())

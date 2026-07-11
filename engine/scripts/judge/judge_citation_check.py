#!/usr/bin/env python3
"""judge_citation_check.py — verify each finding in a judge verdict cites a real tool-call or script line.

Per spec 089 D18.3: every factual finding MUST cite a deterministic gate output (Iris
pipeline-verdict.yaml line, prose-verifier script stdout, or a specific tool-call result).
An empty or missing `citation` field is an invalid verdict — upgraded to BLOCKER.

This script may mutate the verdict in-place: it upgrades any uncited finding to
severity=BLOCKER and sets verdict=fail if the verdict was not already fail/inconclusive.
Pass --check-only to report violations without mutating.

Reuses the 084/086 substrate: ruamel.yaml (round-trip, preserves comments).

Usage:
    python judge_citation_check.py --verdict <path-to-judge-verdict.yaml>
    python judge_citation_check.py --verdict <path> [--check-only] [--out <output-path>]

Exit codes (ADR-0003): 0 all citations present · 1 uncited findings found · 2 missing file
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ruamel.yaml import YAML

_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.default_flow_style = False

_AUTO_BLOCKER_MARKER = "MISSING — auto-BLOCKER by judge_citation_check.py (D18.3)"


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


def _check_and_upgrade(verdict: dict) -> tuple[dict, list[str]]:
    """Return (mutated verdict dict, list of violation messages).

    For each finding with an empty/missing citation:
      - sets citation to the auto-BLOCKER marker
      - upgrades severity to BLOCKER
    If any violations were found, ensures verdict != pass/partial.
    """
    violations: list[str] = []

    for finding in verdict.get("findings", []):
        citation = finding.get("citation", "")
        if not citation or not str(citation).strip():
            fid = finding.get("id", "<unknown>")
            ac_ref = finding.get("ac_ref", "")
            violations.append(
                f"finding {fid!r} (ac_ref={ac_ref!r}): missing citation — upgraded to BLOCKER"
            )
            finding["citation"] = _AUTO_BLOCKER_MARKER
            finding["severity"] = "BLOCKER"

    if violations and verdict.get("verdict") not in ("fail", "inconclusive"):
        verdict["verdict"] = "fail"

    return verdict, violations


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Verify each finding cites a tool-call/script line; uncited → auto-BLOCKER (D18.3)"
    )
    ap.add_argument("--verdict", required=True, type=Path,
                    help="Path to judge-verdict.yaml")
    ap.add_argument("--check-only", action="store_true",
                    help="Report violations without mutating the file")
    ap.add_argument("--out", type=Path, default=None,
                    help="Write upgraded verdict to this path (default: overwrite --verdict)")
    args = ap.parse_args(argv)

    data = _load(args.verdict)
    mutated, violations = _check_and_upgrade(data)

    if violations:
        for v in violations:
            print(f"UNCITED: {v}", file=sys.stderr)
        if not args.check_only:
            out_path = args.out or args.verdict
            tmp = out_path.with_suffix(out_path.suffix + ".tmp")
            with tmp.open("w") as fh:
                _yaml.dump(mutated, fh)
            tmp.replace(out_path)
            print(
                f"Upgraded {len(violations)} uncited finding(s) to BLOCKER "
                f"(verdict={mutated.get('verdict')}) -> {out_path}"
            )
        return 1

    n_findings = len(data.get("findings", []))
    print(f"OK: all {n_findings} finding(s) have citations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

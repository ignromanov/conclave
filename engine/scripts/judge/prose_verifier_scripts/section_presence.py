#!/usr/bin/env python3
"""section_presence.py — deterministic floor: verify required sections present in a prose artifact.

Part of the prose-verifier suite (spec 089 D14 — deterministic scripts first).
Checks that each required section heading (markdown ## or deeper) is present in the artifact.
Case-insensitive match by default; use --case-sensitive to override.

Usage:
    python section_presence.py \\
        --artifact <path> \\
        --required-sections "Summary" "Acceptance Criteria" "Risks" \\
        [--case-sensitive]

    # Or supply sections from a file (one per line):
    python section_presence.py --artifact <path> --sections-file required-sections.txt

Exit codes (ADR-0003): 0 all sections present · 1 missing sections · 2 missing file
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_HEADING_RE = re.compile(r"^#{2,}\s+(.+)$", re.MULTILINE)


def _extract_headings(text: str) -> list[str]:
    return [m.group(1).strip() for m in _HEADING_RE.finditer(text)]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Verify required markdown sections are present in a prose artifact (D14 floor)"
    )
    ap.add_argument("--artifact", required=True, type=Path)
    ap.add_argument("--required-sections", nargs="*", default=[],
                    help="Section heading texts that must be present")
    ap.add_argument("--sections-file", type=Path, default=None,
                    help="File with required section names, one per line (# lines are comments)")
    ap.add_argument("--case-sensitive", action="store_true")
    args = ap.parse_args(argv)

    if not args.artifact.is_file():
        print(f"ERROR: artifact not found: {args.artifact}", file=sys.stderr)
        sys.exit(2)

    required = list(args.required_sections)
    if args.sections_file:
        if not args.sections_file.is_file():
            print(f"ERROR: sections file not found: {args.sections_file}", file=sys.stderr)
            sys.exit(2)
        for line in args.sections_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                required.append(line)

    if not required:
        print("WARN: no required sections specified — trivially passing", file=sys.stderr)
        return 0

    text = args.artifact.read_text()
    headings = _extract_headings(text)

    def norm(s: str) -> str:
        return s if args.case_sensitive else s.lower()

    normalised = [norm(h) for h in headings]
    missing = [r for r in required if norm(r) not in normalised]

    if missing:
        for m in missing:
            print(f"MISSING SECTION: {m!r}", file=sys.stderr)
        print(
            f"FAIL: {len(missing)}/{len(required)} required section(s) absent in {args.artifact}"
        )
        return 1

    print(f"PASS: all {len(required)} required section(s) present in {args.artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

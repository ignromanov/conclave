#!/usr/bin/env python3
"""ac_grep.py — deterministic floor: verify mandatory AC phrases are present in a prose artifact.

Part of the prose-verifier suite (spec 089 D14 / D17 — verifiable criteria, behavioral anchors).
Greps for required acceptance-criteria phrases in the artifact. Each phrase is a mandatory
behavioral anchor that must appear; absence = FAIL for that criterion.

Usage:
    python ac_grep.py \\
        --artifact <path> \\
        --phrases "schema_version" "oracle_grounded" "sample_count" \\
        [--case-sensitive] [--whole-word]

    # Or supply phrases from a file (one per line, # lines are comments):
    python ac_grep.py --artifact <path> --phrases-file ac-phrases.txt

Exit codes (ADR-0003): 0 all phrases found · 1 missing phrases · 2 missing file
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def _compile(phrase: str, case_sensitive: bool, whole_word: bool) -> re.Pattern:
    escaped = re.escape(phrase)
    if whole_word:
        escaped = r"\b" + escaped + r"\b"
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(escaped, flags)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Grep for mandatory AC phrases in a prose artifact (D14/D17 behavioral-anchor floor)"
    )
    ap.add_argument("--artifact", required=True, type=Path)
    ap.add_argument("--phrases", nargs="*", default=[],
                    help="Mandatory phrases that must appear in the artifact")
    ap.add_argument("--phrases-file", type=Path, default=None,
                    help="File with mandatory phrases, one per line (# lines are comments)")
    ap.add_argument("--case-sensitive", action="store_true")
    ap.add_argument("--whole-word", action="store_true",
                    help="Match whole words only (word-boundary anchors)")
    args = ap.parse_args(argv)

    if not args.artifact.is_file():
        print(f"ERROR: artifact not found: {args.artifact}", file=sys.stderr)
        sys.exit(2)

    phrases = list(args.phrases)
    if args.phrases_file:
        if not args.phrases_file.is_file():
            print(f"ERROR: phrases file not found: {args.phrases_file}", file=sys.stderr)
            sys.exit(2)
        for line in args.phrases_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                phrases.append(line)

    if not phrases:
        print("WARN: no phrases specified — trivially passing", file=sys.stderr)
        return 0

    text = args.artifact.read_text()
    missing = [
        p for p in phrases
        if not _compile(p, args.case_sensitive, args.whole_word).search(text)
    ]

    if missing:
        for m in missing:
            print(f"MISSING PHRASE: {m!r}", file=sys.stderr)
        print(
            f"FAIL: {len(missing)}/{len(phrases)} required phrase(s) absent in {args.artifact}"
        )
        return 1

    print(f"PASS: all {len(phrases)} required phrase(s) found in {args.artifact}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

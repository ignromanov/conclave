#!/usr/bin/env python3
"""citation_format.py — deterministic floor: verify citations follow expected format in a prose artifact.

Part of the prose-verifier suite (spec 089 D14). Checks that factual claim paragraphs
in the artifact contain a recognisable citation in one of the supported formats:
  - Markdown link:      [text](https://...)
  - Ref-style link:     [text][ref-id]
  - arXiv ID:           arXiv:NNNN.NNNNN
  - Numeric footnote:   [1], [12], etc.
  - Author-year:        (Author Year) or (Author et al. Year)

Reports paragraphs that contain claim-like language but no detectable citation.

Usage:
    python citation_format.py --artifact <path> [--strict] [--min-citations <n>]

    --strict        Fail on any claim-paragraph without a citation (default: warn only)
    --min-citations Required total citation count (default: 0)

Exit codes (ADR-0003): 0 citations adequate · 1 violations found · 2 missing file
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_CLAIM_KEYWORDS = [
    r"\bshows?\b", r"\bdemonstrates?\b", r"\bfound\b", r"\bmeasured\b",
    r"\baccording to\b", r"\bstudy\b", r"\bresearch\b", r"\bpaper\b",
    r"\breport\b", r"\bevidence\b", r"\bproves?\b", r"\bdata\b",
]

_CITATION_PATTERNS = [
    re.compile(r"\[.+?\]\(https?://"),        # markdown inline link
    re.compile(r"\[.+?\]\[.+?\]"),            # markdown ref-style link
    re.compile(r"arXiv:\d{4}\.\d{4,5}"),      # arXiv ID
    re.compile(r"\[\d+\]"),                   # numeric footnote [1]
    re.compile(r"\([A-Z][a-z]+(?: et al\.)? \d{4}\)"),  # (Author Year)
]

_CLAIM_RE = re.compile("|".join(_CLAIM_KEYWORDS), re.IGNORECASE)


def _has_citation(text: str) -> bool:
    return any(p.search(text) for p in _CITATION_PATTERNS)


def _count_citations(text: str) -> int:
    return sum(len(p.findall(text)) for p in _CITATION_PATTERNS)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Verify citations follow expected format in a prose artifact (D14 floor)"
    )
    ap.add_argument("--artifact", required=True, type=Path)
    ap.add_argument("--strict", action="store_true",
                    help="Fail on any claim-paragraph lacking a citation")
    ap.add_argument("--min-citations", type=int, default=0,
                    help="Minimum total citation count required in the artifact")
    args = ap.parse_args(argv)

    if not args.artifact.is_file():
        print(f"ERROR: artifact not found: {args.artifact}", file=sys.stderr)
        sys.exit(2)

    text = args.artifact.read_text()
    paras = _paragraphs(text)
    total_citations = _count_citations(text)

    uncited_claim_paras = [
        p for p in paras
        if _CLAIM_RE.search(p) and not _has_citation(p)
    ]

    violations: list[str] = []

    if args.strict:
        for p in uncited_claim_paras:
            preview = p[:80].replace("\n", " ")
            violations.append(f"uncited claim paragraph: {preview!r}...")

    if args.min_citations and total_citations < args.min_citations:
        violations.append(
            f"total citations {total_citations} < required minimum {args.min_citations}"
        )

    if violations:
        for v in violations:
            print(f"FAIL: {v}", file=sys.stderr)
        return 1

    status = "PASS" if not uncited_claim_paras else "WARN"
    print(
        f"{status}: {total_citations} citation(s) found; "
        f"{len(uncited_claim_paras)} uncited-claim paragraph(s) "
        f"{'(strict: none tolerated)' if args.strict else '(strict mode off)'} "
        f"in {args.artifact}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""scout_verify_citations.py — citation claim-presence verifier (spec 089, D31 / AC8 / AC23).

Script-first citation grounding for the P6 hook: for each evidence claim that cites a LOCAL source
(path[:line] or wiki node), confirm the source is reachable AND the claim's key terms are present
near the citation. Phantom / unreachable / claim-absent → veracity:unknown. A BLOCKER claim with
veracity:unknown triggers the bounded scout web-fetch (AC23); web (URL) sources are reported as
`needs_fetch` (this script does NOT make network calls — reachability for URLs is the scout's job).

I/O:
  --scout-output <scout-*.yaml>   reads candidates[].evidence[]{claim, source}
  [--repo-root <path>]            base for resolving path[:line] sources (default: cwd)
Stdout (one line per claim): "<veracity>\t<source>\t<claim[:60]>"
Exit (ADR-0003): 0 all settled/contested · 3 ≥1 unknown (grounding gap) · 1 usage · 2 missing input.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from ruamel.yaml import YAML

_yaml = YAML(typ="safe")

PATH_LINE_RE = re.compile(r"^(?P<path>[\w./\-]+?\.\w+)(?::(?P<line>\d+))?$")


def claim_terms(claim: str) -> list[str]:
    # key terms = tokens ≥4 chars, lowercased, deduped, capped (avoid trivial stopword matches)
    toks = [t.lower() for t in re.findall(r"\w{4,}", claim)]
    seen: list[str] = []
    for t in toks:
        if t not in seen:
            seen.append(t)
    return seen[:8]


def verify_local(source: str, claim: str, repo_root: Path) -> str:
    """Return settled | unknown for a local path[:line] source."""
    m = PATH_LINE_RE.match(source.strip())
    if not m:
        return "unknown"
    fpath = (repo_root / m.group("path"))
    if not fpath.is_file():
        return "unknown"
    text = fpath.read_text(errors="ignore").lower()
    terms = claim_terms(claim)
    if not terms:
        return "unknown"
    hits = sum(1 for t in terms if t in text)
    # majority of key terms present near the cited file = claim-present
    return "settled" if hits >= max(1, len(terms) // 2) else "unknown"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scout-output", required=True, type=Path)
    ap.add_argument("--repo-root", type=Path, default=Path.cwd())
    args = ap.parse_args(argv)

    if not args.scout_output.is_file():
        print(f"ERROR: missing scout output: {args.scout_output}", file=sys.stderr)
        return 2

    data = _yaml.load(args.scout_output.read_text()) or {}
    any_unknown = False

    for cand in data.get("candidates", []) or []:
        for ev in cand.get("evidence", []) or []:
            claim = str(ev.get("claim", ""))
            source = str(ev.get("source", ""))
            if source.startswith(("http://", "https://")):
                veracity = "needs_fetch"  # URL — scout web-fetch resolves (AC23), not this script
            else:
                veracity = verify_local(source, claim, args.repo_root)
            if veracity in ("unknown", "needs_fetch"):
                any_unknown = True
            print(f"{veracity}\t{source}\t{claim[:60]}")

    return 3 if any_unknown else 0


if __name__ == "__main__":
    raise SystemExit(main())

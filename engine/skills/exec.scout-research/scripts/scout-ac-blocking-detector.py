#!/usr/bin/env python3
"""scout_ac_blocking_detector.py — P2 spec-enrichment trigger (spec 089, D31 / AC22).

A P1 scout `contested[]`/`unknown[]` item is **AC-blocking** when an UNSEALED AC entry in
contract.md references it — meaning the planner cannot seal that criterion without resolving the
gap. Fires the bounded P2 scout lookup (≤10k). When no AC-blocking gap exists, the hook is skipped.

I/O:
  --contract <contract.md>     reads ac_entries[]{ac_id, text, sealed}
  --scout-output <scout-*.yaml> reads contested[] + unknown[] (lists of short tokens/phrases)
Stdout (one line per blocking item): "<ac_id>\t<contested-or-unknown-token>"
Exit (ADR-0003): 0 no AC-blocking gap (skip hook) · 3 ≥1 AC-blocking gap (fire P2 lookup) · 1/2 errors.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import frontmatter
from ruamel.yaml import YAML

_yaml = YAML(typ="safe")


def _tokens(s: str) -> set[str]:
    return {t.lower() for t in re.findall(r"\w{4,}", s)}


def load_ac_entries(contract_path: Path) -> list[dict]:
    post = frontmatter.load(str(contract_path))
    entries = post.metadata.get("ac_entries")
    if isinstance(entries, list):
        return entries
    # Fallback: parse markdown "- [ ] ACn: text" checklist (unsealed = unchecked).
    out = []
    for m in re.finditer(r"^- \[( |x)\] (AC\d+):\s*(.+)$", post.content, re.MULTILINE):
        out.append({"ac_id": m.group(2), "text": m.group(3), "sealed": m.group(1) == "x"})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True, type=Path)
    ap.add_argument("--scout-output", required=True, type=Path)
    args = ap.parse_args(argv)

    for p in (args.contract, args.scout_output):
        if not p.is_file():
            print(f"ERROR: missing input: {p}", file=sys.stderr)
            return 2

    ac_entries = load_ac_entries(args.contract)
    data = _yaml.load(args.scout_output.read_text()) or {}
    gap_items = list(data.get("contested", []) or []) + list(data.get("unknown", []) or [])

    found = False
    for entry in ac_entries:
        if entry.get("sealed"):
            continue  # sealed criteria are not blockable
        ac_terms = _tokens(str(entry.get("text", "")))
        for item in gap_items:
            item_terms = _tokens(str(item))
            if item_terms and item_terms & ac_terms:
                print(f"{entry.get('ac_id', '?')}\t{item}")
                found = True

    return 3 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())

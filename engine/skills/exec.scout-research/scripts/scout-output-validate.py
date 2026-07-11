#!/usr/bin/env python3
"""scout_output_validate.py — injection-hardening for scout output (spec 089, AC27 / R4).

The scout P1 artifact reads the advisor-writable wiki — a Track-A prompt-injection surface
(MemoryGraft 47.9% persistent-compromise precedent). Before any consumer (planner at P2, judge at
P6) reads the scout artifact, this strips instruction-override patterns from the natural-language
fields. Returns the sanitized text + the list of stripped spans.

I/O:
  --input <scout-output.yaml|.txt>   the scout artifact (or raw NL field)
  [--out <file>]                     write sanitized copy (default: stdout report only)
Stdout: {valid: bool, stripped_count: int, stripped: [pattern, ...]}
Exit (ADR-0003): 0 clean · 3 override patterns found+stripped · 1 usage · 2 missing input.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Instruction-override patterns common to NL prompt-injection. Conservative — targets imperative
# override forms, not legitimate research prose. Case-insensitive.
OVERRIDE_PATTERNS = [
    r"ignore (all |the )?(previous|prior|above) (instructions|context|rules)",
    r"disregard (all |the )?(previous|prior|above)",
    r"you are now [a-z ]{0,40}(unrestricted|jailbroken|dan|developer mode)",
    r"system prompt[:\s]",
    r"</?(system|assistant|user)>",          # role-tag injection
    r"\bact as\b.{0,40}\b(admin|root|developer mode)\b",
    r"new instructions?[:\s]",
    r"override (the )?(safety|guard|filter)",
    r"print (your|the) (system )?prompt",
]
_COMPILED = [re.compile(p, re.IGNORECASE) for p in OVERRIDE_PATTERNS]


def sanitize(text: str) -> tuple[str, list[str]]:
    stripped: list[str] = []
    out = text
    for rx in _COMPILED:
        for m in rx.finditer(out):
            stripped.append(m.group(0))
        out = rx.sub("[STRIPPED:injection]", out)
    return out, stripped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    if not args.input.is_file():
        print(f"ERROR: missing input: {args.input}", file=sys.stderr)
        return 2

    raw = args.input.read_text()
    sanitized, stripped = sanitize(raw)

    if args.out is not None:
        args.out.write_text(sanitized)

    valid = len(stripped) == 0
    quoted = ", ".join(f'"{s}"' for s in stripped)
    print(f'{{"valid": {str(valid).lower()}, "stripped_count": {len(stripped)}, '
          f'"stripped": [{quoted}]}}')
    return 0 if valid else 3


if __name__ == "__main__":
    raise SystemExit(main())

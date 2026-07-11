"""enginelib/audit/architecture_doc.py — port of audit-architecture-doc.sh.

I/O-free: no print/argparse/sys.exit. Returns Findings for the adapter to format.

Three checks:
  1. §B scripts: every *.sh under scripts_dir (recursive, excl. /tests/ paths) appears in arch_file.
  2. last-reviewed freshness: missing→CRIT; unparseable→WARN; >30d→CRIT (stale); >14d→WARN.
  3. §C contracts: every *.md stem in contracts_dir (top-level) appears in arch_file;
     missing contracts_dir→WARN.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

from enginelib.audit import Findings


def run(arch_file: Path, scripts_dir: Path, contracts_dir: Path) -> Findings:
    crit: list[str] = []
    warn: list[str] = []

    if not arch_file.is_file():
        crit.append(f"ARCHITECTURE.md not found at {arch_file}")
        return Findings(crit=crit, warn=warn)

    arch_text = arch_file.read_text(encoding="utf-8")

    # ── Check 1: every non-test *.sh appears in arch_file ─────────────────────
    for sh in sorted(scripts_dir.rglob("*.sh")):
        if "/tests/" in str(sh):
            continue
        base = sh.name
        if base not in arch_text:
            crit.append(f"script '{base}' not found in ARCHITECTURE.md")

    # ── Check 2: last-reviewed freshness ───────────────────────────────────────
    m = re.search(r"^last-reviewed:\s*(.+)$", arch_text, re.MULTILINE)
    if not m:
        crit.append("last-reviewed frontmatter missing")
    else:
        raw = m.group(1).strip()
        try:
            reviewed = datetime.date.fromisoformat(raw)
            age = (datetime.date.today() - reviewed).days
            if age > 30:
                crit.append(f"last-reviewed {raw} is {age}d ago (>30d stale)")
            elif age > 14:
                warn.append(f"last-reviewed {raw} is {age}d ago (>14d, consider updating)")
        except ValueError:
            warn.append(f"could not parse last-reviewed date '{raw}'")

    # ── Check 3: every contract stem appears in arch_file ─────────────────────
    if not contracts_dir.is_dir():
        warn.append(f"contracts/ directory not found at {contracts_dir}")
    else:
        for con in sorted(contracts_dir.glob("*.md")):
            if con.stem not in arch_text:
                crit.append(f"contract '{con.name}' not found in ARCHITECTURE.md §C")

    return Findings(crit=crit, warn=warn)

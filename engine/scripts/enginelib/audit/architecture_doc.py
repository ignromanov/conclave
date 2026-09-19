"""enginelib/audit/architecture_doc.py — port of audit-architecture-doc.sh.

I/O-free: no print/argparse/sys.exit. Returns Findings for the adapter to format.

Four checks:
  1a. §B scripts: every *.sh under scripts_dir (recursive, excl. /tests/ paths) appears in arch_file.
  1b. the converse: every *.sh arch_file names exists under scripts_dir, unless the line naming it
      marks it retired. 1a walks the tree, so an empty tree makes it vacuous; 1b walks the
      document, so it still has something to grade once the scripts are gone.
  2. last-reviewed freshness: missing→CRIT; unparseable→WARN; >30d→CRIT (stale); >14d→WARN.
  3. §C contracts: every *.md stem in contracts_dir (top-level) appears in arch_file;
     missing contracts_dir→WARN.
"""
from __future__ import annotations

import datetime
import re
from pathlib import Path

from enginelib.audit import Findings

# Dots belong to the name: without them `apply-overlay.test.sh` yields the tail `test.sh`,
# a file that never existed, and the check demands its presence. The lookbehind stops a
# match starting mid-name for the same reason.
_SH_RE = re.compile(r"(?<![\w.-])[A-Za-z0-9_.-]+\.sh")
_RETIRED_RE = re.compile(r"\*\*(deleted|retired|removed)\b", re.IGNORECASE)


def run(arch_file: Path, scripts_dir: Path, contracts_dir: Path) -> Findings:
    crit: list[str] = []
    warn: list[str] = []

    if not arch_file.is_file():
        crit.append(f"ARCHITECTURE.md not found at {arch_file}")
        return Findings(crit=crit, warn=warn)

    arch_text = arch_file.read_text(encoding="utf-8")

    # ── Check 1: every non-test *.sh appears in arch_file ─────────────────────
    shipped = [sh for sh in sorted(scripts_dir.rglob("*.sh")) if "/tests/" not in str(sh)]
    for sh in shipped:
        if sh.name not in arch_text:
            crit.append(f"script '{sh.name}' not found in ARCHITECTURE.md")
    if not shipped:
        # The shell layer was ported to Python (spec 099) and no *.sh survives, so this check
        # now grades an empty set and passes over any document at all. It says so rather than
        # reporting a cleanliness it did not measure — and the direction it can never cover is
        # the live one: a document naming a script that is gone. `skills/forge-operations/
        # ARCHITECTURE.md` names 61 such scripts today, and this audit calls it clean.
        warn.append(
            f"no *.sh under {scripts_dir} — check 1 graded 0 scripts and proves nothing; "
            "it cannot see a script the document names but the tree does not have"
        )

    # ── Check 1b: every *.sh the document names exists ────────────────────────
    # The converse of check 1, and the only direction that can fail once the tree is empty.
    # A line that marks the script retired is declaring its absence, not claiming its presence:
    # ARCHITECTURE.md already writes those as `**deleted (spec 086)** — replaced by ...`, so the
    # audit reads the document's own convention instead of inventing a second one. Without this
    # exemption the check would fire on the honest rows and teach people to silence it.
    # `shipped` excludes tests; 1b must not, or a document naming a live *.test.sh is
    # reported as naming a ghost.
    on_disk = {sh.name for sh in scripts_dir.rglob("*.sh")}
    missing: list[str] = []
    for line in arch_text.splitlines():
        if _RETIRED_RE.search(line):
            continue
        for name in _SH_RE.findall(line):
            if name not in on_disk and name not in missing:
                missing.append(name)
    for name in missing:
        crit.append(
            f"ARCHITECTURE.md names '{name}', which does not exist under {scripts_dir} "
            "— mark the row retired or name the successor"
        )

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

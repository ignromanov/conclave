"""enginelib/audit/feedback_owners.py — report notebook owners no advisor answers to.

`feedback_triage.cmd_set` refuses a new write whose owner the roster does not hold.
That closes the door; this reports what was already inside when it closed.

Why it matters more than a naming blemish: an owner nothing resolves produces no
error anywhere. The briefing's `owed` scan, triage routing and every per-advisor
query filter on the field, so an item owned by a retired id is not late -- it is
absent, and absence has no error message. On this instance 71 live items name
`forge` (a real id until the 106 rename created `forge-chro`) or `sage` (a short
name typed at triage that was never an id at all).

Reports rather than refuses, on the `advisor_naming` precedent: the fix is a data
migration an operator has to choose, and a gate that merely rejected would leave
the instance no path out.

I/O-free apart from reading the index it is handed: no print/argparse/sys.exit.
"""
from __future__ import annotations

import json
from collections import Counter
from collections.abc import Collection
from pathlib import Path

from enginelib.audit import Findings

# Owners that are legitimately not advisors. `verify:auto` is stamped by the
# auto-close path on every item its predicate resolves.
RESERVED_OWNERS = frozenset({"verify:auto"})


def run(index_path: Path, roster: Collection[str]) -> Findings:
    """Report every owner in the live index that *roster* does not hold."""
    findings = Findings()
    roster = set(roster)
    # Membership is unjudgeable without a roster, and judging anyway would report
    # every real advisor as unknown -- a false accusation reads as a finding (#170).
    if not roster or not index_path.is_file():
        return findings

    counts: Counter[str] = Counter()
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        owner = row.get("owner")
        if not owner or owner in RESERVED_OWNERS or owner in roster:
            continue
        counts[str(owner)] += 1

    for owner, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        findings.warn.append(
            f"{owner}: {n} item(s) owned by an id no advisor answers to. "
            f"Owner-scoped queries omit them silently. "
            f"Roster: {', '.join(sorted(roster))}."
        )
    return findings

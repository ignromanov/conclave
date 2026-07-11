"""enginelib.inbox — parse a legacy inbox.md into issue specs.

Public API:
  parse_inbox(text, advisor) -> list[IssueSpec]

Pure string processing: no I/O, no sys.exit, no argparse.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class IssueSpec:
    title: str
    labels: list[str] = field(default_factory=list)
    body: str = ""


def _detect_priority(text: str) -> str | None:
    """Return first priority marker p0/p1/p2 found as whole word, or None."""
    for level in ("0", "1", "2"):
        pattern = r"(^|[^a-zA-Z0-9])p" + level + r"([^a-zA-Z0-9]|$)"
        if re.search(pattern, text):
            return f"p{level}"
    return None


def parse_inbox(text: str, advisor: str) -> list[IssueSpec]:
    """Parse inbox markdown text; return one IssueSpec per non-done bullet."""
    specs = []
    for line in text.splitlines():
        if not line.startswith("- "):
            continue
        remainder = line[2:]  # strip leading "- "
        if remainder.startswith("[x] ") or remainder.startswith("[X] "):
            continue  # completed — skip silently
        if remainder.startswith("[ ] "):
            remainder = remainder[4:]
        title = remainder.rstrip()
        if not title:
            continue
        labels = [f"advisor:{advisor}"]
        prio = _detect_priority(title)
        if prio:
            labels.append(prio)
        body = f"Migrated from legacy inbox (advisor:{advisor})"
        specs.append(IssueSpec(title=title, labels=labels, body=body))
    return specs

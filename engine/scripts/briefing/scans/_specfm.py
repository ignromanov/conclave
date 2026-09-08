"""scans/_specfm.py — shared spec.md frontmatter reading for the spec-derived sections.

Four sections (spec_progress, roadmap, drift, owed) each answer a question about
ops/specs/*/spec.md, and each grew its own copy of "parse the frontmatter" and
"decide whether this spec is the advisor's". The copies drifted: drift.py folded
`_`/`-` in a status, owed.py compared the raw literal against `in_progress` — a
token no spec.md has ever carried — so its section had never rendered a row for
any advisor since it was built (#228).

Status normalisation is NOT here: `enginelib.spec.map_status` already owns it, and a
second spelling of a match key is how the first one drifted. This module holds only
what that one does not. It is pure: text in, values out, no file I/O.
"""
from __future__ import annotations

import re

# Matches the YAML frontmatter block at file top.
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text: str) -> dict[str, str]:
    """Return a flat dict of frontmatter key→value (scalar keys only, best-effort).

    Nested keys and list items are skipped rather than flattened: every consumer
    here reads scalars, and a partial parse that invents structure is worse than
    one that omits it.
    """
    m = _FM_RE.match(text)
    if not m:
        return {}
    out: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "-")):
            key, _, val = line.partition(":")
            out[key.strip()] = val.strip().strip('"')
    return out

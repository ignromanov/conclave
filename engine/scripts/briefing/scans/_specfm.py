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
            out[key.strip()] = _unquote(val)
    return out


def _unquote(val: str) -> str:
    """Strip one matched pair of surrounding quotes and undo the escapes inside it.

    `.strip('"')` — what every copy of this parser did — removes the quote CHARACTER
    from both ends, so a title that ends in an escaped quote loses its closing pair
    and keeps the backslash: spec 107 rendered as `truth for \\"who is an advisor\\`.
    The defect was invisible for as long as no section rendered a title.
    """
    val = val.strip()
    if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
        inner = val[1:-1]
        if val[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner.replace("''", "'")
    return val


# The engine's own retired id. Spec 106 renamed the shipped meta-advisor `forge` to
# `forge-chro`, and 11 spec files still carry the old spelling in an ownership field.
# This map holds engine renames ONLY: an instance's own retired ids are its data, and
# the fix for those is to correct the spec file, not to teach the engine an instance's
# history. Forge is the one agent present in every instance, which is why its rename
# is the one that ships (the same reason the output-formatting contract ships exactly
# one persona-emoji row).
_RETIRED_IDS = {"forge": "forge-chro"}

# Read in this order; the first match decides `matched_field`. `owner` leads because it
# is what REGISTRY.md and 23 of 28 specs carry, and reading it last would keep the
# section empty for exactly the specs it exists to show.
OWNER_FIELDS = ("owner", "advisor", "owner_suggestion")


def resolve_id(raw: str) -> tuple[str, bool]:
    """Return (canonical_id, inferred) for an ownership value.

    `inferred` is True when a retired id was mapped forward — the row renders it as
    `forge→forge-chro` so the reader can tell an alias from a direct claim.
    """
    raw = (raw or "").strip()
    mapped = _RETIRED_IDS.get(raw)
    return (mapped, True) if mapped else (raw, False)


def owns(fm: dict[str, str], advisor: str | None) -> str | None:
    """Return the name of the first ownership field naming *advisor*, else None.

    A spec belongs to an advisor when ANY of owner / advisor / owner_suggestion names
    them, after retired-id mapping. Reading only two of the three is why every
    spec-derived section rendered its placeholder for the advisor who owns four
    specs (#226).

    `advisor=None` is instance scope — owned by ANYONE — and returns the first
    ownership field carrying a value. `advisor=""` is not a scope and never was: it
    matched nobody, so three spec-derived sections answered "give me everything" with
    an empty render. ScanCtx now refuses to construct it (plan 057 T3).
    """
    for field in OWNER_FIELDS:
        value = fm.get(field)
        if not value:
            continue
        if advisor is None or resolve_id(value)[0] == advisor:
            return field
    return None


def provenance(fm: dict[str, str]) -> str:
    """Render every ownership field the spec carries, e.g. `(owner: forge→forge-chro)`.

    All of them, not just the one that matched: twelve specs carry two ownership
    fields and six of those disagree with each other. Showing only the matching field
    turns a contradiction in the data into a confident single attribution — wrong
    rather than merely empty, which is worse. An id that no alias moves is rendered
    as written, so nothing is dropped in silence.
    """
    parts: list[str] = []
    for field in OWNER_FIELDS:
        value = (fm.get(field) or "").strip()
        if not value:
            continue
        resolved, inferred = resolve_id(value)
        parts.append(f"{field}: {value}→{resolved}" if inferred else f"{field}: {value}")
    return f" ({' · '.join(parts)})" if parts else ""

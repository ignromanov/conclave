"""records.py — does a record still say what its writer was given? (#249 item 1)

The engine's readers of its own records are line-based on purpose: `fm_get` slices the
text after the colon and never consults YAML, and that is what keeps a frontmatter edit
from reformatting every untouched line. The cost is that the engine cannot see a record
whose YAML value is gone. `sessions/2026-09-14-sage-cto-117-mechanism-decided.md` carries
`issues: [#26]`, does not parse, and its reflexion still rendered in the next morning's
session-init banner — written five days AFTER the writer that produces that field learned
to quote it (#261), so it arrived by hand, where no serializer stands.

The predicate is LOSS, not disagreement. The two readers differ constantly and harmlessly
— `created: 2026-09-15T02:19:42-03:00` is text to one and a `datetime` to the other, a
different type carrying the same information. A first pass written as "report every
difference" flagged 32 of 30 mention records, and a gate with that ratio is read once.

Loss has exactly two shapes, and `#` produces both:

    key: #297                     -> None      the comment ate the whole value (#301)
    key: fixed by #68; and more   -> "fixed by"  the comment ate the tail (5 reflexions)

Everything else a YAML parser does to a plain scalar — coercing a date, a number, a flow
sequence — preserves the information and is not reported.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

# A top-level `key: value` line. Indented lines belong to a block scalar or a nested
# mapping, where the line-based view is not a value at all.
_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):(.*)$")

# The block indicators. On such a line the text after the colon is syntax, not a value,
# so there is nothing to compare — and comparing it would measure the reader, not the file.
_BLOCK_INDICATORS = frozenset({"|", "|-", "|+", ">", ">-", ">+"})

_FENCE_RE = re.compile(r"---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def _unquoted(text: str) -> str:
    """The value a YAML reader should produce from this plain-or-quoted scalar line."""
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        inner = text[1:-1]
        return inner.replace("''", "'") if text[0] == "'" else inner
    return text


def find_lost_values(fm_text: str) -> list[str]:
    """Return one finding per frontmatter value that did not survive being written.

    *fm_text* is the YAML between the fences, without them.
    """
    try:
        doc: Any = yaml.safe_load(fm_text)
    except yaml.YAMLError as exc:
        first = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
        return [f"the record does not parse — {exc.__class__.__name__}: {first}"]
    if not isinstance(doc, dict):
        return []

    findings: list[str] = []
    for line in fm_text.splitlines():
        m = _KEY_RE.match(line)
        if m is None:
            continue
        key, rest = m.group(1), m.group(2).strip()
        if not rest or rest in _BLOCK_INDICATORS or key not in doc:
            continue

        value = doc[key]
        if value is None:
            findings.append(
                f"{key}: the written value {rest!r} reads back as None — "
                f"a leading '#' comments the whole value out"
            )
            continue
        if isinstance(value, str):
            written = _unquoted(rest)
            if value != written and written.startswith(value):
                findings.append(
                    f"{key}: the written value {written!r} reads back truncated to "
                    f"{value!r} — an unquoted ' #' opens a comment"
                )
    return findings


def check_file(path: Path) -> list[str]:
    """Findings for one markdown record. A file without frontmatter has nothing to lose."""
    m = _FENCE_RE.match(Path(path).read_text(encoding="utf-8"))
    return find_lost_values(m.group(1)) if m else []

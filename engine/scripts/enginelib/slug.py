"""slug.py — slug-ification and id generators (ASCII-only). Port of lib/slug.sh."""
import re

_PLACEHOLDER = "untitled"
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    out = _NON_ALNUM.sub("-", text.lower()).strip("-")[:40].rstrip("-")
    return out or _PLACEHOLDER


def mention_id(frm: str, to: str, body: str, ts: str) -> str:
    if len(ts) < 16:
        raise ValueError(
            f"mention_id: ts must be ISO-8601 with time component (got: {ts})")
    date = ts[:10]
    hhmm = ts[11:13] + ts[14:16]
    return f"{date}-{hhmm}-{frm}-to-{to}-{slugify(body)}"


def decision_id(slug: str, date: str) -> str:
    return f"{date}-{slug}"


def session_id(advisor: str, slug: str, date: str) -> str:
    return f"{date}-{advisor}-{slug}"

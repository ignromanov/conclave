"""duty.py — duty files (KAD) and the description↔body drift check (spec 091 §3).

A duty is a markdown file with YAML frontmatter. Its `description` is injected at startup
for every agent holding the duty; the body lazy-loads only when the duty triggers. That
asymmetry is the whole point of §3 — over-injection is the named top failure mode — and it
is also why the description is worth validating: it is the part that is always paid for,
and the part an editor most easily forgets to update.

Findings are returned on the loaded object, not raised. A duty with problems is still a
duty; the caller decides whether to refuse it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from briefing.frontmatter_io import read

from enginelib.duties.validate import Finding

#: agentskills.io standard. Spec §3 targets 30-80 tokens; the hard cap is the standard's.
DUTY_DESCRIPTION_MAX = 1024

#: Words carrying no topical signal. Overlap on these is not evidence of anything — without
#: this filter, any two English sentences would "match" and drift would never fire.
_STOPWORDS = frozenset("""
a an and are as at be been by for from has have if in into is it its of on or that the
their then there these they this to was were when where which while who will with you your
use used using when mentioned run runs
""".split())

_WORD = re.compile(r"[a-z0-9][a-z0-9_:-]*")


@dataclass
class Duty:
    id: str
    description: str
    goal: str
    triggers: list[str]
    body: str
    path: Path
    findings: list[Finding] = field(default_factory=list)


def template_path() -> Path:
    """The shipped KAD scaffold. Anchored to this file's location — the roster tree ships
    with the engine, so source-relative is the only stable anchor."""
    return (
        Path(__file__).resolve().parents[4]
        / "skills" / "forge-operations" / "roster" / "templates" / "DUTY.md"
    )


def _content_words(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2}


def load_duty(path: Path) -> Duty:
    """Parse a duty file and collect every problem with it."""
    meta, body = read(Path(path))
    findings: list[Finding] = []

    duty_id = str(meta.get("id") or "").strip()
    if not duty_id:
        findings.append(Finding("missing-id", f"{path.name}: duty has no `id`"))

    description = str(meta.get("description") or "").strip()
    if not description:
        findings.append(Finding(
            "empty-description",
            f"{path.name}: `description` is empty — it is the only part injected at startup",
        ))
    elif len(description) > DUTY_DESCRIPTION_MAX:
        findings.append(Finding(
            "description-too-long",
            f"{path.name}: `description` is {len(description)} chars, max "
            f"{DUTY_DESCRIPTION_MAX} (agentskills.io standard)",
        ))

    context = meta.get("context") or {}
    triggers = list(context.get("triggers") or []) if isinstance(context, dict) else []

    if description and body.strip() and not _content_words(description) & _content_words(body):
        findings.append(Finding(
            "drifted",
            f"{path.name}: `description` and body share no content words — the description "
            f"likely describes behaviour the body no longer has",
            severity="warning",
        ))

    return Duty(
        id=duty_id,
        description=description,
        goal=str(meta.get("goal") or "").strip(),
        triggers=triggers,
        body=body.strip(),
        path=Path(path),
        findings=findings,
    )

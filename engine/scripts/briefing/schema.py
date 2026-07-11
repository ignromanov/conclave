"""schema.py — pydantic v2 models for the 10 ops page types.

One frozen BaseModel per type (spec §4). `brief` is excluded — it is a compiled
artifact with no frontmatter schema requirement.

snake_case keys throughout (Obsidian Bases requires bracket-notation for hyphens;
pydantic needs no alias generator for snake_case). `type` is required on every page
because directory location is lost on promotion/copy to wiki.

`schema_version` is an integer (`1`), not a string — internal iteration counter,
not a public SemVer (see research/frontmatter-source-of-truth.md §R6a).

`created` is `datetime` (YYYY-MM-DDTHH:MM:SS) for session/handoff/meeting
(same-day ordering matters); `date` (YYYY-MM-DD) for the rest.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, Strict

# StrictInt rejects string coercion — `"1"` does not silently become `1`.
# Spec §4 and research R6a: schema_version is an integer iteration counter.
StrictInt = Annotated[int, Strict()]


class Spec(BaseModel, frozen=True):
    """ops/specs/###-*/spec.md"""

    type: Literal["spec"]
    status: Literal["proposed", "approved", "in_progress", "done", "archived", "cancelled"]
    id: str
    created: date
    updated: date
    owner: str
    schema_version: StrictInt
    # Optional fields
    related: list[str] | None = None
    retention: str | None = None
    frozen: bool | None = None
    tags: list[str] | None = None
    aliases: list[str] | None = None


class Session(BaseModel, frozen=True):
    """agent-memory/advisors/sessions/ — immutable; no `updated`."""

    type: Literal["session"]
    owner: str
    created: datetime
    schema_version: StrictInt
    # Optional fields
    duration: str | None = None
    sources: list[str] | None = None
    related: list[str] | None = None
    tags: list[str] | None = None


class Decision(BaseModel, frozen=True):
    """agent-memory/advisors/decisions/ — status adds `rejected` vs spec 077."""

    type: Literal["decision"]
    status: Literal["proposed", "approved", "promoted", "superseded", "rejected"]
    owner: str
    created: date
    confidence: str
    contested: bool
    promoted_to: str | None = None
    schema_version: StrictInt
    # Optional fields
    sources: list[str] | None = None
    related: list[str] | None = None
    retention: str | None = None
    tags: list[str] | None = None
    aliases: list[str] | None = None


class Mention(BaseModel, frozen=True):
    """agent-memory/advisors/mentions/"""

    type: Literal["mention"]
    source_session: str
    target_advisor: str
    # Derived from live data (mention.sh writes "open"; resolve-mention.sh writes "resolved").
    status: Literal["open", "resolved"]
    created: date
    schema_version: StrictInt
    # Optional fields
    related: list[str] | None = None
    tags: list[str] | None = None


class Feedback(BaseModel, frozen=True):
    """agent-memory/advisors/feedback/ — status adds `wontfix`."""

    type: Literal["feedback"]
    severity: str
    target: str
    # Derived from spec §4 + Iris followup: open / resolved / archived / wontfix.
    status: Literal["open", "resolved", "archived", "wontfix"]
    created: date
    schema_version: StrictInt
    # Optional fields
    related: list[str] | None = None
    tags: list[str] | None = None


class Handoff(BaseModel, frozen=True):
    """ops/handoffs/ — `from` is a reserved keyword; aliased as `from_`."""

    type: Literal["handoff"]
    # `from` is a Python keyword — use alias in serialization.
    from_: str = Field(alias="from")
    to: str
    created: datetime
    priority: str
    status: str
    schema_version: StrictInt
    # Optional fields
    state_at_handoff: str | None = None
    related: list[str] | None = None
    tags: list[str] | None = None

    model_config = {"populate_by_name": True}


class Retro(BaseModel, frozen=True):
    """ops/retros/"""

    type: Literal["retro"]
    spec: str
    owner: str
    created: date
    schema_version: StrictInt
    # Optional fields
    what_worked: str | None = None
    what_didnt: str | None = None
    tags: list[str] | None = None


class OpenQuestion(BaseModel, frozen=True):
    """ops/open-questions/"""

    type: Literal["open-question"]
    status: Literal["open", "answered", "abandoned", "superseded"]
    opened: date
    owner: str
    schema_version: StrictInt
    # Optional fields
    spec: str | None = None
    answered_by: str | None = None
    related: list[str] | None = None
    tags: list[str] | None = None


class Meeting(BaseModel, frozen=True):
    """ops/meetings/ — immutable."""

    type: Literal["meeting"]
    attendees: list[str]
    created: datetime
    schema_version: StrictInt
    # Optional fields
    agenda: list[str] | None = None
    outcomes: list[str] | None = None
    related: list[str] | None = None
    tags: list[str] | None = None


# Registry mapping `type` frontmatter value → model class.
# `brief` is intentionally excluded — compiled output, no frontmatter schema.
PAGE_TYPES: dict[str, type[BaseModel]] = {
    "spec": Spec,
    "session": Session,
    "decision": Decision,
    "mention": Mention,
    "feedback": Feedback,
    "handoff": Handoff,
    "retro": Retro,
    "open-question": OpenQuestion,
    "meeting": Meeting,
}

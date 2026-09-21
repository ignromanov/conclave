"""schema.py — pydantic v2 models for spec 086 feedback reviews."""
from __future__ import annotations

import hashlib
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Literal

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# `positive` added 2026-09-08 (spec 117 lens rewrite, operator-approved). Every other member
# names a defect, so the corpus could only ever be defects: 244 items, 0 positive. That was
# read for months as evidence that the retrospective prompts were breakage-shaped. The prompts
# were a contributing cause; the enum was a sufficient one — with nowhere to put a positive
# finding, no wording could have produced one. Admissible form is narrow by design and lives in
# the prompt, not here: "artefact X removed step Y", never "what worked well" (W3 rows 12/17).
Category = Literal["script-defect", "doc-contradiction", "naming-inconsistency",
                    "skill-inaccuracy", "skill-gap", "process-friction",
                    "data-access", "idea", "positive", "near-miss"]
Layer = Literal["infra", "skill", "contract", "memory", "workflow"]
Severity = Literal["low", "medium", "high", "critical"]
Frequency = Literal["first-time", "occasional", "every-dispatch"]
Status = Literal["open", "accepted", "in_progress", "resolved", "re-occurred", "rejected", "deferred", "acknowledged"]  # `acknowledged` is terminal for the two categories that name no fix (`positive`, `near-miss`): `resolved` would claim a repair that never happened and `rejected` would call a valid finding invalid, so both used to sit non-terminal forever (#250)  # `re-occurred` set by feedback_emit._reopen_matches when a new item's fingerprint matches a resolved item (any severity) — unless a live non-terminal dup exists, or the new item carries no `location.section`, in which case the match is file-level only and cannot distinguish a regression from a different defect in the same file (#59; spec 086 A4 / 093 §E, Reflexion §3 local-minima mitigation)
AgentType = Literal["advisor", "executor", "other"]


class Location(BaseModel):
    file: str | None = None
    line: int | None = None
    skill: str | None = None
    section: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> Location:
        if not (self.file or self.skill or self.section):
            raise ValueError("location needs file, skill, or section")
        if self.skill is not None:
            import re
            if not re.match(r"^(team|exec|workflow|util)\..+", self.skill):
                raise ValueError(
                    "location.skill must be a skill path slug "
                    "(team.*/exec.*/workflow.*/util.*), not an agent name"
                )
        return self


PredicateKind = Literal["grep-absent", "file-contains", "file-absent"]
# #170 — which tree a predicate's relative path is resolved against.
#   project: the instance's project root (holds .claude/ and the .conclave DATA root).
#   code:    the engine distribution root — the dir holding engine/, skills/, agents/,
#            commands/, docs/. On the dogfooding instance the two name the same
#            directory, which is why one root looked sufficient; in plugin mode, the
#            supported distribution shape, the engine is a separate checkout and every
#            engine-layer predicate resolved against the project escapes containment.
PredicateRoot = Literal["project", "code"]


class Predicate(BaseModel):
    """Structured, side-effect-free resolution check (no shell exec).

    - grep-absent:  file exists AND pattern NO LONGER present  -> resolved
    - file-contains: file exists AND pattern present           -> resolved
    - file-absent:  path no longer exists                      -> resolved
    """
    kind: PredicateKind
    root: PredicateRoot = "project"   # #170 — which tree `file`/`path` is relative to
    file: str | None = None
    path: str | None = None
    pattern: str | None = None

    @model_validator(mode="after")
    def _shape(self) -> Predicate:
        if self.kind in ("grep-absent", "file-contains"):
            if not self.file or not self.pattern:
                raise ValueError(f"{self.kind} needs file + pattern")
        if self.kind == "file-absent" and not self.path:
            raise ValueError("file-absent needs path")
        return self


class FeedbackItem(BaseModel):
    id: str
    category: Category
    layer: Layer
    location: Location
    fingerprint: str | None = None      # set by feedback_emit.py
    observation: str
    interpretation: str | None = None
    # Optional since 2026-09-08 (spec 117 lens rewrite, operator-approved). Mandatory, this
    # field was W3 row 20 — "what should we build next?" — required on every item, and that
    # row is rated CONFABULATED: solution-space speculation with no in-context referent. The
    # evidence gate below carries the mandate instead.
    #
    # Deliberately a plain optional and NOT a validator reading "required unless evidence".
    # `evidence` is already mandatory for every non-migrated item, so that branch would be
    # unreachable — a guard that can never fire, indistinguishable from a working one.
    suggested_fix: str | None = None
    severity: Severity
    frequency: Frequency
    occurrence_count: int | None = None
    evidence: str | None = None         # gate enforced below
    status: Status = "open"
    owner: str | None = None
    issue: int | None = None            # GH issue opened for this item at triage Step 4
    resolved_at: datetime | None = None
    accepted_at: str | None = None
    # #218 — stamped ONLY on the item a write path actually modifies (cmd_set,
    # cmd_set_verify), never backfilled onto siblings. Absent means unknown, not zero:
    # existing reviews predate this field and Global Constraint 2 forbids backfilling them.
    touched_at: datetime | None = None
    archived_at: str | None = None      # set by feedback_archive: item is in the ledger,
                                        # still verbatim here, and out of the working set
    migrated: bool = False
    legacy_source: str | None = None
    reopened_from: str | None = None    # 093 — provenance "fid:iid" when status re-occurred
    notes: str | None = None  # DEPRECATED 2026-05-26 (spec 086, ELEPHANT §2/3.2/5); read-only for legacy graceful-read, not emitted by feedback_emit.py
    verify: Predicate | None = None     # 093 — structured resolution check
    # 093/#165 — the recorded reason an item can carry NO predicate. A real field, not a
    # convention, so predicate coverage can distinguish a deliberate waiver from an
    # omission: an unmeasurable waiver is indistinguishable from forgetting.
    verify_waiver: str | None = None

    @field_validator("location", mode="before")
    @classmethod
    def _coerce_location_str(cls, v: object) -> object:
        # Author shorthand: a bare-string location → {file: <path>}. The most
        # common authoring slip (a path written where a typed object is expected).
        if isinstance(v, str):
            return {"file": v}
        return v

    @model_validator(mode="after")
    def _evidence_gate(self) -> FeedbackItem:
        if not self.migrated and not self.evidence:
            raise ValueError("evidence is mandatory unless migrated")
        return self


class Review(BaseModel):
    feedback_id: str
    agent: str
    agent_type: AgentType
    session_ref: str
    created: datetime
    updated_at: datetime
    skill_version: str
    summary: str
    items: list[FeedbackItem] = []
    below_threshold_count: int = 0
    draft: bool = Field(default=False, alias="_draft")  # YAML key is _draft — frontmatter_io emits this literally
    trace_ref: str | None = None          # G4 — populated from CLAUDE_SESSION_ID if set
    parent_session_ref: str | None = None  # G9 — populated from CLAUDE_PARENT_SESSION if set
    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _minimum_item_rule(self) -> Review:
        if self.below_threshold_count > 0 and not self.items:
            raise ValueError("below_threshold_count > 0 forbids empty items[]")
        return self


def fingerprint(location: Location | dict, category: str) -> str:
    """Normalized (location, category) dedup key — reused by emit/index/triage."""
    loc = location if isinstance(location, dict) else location.model_dump()
    base = loc.get("file") or loc.get("skill") or loc.get("section") or ""
    norm = base.strip().lower().rstrip("/")   # so `emit.py:42` ~ `emit.py`
    # Keep distinct findings in the same file/skill apart by section (function/heading),
    # while still ignoring line noise. Only when base is a file/skill — else section IS base.
    section = loc.get("section") if (loc.get("file") or loc.get("skill")) else ""
    if section:
        norm = f"{norm}#{section.strip().lower()}"
    return hashlib.sha256(f"{norm}|{category}".encode()).hexdigest()[:12]


def schema_errors(meta: Mapping[str, object]) -> list[str]:
    """Why `Review.model_validate` would reject this frontmatter, one line per fault.

    THE SINGLE DEFINITION OF "fileable". Before GH#310 there were three: a
    `re.search(r"^_draft: false")` in `enginelib/filing.py`, `model_validate` over
    `read_commented` in `feedback_emit._finalize`, and `model_validate` over `fm_read` in
    `feedback_index` — two YAML engines behind two readers, and a string search in front
    of the gate every session runs. The regex was the one that decided whether a session
    could close, and it could not tell a validated review from a hand-edited malformed
    one because it was not looking at the schema at all.

    Returns [] for a review the indexer would accept. Says nothing about `_draft`: a
    draft validates clean (the field is an ordinary optional with a default), so "is it
    finished" is a separate question from "is it well-formed", and a caller that needs
    both must ask both. Collapsing them is the regression `test_a_valid_draft_still_blocks`
    exists to catch.

    Item faults are reported against the item's OWN id rather than only its index.
    Pydantic locates `items.1.location`, and an author looking at a file where the ids
    read i1, i2, i4, i5 has to count to find it — which is the same "correct but
    unactionable" failure the bare `exited 1` produced two days downstream.
    """
    try:
        Review.model_validate(dict(meta))
    except ValidationError as exc:
        return [_render_error(err, meta) for err in exc.errors()]
    return []


def _render_error(err: Mapping[str, Any], meta: Mapping[str, object]) -> str:
    loc: tuple[Any, ...] = tuple(err.get("loc") or ())
    dotted = ".".join(str(part) for part in loc)
    label = dotted
    if len(loc) >= 2 and loc[0] == "items" and isinstance(loc[1], int):
        raw_items = meta.get("items")
        if isinstance(raw_items, list) and loc[1] < len(raw_items):
            entry = raw_items[loc[1]]
            item_id = entry.get("id") if isinstance(entry, Mapping) else None
            if item_id:
                label = f"{dotted} ({item_id})"
    return f"{label}: {err.get('msg', 'invalid')}"

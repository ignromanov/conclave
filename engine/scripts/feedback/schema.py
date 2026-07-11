"""schema.py — pydantic v2 models for spec 086 feedback reviews."""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

Category = Literal["script-defect", "doc-contradiction", "naming-inconsistency",
                    "skill-inaccuracy", "skill-gap", "process-friction",
                    "data-access", "idea"]
Layer = Literal["infra", "skill", "contract", "memory", "workflow"]
Severity = Literal["low", "medium", "high", "critical"]
Frequency = Literal["first-time", "occasional", "every-dispatch"]
Status = Literal["open", "accepted", "in_progress", "resolved", "re-occurred", "rejected", "deferred"]  # `re-occurred` set by feedback_emit._reopen_matches when a new item's fingerprint matches a resolved item (any severity), unless a live non-terminal dup exists (spec 086 A4 / 093 §E, Reflexion §3 local-minima mitigation)
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


class Predicate(BaseModel):
    """Structured, side-effect-free resolution check (no shell exec).

    - grep-absent:  file exists AND pattern NO LONGER present  -> resolved
    - file-contains: file exists AND pattern present           -> resolved
    - file-absent:  path no longer exists                      -> resolved
    """
    kind: PredicateKind
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
    suggested_fix: str
    severity: Severity
    frequency: Frequency
    occurrence_count: int | None = None
    evidence: str | None = None         # gate enforced below
    status: Status = "open"
    owner: str | None = None
    resolved_at: datetime | None = None
    accepted_at: str | None = None
    migrated: bool = False
    legacy_source: str | None = None
    reopened_from: str | None = None    # 093 — provenance "fid:iid" when status re-occurred
    notes: str | None = None  # DEPRECATED 2026-05-26 (spec 086, ELEPHANT §2/3.2/5); read-only for legacy graceful-read, not emitted by feedback_emit.py
    verify: Predicate | None = None     # 093 — structured resolution check

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

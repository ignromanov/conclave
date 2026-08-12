"""model.py — pydantic v2 models for the protocol registry (spec 108 §5).

Applicability is DECLARED, not inferred. Inferring it from prose would be semantic
matching, which is the mechanism measured to leave a skill uninvoked in 56% of runs
(evidence-ledger B4). Every axis is required and closed: an absent axis meaning
"applies to everything" is the documented ESLint/VS Code trap, and unknown values are
rejected from day one because Kubernetes had to tighten CRDs only after v1beta1
permissiveness caused problems.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

Stage = Literal["clarify", "design", "spec", "plan", "implement", "verify", "deliver"]
Tier = Literal["quick", "work"]
TaskType = Literal["dev", "content", "research", "review", "advisory"]
Binding = Literal["required", "advisory"]

#: The one hardcoded constant. Assembly orders selected protocols by this.
STAGE_SEQUENCE: tuple[str, ...] = (
    "clarify", "design", "spec", "plan", "implement", "verify", "deliver",
)


class ProtocolMeta(BaseModel):
    """Frontmatter of one registry file.

    `external_skill` present ⇒ this file is an ADAPTER: it carries the applicability
    declaration while the content lives in a third-party skill we do not own and must
    not edit (design §3.1).
    """

    stages: list[Stage] = Field(min_length=1)
    tiers: list[Tier] = Field(min_length=1)
    task_types: list[TaskType] = Field(min_length=1)
    binding: Binding
    last_reviewed: str | None = None
    external_skill: str | None = None

    @property
    def is_adapter(self) -> bool:
        return self.external_skill is not None

    def earliest_stage_index(self) -> int:
        """A protocol claiming several stages sorts by its earliest (design §5.1)."""
        return min(STAGE_SEQUENCE.index(s) for s in self.stages)


@dataclass(frozen=True)
class ProtocolFile:
    path: Path
    meta: ProtocolMeta

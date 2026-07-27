"""model.py — pydantic v2 models for the deontic duty registry (spec 091 §2).

The deontic tuple:

    {type: obligation|permission|advice, role, mission, condition, priority}

`condition` is a STRING the LLM evaluates in context. Research §E rejects a runtime policy
engine (OPA/Cedar/XACML) explicitly; this module validates that the string is present and
non-blank and does nothing else with it. Adding an expression grammar here would be that
rejected design re-entering through the back door.

Capabilities are not a separate subsystem: a capability is a `permission` norm over a
capability-mission (`cap_web_search`, `cap_code_execution`). One vocabulary, not two.
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

DeonticType = Literal["obligation", "permission", "advice"]
AgentKind = Literal["advisor", "executor"]

#: Abstract roles every instance inherits. Concrete roles are instance data.
ABSTRACT_ROLES = ("all", "kind:advisor", "kind:executor")


class Role(BaseModel):
    """A role a norm can attach to. `inherits` names parents — typically an abstract role,
    which is how base norms reach concrete role-holders without being duplicated."""

    id: str
    kind: AgentKind
    inherits: list[str] = Field(default_factory=list)


class Mission(BaseModel):
    """A reusable goal bundle. Norms attach to (role, mission) pairs rather than to bare
    prose, which is what gives a norm a stable identity to be audited by."""

    id: str
    goal: str


class Norm(BaseModel):
    type: DeonticType
    role: str
    mission: str
    condition: str | None = None
    priority: int = 100
    co_sign_with: list[str] = Field(default_factory=list)

    @field_validator("condition")
    @classmethod
    def _condition_not_blank(cls, v: str | None) -> str | None:
        """Absent `condition` means unconditional. A blank string means someone meant to
        write one — the two must not collapse into each other silently."""
        if v is not None and not v.strip():
            raise ValueError("condition must be non-blank prose, or omitted entirely")
        return v


class Manifest(BaseModel):
    """A roster file: the engine base, or one agent's self-written declarations."""

    version: int
    roles: list[Role] = Field(default_factory=list)
    missions: list[Mission] = Field(default_factory=list)
    norms: list[Norm] = Field(default_factory=list)


#: Models exported as JSON-Schema into roster/schema/. Single owner of the fact; the
#: committed files are generated, never hand-edited (test_roster_schema asserts lockstep).
#: `duty` joins in Task 4, when the duty model exists. An entry here must name a real model —
#: a placeholder would publish a schema that describes something other than what it claims.
SCHEMA_FILES: dict[str, type[BaseModel]] = {
    "manifest": Manifest,
    "mission": Mission,
    "norm": Norm,
    "role": Role,
}


def schema_dir() -> Path:
    """The engine-owned schema dir: skills/forge-operations/roster/schema/.

    Resolved from this file's location rather than from cwd or an env var — the tree ships
    with the engine, so its position relative to the source is the only stable anchor.
    """
    return (
        # roster -> enginelib -> scripts -> engine -> repo root
        Path(__file__).resolve().parents[4]
        / "skills"
        / "forge-operations"
        / "roster"
        / "schema"
    )

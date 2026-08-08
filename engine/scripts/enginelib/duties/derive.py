"""derive.py — a duty file becomes a norm the registry can see (spec 091 P2 §0).

`check_discharge` iterates norms. A duty that never enters the norm namespace can therefore
never be owed, and a session that skipped it reports clean — the seam this module closes.

Every duty derives **advice**: visible in the registry, not yet binding. Force is the
operator's to grant, from `.conclave/roster/norms.yaml`, because a duty that could declare
its own force would hand the key to the very agent the check exists to catch.

Derivation emits all three of Role, Mission and Norm. Emitting only the norm is not a
smaller version of this — it is a different design, in which the operator must hand-write
three YAML blocks to elevate one duty. The cost of elevation is what decides whether the
mechanism is used at all.

I/O-free: takes loaded duties, returns a Manifest.
"""
from __future__ import annotations

from pathlib import Path

from enginelib.duties.duty import Duty, load_duty
from enginelib.duties.model import AgentKind, Manifest, Mission, Norm, Role

#: Derived advice sits far below the `Norm.priority` default of 100, so an operator norm
#: written without any thought about numbers still outranks it. Lower wins (Nix convention).
#: Do not narrow this gap: the margin is what lets the default be "the operator is right".
DERIVED_PRIORITY = 900


def load_duties(duties_dir: Path | None) -> list[Duty]:
    """Every duty file an agent holds, id-sorted. An absent dir is no duties, not an error —
    a fresh agent has written none.

    The single reader: the projection and the discharge check must see the same set, or the
    registry can show one thing and enforce another.
    """
    if duties_dir is None or not duties_dir.is_dir():
        return []
    return sorted((load_duty(p) for p in sorted(duties_dir.glob("*.md"))), key=lambda d: d.id)


def derive(duties: list[Duty], agent_id: str, kind: AgentKind) -> Manifest:
    """Project an agent's duty files into a manifest of role + missions + advice norms.

    An agent with no duties derives nothing — not an empty role. A role declared with no
    norm attached to it is a dangling declaration the validator would have to explain away.
    """
    if not duties:
        return Manifest(version=1)

    missions: dict[str, Mission] = {}
    norms: list[Norm] = []
    for duty in duties:
        mission_id = duty.mission or duty.id
        # A duty file is the single owner of its mission's goal; `missions.base.yaml` stays
        # the owner for engine-declared ones. Two homes for one fact was the P2 §0.4 defect.
        missions.setdefault(mission_id, Mission(id=mission_id, goal=duty.goal or duty.description))
        norms.append(Norm(
            type="advice",
            role=agent_id,
            mission=mission_id,
            condition=duty.condition,
            priority=DERIVED_PRIORITY,
        ))

    return Manifest(
        version=1,
        roles=[Role(id=agent_id, kind=kind, inherits=[f"kind:{kind}"])],
        missions=[missions[m] for m in sorted(missions)],
        norms=norms,
    )

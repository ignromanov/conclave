"""validate.py — composition and validation for the deontic registry (spec 091 §1/§2).

Pure: every function here takes models and returns models or findings. Invalid input is a
RESULT, not an exception — a validator that raises on the thing it exists to detect cannot
report more than one problem per run.

Composition semantics:
  - manifests merge (engine base first, agent manifests after) into one namespace;
  - a norm on an abstract role reaches every concrete role that inherits it;
  - the abstract tier is a PARTITION: `kind:advisor` and `kind:executor` do not reach each
    other. Only `all` reaches both.
  - precedence is `priority` alone (lower number wins, Nix convention). Source order never
    decides — otherwise file layout becomes policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from enginelib.roster.model import ABSTRACT_ROLES, Manifest, Mission, Norm, Role


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    severity: str = "error"


@dataclass
class Composed:
    """The merged registry: one role/mission namespace plus the full norm set."""

    roles: dict[str, Role] = field(default_factory=dict)
    missions: dict[str, Mission] = field(default_factory=dict)
    norms: list[Norm] = field(default_factory=list)

    def roles_reaching(self, role_id: str) -> set[str]:
        """Every role label whose norms apply to `role_id`: itself, its declared parents
        (transitively), and `all`."""
        seen: set[str] = {"all", role_id}
        frontier = [role_id]
        while frontier:
            current = frontier.pop()
            declared = self.roles.get(current)
            if declared is None:
                continue
            for parent in declared.inherits:
                if parent not in seen:
                    seen.add(parent)
                    frontier.append(parent)
        return seen

    def for_role(self, role_id: str) -> list[Norm]:
        """Effective norms for a concrete role, precedence resolved.

        One winner per (role-label, mission): the lowest `priority`. Ties are left intact —
        `validate()` reports them as conflicts rather than picking, so a conflicting pair
        can never be silently resolved by whichever file happened to load first.
        """
        reaching = self.roles_reaching(role_id)
        applicable = [n for n in self.norms if n.role in reaching]
        best: dict[str, Norm] = {}
        for norm in applicable:
            incumbent = best.get(norm.mission)
            if incumbent is None or norm.priority < incumbent.priority:
                best[norm.mission] = norm
        return [best[m] for m in sorted(best)]


def compose(manifests: list[Manifest]) -> Composed:
    """Merge manifests into one registry. Later manifests may add; they do not override by
    position — see `Composed.for_role`."""
    out = Composed()
    for manifest in manifests:
        for role in manifest.roles:
            out.roles[role.id] = role
        for mission in manifest.missions:
            out.missions[mission.id] = mission
        out.norms.extend(manifest.norms)
    return out


def validate(manifests: list[Manifest]) -> list[Finding]:
    """Return every problem in the composed registry. Empty list = clean."""
    composed = compose(manifests)
    findings: list[Finding] = []
    findings.extend(_check_references(composed))
    findings.extend(_check_parents(composed))
    findings.extend(_check_priority_conflicts(composed))
    return findings


def _known_role(composed: Composed, role_id: str) -> bool:
    return role_id in ABSTRACT_ROLES or role_id in composed.roles


def _check_references(composed: Composed) -> list[Finding]:
    """A norm pointing at a mission or role nobody declared is a norm that can never fire —
    and it fails silently, which is the worst way for an obligation to fail."""
    findings = []
    for norm in composed.norms:
        if norm.mission not in composed.missions:
            findings.append(Finding(
                "unknown-mission",
                f"norm on role '{norm.role}' references undeclared mission '{norm.mission}'",
            ))
        if not _known_role(composed, norm.role):
            findings.append(Finding(
                "unknown-role",
                f"norm on mission '{norm.mission}' references undeclared role '{norm.role}'",
            ))
    return findings


def _check_parents(composed: Composed) -> list[Finding]:
    findings = []
    for role in composed.roles.values():
        for parent in role.inherits:
            if not _known_role(composed, parent):
                findings.append(Finding(
                    "unknown-parent-role",
                    f"role '{role.id}' inherits undeclared role '{parent}'",
                ))
    return findings


def _check_priority_conflicts(composed: Composed) -> list[Finding]:
    """Two norms on the same (role, mission) at equal priority with DIFFERENT deontic types
    have no defined winner. Identical types are redundant, not contradictory — base and
    agent are allowed to assert the same obligation."""
    buckets: dict[tuple[str, str, int], set[str]] = {}
    for norm in composed.norms:
        buckets.setdefault((norm.role, norm.mission, norm.priority), set()).add(norm.type)
    findings = []
    for (role, mission, priority), types in buckets.items():
        if len(types) > 1:
            findings.append(Finding(
                "priority-conflict",
                f"role '{role}' × mission '{mission}' has {sorted(types)} both at priority "
                f"{priority} — no defined precedence; change one priority",
            ))
    return findings

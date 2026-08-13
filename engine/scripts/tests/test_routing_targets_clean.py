"""No shipped command names a routing target that does not exist (108 P1).

Red until the P1 deletions land. Runs against the real tree, no mocking — the same shape as
test_protocol_registry_clean.py, which P0 shipped for the registry.

The perimeter is commands/ + agents/ and not the whole tree, deliberately: at the full perimeter
the extra findings are almost entirely the team.* rename debt in contracts and architecture docs
(measured: 18 findings over 18 surfaces here, 38 over 96 there), which this phase excludes.
Widening is blocked on that rename — see plan-p1.md D-5.
"""
from __future__ import annotations

from pathlib import Path

from enginelib.audit import routing_targets as rt

REPO = Path(__file__).resolve().parents[3]

SURFACE_DIRS = [REPO / "commands", REPO / "agents"]
SKILLS_ROOTS = [REPO / "skills", REPO / "engine" / "skills"]


def _roster() -> frozenset[str]:
    """Bare advisor ids discovered from the agent defs — never a hardcoded list."""
    out: set[str] = set()
    for p in (REPO / "agents").glob("*.md"):
        out.add(p.stem.removeprefix("conclave-").removeprefix("exec-"))
    return frozenset(out)


def _surfaces() -> list[Path]:
    out: list[Path] = []
    for d in SURFACE_DIRS:
        out.extend(sorted(d.rglob("*.md")))
    return out


def test_every_surface_dir_exists():
    """Naming a directory that was renamed away shrinks the scan silently."""
    missing = [str(d.relative_to(REPO)) for d in SURFACE_DIRS if not d.is_dir()]
    assert missing == [], f"surface dirs missing: {missing}"


def test_the_surface_set_is_not_empty():
    """A gate that scans nothing passes for the wrong reason."""
    surfaces = _surfaces()
    assert len(surfaces) >= 15, f"only {len(surfaces)} surfaces found — the globs went stale"


def test_the_roster_is_discovered_and_not_empty():
    """An empty roster makes every team.<advisor> reference a false positive."""
    assert len(_roster()) >= 5, "roster discovery returned almost nothing — agents/ moved?"


def test_no_shipped_command_names_a_routing_target_that_does_not_exist():
    findings = rt.run(_surfaces(), SKILLS_ROOTS, _roster())
    assert findings.crit == [], "\n".join(findings.crit)

"""enginelib/audit/specs_registry.py — port of audit-specs-registry.sh.

I/O-free: no print/argparse/sys.exit. Returns Findings for the adapter to format.

Five defect classes:
  CRIT: unrunnable  — the gate cannot check (specs dir absent, or specs exist untraced)
  CRIT: collision   — two+ specs share the same NNN prefix
  WARN: untracked   — disk spec absent from REGISTRY
  WARN: dead-link   — REGISTRY entry has no matching spec
  WARN: hollow      — spec dir has neither spec.md nor plan.md

R6 made an absent registry clean. That collapsed two different states into one: "there is
nothing to trace" (a fresh instance — clean) and "there are specs and no way to trace them"
(the gate cannot run — CRIT). A gate that reports 0 CRIT because it was unable to check has
verified nothing; see the `scanned > 0` rule in tests/test_gates.py.

Specs are counted whether stored as `NNN-slug/` dirs or flat `NNN-slug.md` files; the dir-only
scan was blind to the live tree's flat layout and so passed vacuously on a non-empty tree.
"""
from __future__ import annotations

import re
from pathlib import Path

from enginelib.audit import Findings

# `NNN-slug.md` and its satellite `NNN-slug-plan.md` are one spec, not two (and not a collision).
_FLAT_SPEC_RE = re.compile(r"^(\d{3}-[a-z0-9-]+?)(?:-plan)?\.md$")


def _spec_names(specs_dir: Path) -> list[str]:
    """Spec identities on disk, from both storage shapes."""
    names = {
        d.name for d in specs_dir.iterdir()
        if d.is_dir() and re.match(r"^[0-9]", d.name)
    }
    for f in specs_dir.iterdir():
        if not f.is_file():
            continue
        m = _FLAT_SPEC_RE.match(f.name)
        if m:
            names.add(m.group(1))
    return sorted(names)


def run(specs_dir: Path, registry: Path) -> Findings:
    crit: list[str] = []
    warn: list[str] = []

    if not specs_dir.is_dir():
        crit.append(f"specs dir absent — the gate cannot run: {specs_dir}")
        return Findings(crit=crit, warn=warn)

    dirs = _spec_names(specs_dir)

    if not registry.is_file():
        if not dirs:
            return Findings(crit=crit, warn=warn)  # nothing to trace yet
        crit.append(
            f"REGISTRY.md absent while {len(dirs)} spec(s) exist — the gate cannot run: {registry}"
        )
        return Findings(crit=crit, warn=warn)

    # Registry: NNN-slug referenced by a link target — `(NNN-slug/...)` or flat `(NNN-slug.md)`.
    registry_text = registry.read_text(encoding="utf-8")
    linked = sorted(set(re.findall(r"\(([0-9]{3}-[a-z0-9-]+?)(?:-plan)?(?:/|\.md\))", registry_text)))

    # CRIT: ID collisions (same NNN prefix on 2+ dirs)
    prefixes: dict[str, list[str]] = {}
    for d in dirs:
        m = re.match(r"^(\d{3})-", d)
        if m:
            prefixes.setdefault(m.group(1), []).append(d)
    for prefix, dupes in sorted(prefixes.items()):
        if len(dupes) > 1:
            crit.append(f"spec-id collision {prefix} shared by: {' '.join(dupes)}")

    # WARN: untracked specs (on disk, not linked from REGISTRY)
    linked_set = set(linked)
    for d in dirs:
        if d not in linked_set:
            warn.append(f"untracked spec dir (no REGISTRY link): {d}")

    # WARN: dead links (linked from REGISTRY, spec absent on disk)
    dirs_set = set(dirs)
    for lnk in linked:
        if lnk not in dirs_set:
            warn.append(f"dead REGISTRY link (dir absent): {lnk}")

    # WARN: hollow specs (no spec.md and no plan.md) — dir-shaped specs only; a flat
    # NNN-slug.md carries its content in the file itself and cannot be hollow.
    for d in dirs:
        d_path = specs_dir / d
        if not d_path.is_dir():
            continue
        if not (d_path / "spec.md").is_file() and not (d_path / "plan.md").is_file():
            warn.append(f"hollow spec (no spec.md or plan.md): {d}")

    return Findings(crit=crit, warn=warn)

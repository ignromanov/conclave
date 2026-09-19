"""No shipped agent or command names an engine script that does not exist.

The sibling of test_routing_targets_clean.py, for the other half of what a surface can
point at: that one checks routing targets, this one checks the executable paths an
executor is told to run.

It exists because `agents/exec-socra-critic.md` step 5 said "Archive via
`scripts/critic/critic_log_archive.py`" for as long as that file has existed, from a root
where `scripts/` is not a directory — and the only visible consequence was that
`agent-memory/executors/socra-critic/runs/` stayed empty. An agent that cannot find the
script it was told to run does not raise; it moves on. That is the same silence as a
briefing source with no writer (#116) and a CLI no protocol invokes (093), reached from
the third direction: the protocol invokes it, at an address nothing answers.

Perimeter is commands/ + agents/, matching test_routing_targets_clean.py.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SURFACE_DIRS = [REPO / "commands", REPO / "agents"]

# `(?<![\w/.-])` keeps a longer path from matching at its own tail: without it
# `engine/scripts/judge/x.py` also yields the bare `scripts/judge/x.py`, and the gate
# reports a phantom finding for a reference that is correct.
_SCRIPT_REF = re.compile(r'(?<![\w/.-])((?:engine/)?scripts/[A-Za-z0-9_/]+\.py)')


def _surfaces() -> list[Path]:
    out: list[Path] = []
    for d in SURFACE_DIRS:
        out.extend(sorted(d.rglob("*.md")))
    return out


# A line that marks the script gone is declaring an absence, not claiming a presence. A
# retirement record has to be able to name what it retired — spec 121 removed
# `lifecycle/study_phase.py` and `commands/done.md` keeps the record of it — and a gate blind
# to that difference fires on the honest text and teaches people to delete the record instead.
# Same convention the charter and `skills/forge-operations/ARCHITECTURE.md` already use.
_RETIRED = re.compile(r"\*\*(deleted|retired|removed)\b", re.IGNORECASE)


def _references() -> dict[str, set[str]]:
    hits: dict[str, set[str]] = {}
    for p in _surfaces():
        for line in p.read_text(encoding="utf-8").splitlines():
            if _RETIRED.search(line):
                continue
            for m in _SCRIPT_REF.finditer(line):
                hits.setdefault(m.group(1), set()).add(str(p.relative_to(REPO)))
    return hits


def test_every_surface_dir_exists():
    """A missing perimeter makes every assertion below vacuously true.

    Without this, moving or renaming commands/ turns the gate green by emptying it —
    the failure mode is indistinguishable from a clean tree, which is precisely what
    the gate is for.
    """
    missing = [str(d) for d in SURFACE_DIRS if not d.is_dir()]
    assert not missing, f"surface dirs missing: {missing}"


def test_the_scan_finds_references_at_all():
    """The same falsifiability guard one level down.

    The regex is the instrument; if it stops matching — a fence style changes, the paths
    move — `_references()` returns {} and the gate below passes over any number of broken
    paths. Measured 2026-09-15: 23 distinct references across the perimeter.
    """
    assert len(_references()) >= 10, (
        "the script-reference scan found almost nothing — the pattern has stopped "
        "matching, not the corpus stopped referencing"
    )


def test_every_referenced_engine_script_exists():
    broken = {ref: sorted(where) for ref, where in _references().items()
              if not (REPO / ref).is_file()}
    assert not broken, (
        "surfaces name engine scripts that do not exist at the path given "
        f"(resolve from the repo root): {broken}"
    )


def test_a_line_marking_a_script_retired_is_not_read_as_a_claim(tmp_path, monkeypatch):
    """The exemption is load-bearing, not decorative.

    Without it, spec 121's retirement record in `commands/done.md` — which must name
    `engine/scripts/lifecycle/study_phase.py` to say that it is gone — fails this gate, and the
    only way to go green is to delete the record. That is the opposite of what the gate is for:
    it exists so surfaces stop naming scripts as if they ran, not so they stop remembering them.
    """
    surface = tmp_path / "commands"
    surface.mkdir()
    (surface / "a.md").write_text(
        "Run `engine/scripts/lifecycle/ghost.py` for this.\n"
        "`engine/scripts/lifecycle/gone.py` is **retired** — removed by spec 121.\n"
    )
    monkeypatch.setattr("tests.test_referenced_scripts_exist.SURFACE_DIRS", [surface])
    monkeypatch.setattr("tests.test_referenced_scripts_exist.REPO", tmp_path)
    refs = _references()
    assert "engine/scripts/lifecycle/ghost.py" in refs, (
        "the unmarked reference must still be collected, or the exemption has swallowed the gate"
    )
    assert "engine/scripts/lifecycle/gone.py" not in refs, (
        f"a line declaring the script retired was read as a claim that it exists — {refs}"
    )

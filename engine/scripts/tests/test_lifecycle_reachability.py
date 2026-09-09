"""test_lifecycle_reachability.py — a step that calls itself mandatory must be reachable.

A lifecycle command is reached in exactly one way: another command tells the agent to run it.
There is no scheduler, no daemon and no router — `commands/*.md` is the whole call graph, and
its edges are the `/conclave:<name>` mentions inside those files.

The defect this gate exists for was measured 2026-09-08 while deciding where spec 117's
checkpoint verb belongs (`ops/specs/117-session-ledger/spec.md` §6, forge-chro's item):

    commands/processing.md:20  > **MANDATORY** for every advisor session after /conclave:start

and no file in `commands/` names `/conclave:processing` except itself. `commands/start.md`
ends by naming `/conclave:done`. So the step has declared itself obligatory for every session
for months while nothing in the lifecycle could ever route an agent into it — and its single
external side effect (a project-board write, `processing.md:36`) reads `${PROJECT_ID}`, which
no file in CODE produces, against a board this instance does not have (`roster.yaml`
`board_number: null`). Nothing failed, because an unreachable obligation has no failure mode:
it is indistinguishable, from inside the session, from an obligation that was met.

This is `.claude/memory/a-cli-no-protocol-invokes-is-not-a-path.md` at the command layer, and
it is why the checkpoint verb was NOT given to `/conclave:processing`: a per-unit discipline
hung on a step with in-degree zero is a discipline that never runs.
"""

from __future__ import annotations

import pathlib
import re

import pytest

# tests/ -> scripts/ -> engine/ -> <code root>. Same derivation as test_retro_contract_gate.py.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
COMMANDS = REPO_ROOT / "commands"

# A command claims obligation in one place and one form: a blockquote directly under its H1.
# Body prose says "mandatory" about fields, args and sub-steps a dozen times; those are not
# claims about the step itself, and matching them would make this gate about word frequency.
_HEADLINE_CLAIM = re.compile(r"^>\s*\*\*MANDATORY\*\*", re.MULTILINE)
_INVOKES = re.compile(r"/conclave:([a-z][a-z-]*)")

# The session entry point is reached by the operator, not by another command, so it is the one
# step whose in-degree is legitimately zero. Pinned rather than derived: "which command starts
# a session" is a lifecycle fact, and deriving it from the graph would define the entry point
# as *whatever is unreachable* — which is precisely the defect this file detects.
ENTRY_POINTS = frozenset({"start"})

# The obligatory set is a lifecycle decision (forge-chro's charter), so it is pinned and any
# change to it must be made here, in the same commit, with a reason. Without this, the cheap
# way to pass the reachability gate is to delete the word MANDATORY from an orphan step, and
# the escape hatch quietly becomes the way to avoid the gate.
EXPECTED_MANDATORY = frozenset({"start", "done", "feedback", "handoff"})


def _command_names() -> list[str]:
    return sorted(p.stem for p in COMMANDS.glob("*.md"))


def _claims_mandatory() -> frozenset[str]:
    return frozenset(
        p.stem for p in COMMANDS.glob("*.md") if _HEADLINE_CLAIM.search(p.read_text())
    )


def _edges(text_by_command: dict[str, str]) -> dict[str, set[str]]:
    """command -> the commands it names, excluding self-reference.

    Self-reference is dropped because every command file opens with `# /conclave:<name>`;
    counting that edge would make every command reach itself and grade an empty tree connected.
    """
    return {
        caller: {c for c in _INVOKES.findall(text) if c in text_by_command and c != caller}
        for caller, text in text_by_command.items()
    }


def _reachable(text_by_command: dict[str, str], entries: frozenset[str]) -> set[str]:
    """The commands an agent can actually arrive at, walking out from the entry points.

    In-degree was the first version of this and it was wrong — proved by mutation, not by
    reading: deleting every mention of `/conclave:done` from `commands/start.md` left the gate
    green, because `handoff.md` and `retro.md` also name `done` and both are themselves reached
    only *through* `done`. A cycle has in-degree everywhere and reachability nowhere. What the
    lifecycle needs is the transitive closure from the step the operator actually types.
    """
    edges = _edges(text_by_command)
    seen = {e for e in entries if e in text_by_command}
    queue = list(seen)
    while queue:
        for callee in edges.get(queue.pop(), ()):
            if callee not in seen:
                seen.add(callee)
                queue.append(callee)
    return seen


def _texts() -> dict[str, str]:
    return {p.stem: p.read_text() for p in COMMANDS.glob("*.md")}


# ---------------------------------------------------------------------------
# Gate 1 — an obligatory step is named by some other step
# ---------------------------------------------------------------------------


def test_every_mandatory_command_is_reachable_from_the_entry_point():
    reachable = _reachable(_texts(), ENTRY_POINTS)
    orphans = sorted(_claims_mandatory() - reachable)
    assert not orphans, (
        f"commands that declare themselves MANDATORY and cannot be reached from "
        f"{sorted(ENTRY_POINTS)}: {orphans} — `commands/*.md` is the entire call graph, so a "
        "step no chain of mentions leads to is only ever run if the operator types it by hand, "
        "and an obligation nothing routes into cannot be observed to have been skipped"
    )


def test_reachability_gate_catches_an_orphan():
    """The gate's own falsifier: an orphan mandatory command in a synthetic tree."""
    texts = {
        "start": "# /conclave:start\n> **MANDATORY** for every advisor session.\nthen /conclave:done\n",
        "done": "# /conclave:done\n> **MANDATORY** at the end.\n",
        "ghost": "# /conclave:ghost\n> **MANDATORY** always.\nsee /conclave:start\n",
    }
    orphans = sorted(set(texts) - _reachable(texts, ENTRY_POINTS))
    assert orphans == ["ghost"], (
        "the synthetic orphan was not detected — `ghost` names `start`, which is an outgoing "
        f"edge and not an incoming one, and the scan reported {orphans}"
    )


def test_a_cycle_off_the_entry_point_is_not_reachability():
    """The mutation that killed the first version of this gate, pinned as a test.

    `a` and `b` name each other, so both have in-degree 1 and the in-degree formulation graded
    them reachable. Nothing leads to either from `start`. This is the live shape: `done`,
    `handoff` and `retro` all name each other, so severing `start`'s only edge to `done` left
    four commands with in-degree ≥ 1 and zero ways in.
    """
    texts = {
        "start": "# /conclave:start\n> **MANDATORY** always.\n",
        "a": "# /conclave:a\n> **MANDATORY** always.\ngo to /conclave:b\n",
        "b": "# /conclave:b\n> **MANDATORY** always.\nback to /conclave:a\n",
    }
    assert _reachable(texts, ENTRY_POINTS) == {"start"}


def test_self_reference_is_not_reachability():
    """A command's own H1 names itself; that must not count as an edge.

    Every command file opens with `# /conclave:<name>`, so counting self-mentions would grade
    the entire call graph reachable and this gate would pass on an empty tree.
    """
    texts = {"lonely": "# /conclave:lonely\n> **MANDATORY** always.\nrun /conclave:lonely again\n"}
    assert _edges(texts)["lonely"] == set()
    assert _reachable(texts, ENTRY_POINTS) == set()


# ---------------------------------------------------------------------------
# Gate 2 — the obligatory set itself
# ---------------------------------------------------------------------------


def test_the_mandatory_set_is_the_declared_one():
    claimed = _claims_mandatory()
    assert claimed == EXPECTED_MANDATORY, (
        f"commands claiming MANDATORY: {sorted(claimed)}; declared: "
        f"{sorted(EXPECTED_MANDATORY)}. Adding or removing an obligatory step is a lifecycle "
        "decision (spec 117 §6, forge-chro) — make it here too, so the change is a record "
        "rather than a word deleted from a blockquote"
    )


def test_entry_point_exists_and_is_a_real_command():
    names = set(_command_names())
    missing = sorted(ENTRY_POINTS - names)
    assert not missing, f"ENTRY_POINTS names no such command: {missing}"
    assert ENTRY_POINTS <= _claims_mandatory(), (
        "the entry point is exempted from the reachability gate, so it must itself be one of "
        "the obligatory steps — otherwise the exemption covers an optional command"
    )


def test_claim_detector_ignores_body_prose():
    """`mandatory` appears a dozen times in body text about fields and arguments.

    If the detector matched those, `commands/feedback.md`'s field table alone would enrol
    every command that documents a required field, and the obligatory set would become a
    word count.
    """
    assert not _HEADLINE_CLAIM.search("The `--reflexion` arg is **mandatory**.\n")
    assert not _HEADLINE_CLAIM.search("### Mandatory (always)\n")
    assert _HEADLINE_CLAIM.search("> **MANDATORY** for every advisor session.\n")


@pytest.mark.parametrize("name", ["start", "done", "feedback", "handoff"])
def test_the_spine_stays_connected(name: str):
    """Regression floor: whatever else changes, every obligatory step keeps a route in."""
    assert name in _reachable(_texts(), ENTRY_POINTS), f"/conclave:{name} became unreachable"

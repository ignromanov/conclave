"""`engine status` — the projection's terminal printer (GH#57).

The assertions worth having here are the ones about what the command may NOT say. A
partial projection is honest only while an unwired slot is visibly unwired; the moment
one renders as `0` it is indistinguishable from a measured zero, and the command has
become the failure mode it was built to retire.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from engine.cmd import status as status_cmd
from enginelib.status.model import Absent, Count, SectionResult
from enginelib.status.render_terminal import GLANCE_MAX_CONTENT_LINES, glance, glance_overflows


@pytest.fixture
def instance(tmp_path):
    """A minimal DATA tree: two open handoffs and a feedback index."""
    handoffs = tmp_path / "ops" / "handoffs"
    handoffs.mkdir(parents=True)
    recent = datetime.now(UTC) - timedelta(days=1)
    for i, st in enumerate(["open", "done"]):
        (handoffs / f"h{i}.md").write_text(f"---\nstatus: {st}\n---\nbody\n", encoding="utf-8")
    (handoffs / "h2.md").write_text("---\nstatus: open\n---\nbody\n", encoding="utf-8")

    idx = tmp_path / "ops" / "feedback" / "_index"
    idx.mkdir(parents=True)
    idx.joinpath("index.jsonl").write_text(
        "\n".join(json.dumps({"status": s}) for s in ["open", "resolved", "open"]) + "\n",
        encoding="utf-8",
    )
    assert recent  # keeps the fixture's intent explicit
    return tmp_path


def test_handoffs_are_counted_instance_wide_and_terminal_ones_excluded(instance):
    section = status_cmd._handoffs_section(instance)
    assert isinstance(section.measurement, Count)
    # h0 open, h1 done (terminal, excluded), h2 open
    assert section.measurement.value == 2


def test_feedback_carries_its_denominator_and_its_proof(instance):
    section = status_cmd._feedback_section(instance)
    m = section.measurement
    assert isinstance(m, Count)
    assert (m.value, m.of) == (1, 3)
    assert "index.jsonl" in m.proof


def test_a_missing_source_is_absent_with_a_reason_never_zero(tmp_path):
    """Rule 6 at the surface: the two states must not render alike."""
    for section in (status_cmd._handoffs_section(tmp_path), status_cmd._feedback_section(tmp_path)):
        assert isinstance(section.measurement, Absent), f"{section.name} rendered a number"
        assert section.measurement.reason.strip()
        assert section.verdict == "unknown"
        rendered = glance("engine", "🦉", "состояние", "09.09", [section])
        assert " 0 " not in rendered, f"{section.name} rendered a zero for a missing source"


def test_every_unwired_slot_states_a_reason():
    """An unwired slot with an empty reason is rule 6's forbidden bare em dash."""
    assert status_cmd._NOT_YET_WIRED, "the map may empty only when every slot is wired"
    for name, reason in status_cmd._NOT_YET_WIRED.items():
        assert reason.strip(), f"{name} declares no reason"
        assert Absent(reason=reason)


def test_glance_budget_is_reported_not_silently_trimmed():
    """Twelve is a cap on what the block may CARRY, not a licence to drop rows."""
    many = [
        SectionResult(f"s{i}", Count(1, "x", "p"))
        for i in range(GLANCE_MAX_CONTENT_LINES + 1)
    ]
    assert glance_overflows(many)
    block = glance("engine", "🦉", "состояние", "09.09", many)
    assert all(f"**s{i}**" in block for i in range(len(many))), "a row was dropped to fit"


def test_verb_is_registered_under_status():
    """The mention from forge-chro (2026-09-09) promises a gate asserting every
    `engine …` verb a contract names resolves in the CLI. This is that verb's half."""
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="noun")
    status_cmd.register(sub)
    args = parser.parse_args(["status", "--glance"])
    assert args.func is status_cmd._status
    assert args.glance is True

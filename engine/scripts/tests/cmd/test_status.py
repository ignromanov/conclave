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


# ---------------------------------------------------------------------------
# The gh mosaic: instance scope as an iteration over the roster (plan 057 T7)
# ---------------------------------------------------------------------------


def _write_cache(instance, advisor, captured_at, items):
    """One gh-cache snapshot in the shape gh-fetch.sh writes."""
    cache_dir = instance / "agent-memory" / "gh-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    body = (
        f"---\ntype: gh-snapshot\nadvisor: {advisor}\n"
        f'captured_at: "{captured_at}"\n---\n\n'
        f"# GH Snapshot — {advisor}\n\n```json\n{json.dumps(items)}\n```\n"
    )
    (cache_dir / f"{advisor}.md").write_text(body, encoding="utf-8")


def _issue(number, *labels, repo="conclave", updated="2026-09-09T20:00:00Z"):
    return {
        "number": number,
        "title": f"issue {number}",
        "labels": [{"name": lbl} for lbl in labels],
        "repository": {"name": repo},
        "updatedAt": updated,
    }


@pytest.fixture
def roster(tmp_path, monkeypatch):
    """A DATA tree whose roster is three domain advisors plus the META one.

    CLAUDE_PROJECT_DIR is popped explicitly rather than trusted to the repo-root
    conftest: `_agents_dir_for` consults it first, so an ambient export would point
    the roster walk at the operator's live tree and the assertions below would pass
    or fail on data this test never wrote.
    """
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    for name in ("sage-cto", "keel-coo", "helm-ceo", "forge-chro"):
        (agents / f"{name}.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    (agents / "exec-atlas-dev.md").write_text("---\nname: exec-atlas-dev\n---\n", encoding="utf-8")
    return tmp_path


def _fresh(minutes_ago=1):
    return (datetime.now(UTC) - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_the_meta_advisors_queue_is_counted_not_excluded(roster):
    """`known_advisors` drops forge-chro as META; measured 2026-09-09 it held 73 of
    the instance's 137 cached issues. A projection on that resolver prints a number
    that is 53 % short and calls itself instance-wide — the §2 defect one layer up."""
    _write_cache(roster, "forge-chro", _fresh(), [_issue(1, "p2"), _issue(2, "p2")])
    for advisor in ("sage-cto", "keel-coo", "helm-ceo"):
        _write_cache(roster, advisor, _fresh(), [])

    queue, _p0 = status_cmd._gh_sections(roster)
    assert isinstance(queue.measurement, Count)
    assert queue.measurement.value == 2, "the META advisor's queue was dropped"
    assert "forge-chro" in queue.measurement.proof


def test_an_issue_in_two_caches_is_counted_once(roster):
    shared = _issue(57, "p1")
    _write_cache(roster, "sage-cto", _fresh(), [shared, _issue(58, "p2")])
    _write_cache(roster, "keel-coo", _fresh(), [shared])
    for advisor in ("helm-ceo", "forge-chro"):
        _write_cache(roster, advisor, _fresh(), [])

    queue, _ = status_cmd._gh_sections(roster)
    assert queue.measurement.value == 2


def test_two_repos_sharing_an_issue_number_are_two_issues(roster):
    """This instance runs two repos, so `#57` is not an identity — `conclave#57` and
    `conclave-ai#57` are different issues and must not dedupe into one.

    Asserted through the real `issue_identity`, not by handing pre-built strings to
    the reducer: a mutation that dropped the repo prefix left every unit test in
    test_status_mosaic green, because those tests supply identities rather than
    derive them. A property has to be asserted where it is PRODUCED.
    """
    _write_cache(roster, "sage-cto", _fresh(), [_issue(57, "p1", repo="conclave")])
    _write_cache(roster, "keel-coo", _fresh(), [_issue(57, "p1", repo="conclave-ai")])
    for advisor in ("helm-ceo", "forge-chro"):
        _write_cache(roster, advisor, _fresh(), [])

    queue, _ = status_cmd._gh_sections(roster)
    assert queue.measurement.value == 2, "two repos' issue #57 collapsed into one"


def test_a_missing_snapshot_makes_the_count_a_floor_and_the_verdict_unknown(roster):
    """Skipping an advisor whose cache was never fetched turns a floor into a total.
    Rule 2 puts the resulting uncertainty above any known-bad reading."""
    _write_cache(roster, "sage-cto", _fresh(), [_issue(1, "p1")])
    _write_cache(roster, "keel-coo", _fresh(), [])
    _write_cache(roster, "helm-ceo", _fresh(), [])
    # forge-chro: no cache file at all.

    queue, _ = status_cmd._gh_sections(roster)
    assert queue.measurement.value == 1
    assert "пол" in queue.measurement.noun, "an incomplete union presented itself as a total"
    assert "forge-chro" in queue.measurement.proof
    assert queue.verdict == "unknown"


def test_an_empty_cache_is_a_measured_zero_not_an_absence(roster):
    """The pair the mosaic exists to separate, asserted at the surface."""
    for advisor in ("sage-cto", "keel-coo", "helm-ceo", "forge-chro"):
        _write_cache(roster, advisor, _fresh(), [])

    queue, p0 = status_cmd._gh_sections(roster)
    for section in (queue, p0):
        assert isinstance(section.measurement, Count), f"{section.name} claimed absence"
        assert section.measurement.value == 0
        assert not section.measurement.proof.count("без снимка")


def test_no_snapshot_anywhere_is_absent_and_never_zero(roster):
    """No cache for any advisor: rule 6 forbids this rendering as 0."""
    queue, p0 = status_cmd._gh_sections(roster)
    for section in (queue, p0):
        assert isinstance(section.measurement, Absent), f"{section.name} rendered a number"
        assert section.measurement.reason.strip()
        assert section.verdict == "unknown"
        assert " 0 " not in glance("engine", "🦉", "состояние", "09.09", [section])


def test_the_oldest_snapshot_degrades_the_whole_union(roster):
    """Four fresh caches must not vouch for a fifth that is hours old — the measured
    case: GH#250 was created after forge-chro's snapshot and appears in none of them,
    so the union read 137 while the repo held 138."""
    for advisor in ("sage-cto", "keel-coo", "helm-ceo"):
        _write_cache(roster, advisor, _fresh(), [_issue(1, "p2")])
    old = (datetime.now(UTC) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_cache(roster, "forge-chro", old, [_issue(2, "p2")])

    queue, _ = status_cmd._gh_sections(roster)
    assert queue.verdict == "stale_error", "a stale member was hidden by its fresh siblings"
    assert "старейший" in queue.measurement.proof


def test_p0_is_instance_wide_and_sees_another_advisors_blocker(roster):
    """The executed defect of plan 057 §2: the section is titled "global p0 blockers"
    and reads one advisor's cache, so a p0 on forge-chro renders to sage-cto as none.
    Instance scope means the blocker is visible regardless of whose queue holds it."""
    _write_cache(roster, "forge-chro", _fresh(), [_issue(901, "p0")])
    for advisor in ("sage-cto", "keel-coo", "helm-ceo"):
        _write_cache(roster, advisor, _fresh(), [_issue(10, "p2")])

    _queue, p0 = status_cmd._gh_sections(roster)
    assert isinstance(p0.measurement, Count)
    assert p0.measurement.value == 1, "a p0 on another advisor was invisible"


def test_p0_matches_the_label_not_the_title(roster):
    """`build()` keeps the bash port's substring predicate; this seam does not, because
    a title reading "drop the p0 gate" is not a p0 blocker."""
    _write_cache(roster, "sage-cto", _fresh(), [_issue(1, "p2")])
    cache = roster / "agent-memory" / "gh-cache" / "sage-cto.md"
    cache.write_text(cache.read_text().replace('"issue 1"', '"retire the p0 gate"'), encoding="utf-8")
    for advisor in ("keel-coo", "helm-ceo", "forge-chro"):
        _write_cache(roster, advisor, _fresh(), [])

    _queue, p0 = status_cmd._gh_sections(roster)
    assert p0.measurement.value == 0, "a title containing 'p0' was counted as a blocker"


def test_the_wired_queue_slot_left_the_unwired_map():
    """A slot cannot be both wired and declared unwired; the pair would drift."""
    assert "очередь" not in status_cmd._NOT_YET_WIRED
    assert "p0" not in status_cmd._NOT_YET_WIRED

"""the close gate: a completion is re-checked before its count is published (spec 117 T8/R12).

The requirement has two halves and the second is the one that matters. A gate that refuses is
easy; a gate whose override *silences* is the warning R12 was written to replace — 78 % of agent
failures are silent wrong-state with no tool error, so a signal that goes to scrollback and dies
is the wrong instrument. The override here writes what it overrode into the record, where it
outlives the session and can be counted: the kill criterion for this whole mechanism reads off
those very lines.

The third thing under test is the one that decides whether the gate is usable at all: a check that
could not be RUN is not a unit that lost its artefact. A gh snapshot goes stale in 900 seconds and
every session outlives that, so a gate that read staleness as absence would refuse every close
carrying `issue:` evidence — a refusal keyed on the evidence class rather than on anything that
happened.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from enginelib import paths
from enginelib.checkpoint import evidence, gate, record, store
from enginelib.filing import CloseSessionOpts, close_session

_DATE = "2026-04-22"
_ADVISOR = "nexus-ceo"
_TOKEN = "eeeeeeee-5555"


@pytest.fixture()
def body(tmp_path: Path) -> Path:
    path = tmp_path / "session-body.md"
    path.write_text("What the agent says it did.\n", encoding="utf-8")
    return path


def _opts(body: Path, **kw) -> CloseSessionOpts:
    return CloseSessionOpts(
        advisor=_ADVISOR, slug="gated", date=_DATE, body_file=str(body),
        goal="publish a count", session_id=_TOKEN, **kw,
    )


def _record_path() -> Path:
    return paths.sessions_dir() / f"{_DATE}-{_ADVISOR}-gated.md"


def _vanishing_artefact() -> str:
    """A `file:` ref that resolved when the line was written and does not resolve now.

    Written and then removed rather than never created: the point of R12 is a unit whose evidence
    *was* good — the verb refuses anything else at append time — and stopped being so while the
    session ran. A ref that never resolved would test a state the record cannot reach.
    """
    artefact = paths.repo_root() / "vanished.md"
    artefact.write_text("it was here\n", encoding="utf-8")
    ref = "file:vanished.md"
    artefact.unlink()
    return ref


def test_a_completion_whose_evidence_is_gone_refuses_the_close(ai_root, body):
    """Mutation: run the gate after the write, or drop the raise and only warn.

    Order is half the assertion. The refusal has to leave nothing behind — a session record on
    disk carrying a count the gate rejected is worse than no gate, because the number is now
    published and the objection is only in a terminal nobody kept.
    """
    path = store.ensure(_ADVISOR, _TOKEN)
    store.append(path, record.render(record.KIND_DONE, "the unit that lost its artefact",
                                     evidence=(_vanishing_artefact(),)))

    with pytest.raises(ValueError) as caught:
        close_session(_opts(body))

    assert "the unit that lost its artefact" in str(caught.value), str(caught.value)
    assert "vanished.md" in str(caught.value), "the refusal did not name the gap"
    assert not _record_path().exists(), "the refused close still published a session record"
    assert path.is_file(), "the refused close consumed the checkpoint it refused to publish"


def test_the_override_closes_and_writes_down_what_it_overrode(ai_root, body):
    """**The load-bearing test.** Mutation: make `force` skip the gate entirely.

    That mutation passes every other test in this file — the close succeeds, the record is
    written, the checkpoint is removed — and it reproduces exactly the instrument R12 replaced.
    An override that leaves no trace is a warning with extra steps, and the kill criterion for
    this gate is computed from the traces, so silencing the override also destroys the only
    evidence that could ever retire the gate.
    """
    path = store.ensure(_ADVISOR, _TOKEN)
    store.append(path, record.render(record.KIND_DONE, "the unit that lost its artefact",
                                     evidence=(_vanishing_artefact(),)))

    close_session(_opts(body, force=True))

    text = _record_path().read_text(encoding="utf-8")
    assert "Override" in text
    assert "the unit that lost its artefact" in text
    assert "vanished.md" in text, "the override recorded that it overrode, but not what"
    assert not path.exists(), "a forced close is still a close; the checkpoint should be folded"


def test_a_clean_record_closes_with_no_override_block(ai_root, body):
    """The negative half, so the two tests above cannot be satisfied by refusing everything.

    A file that only proves refusals and overrides passes with the gate replaced by
    `raise ValueError` unconditionally.
    """
    artefact = paths.repo_root() / "kept.md"
    artefact.write_text("still here\n", encoding="utf-8")
    path = store.ensure(_ADVISOR, _TOKEN)
    store.append(path, record.render(record.KIND_DONE, "the unit that kept its artefact",
                                     evidence=("file:kept.md",)))

    close_session(_opts(body))

    text = _record_path().read_text(encoding="utf-8")
    assert "requested 1 · shipped 1 · lost 0" in text
    assert "Override" not in text
    assert not path.exists()


def test_a_declared_unit_is_never_gated_even_when_it_cites_something_gone(ai_root, body):
    """Mutation: drop the `kind != KIND_DONE` guard and gate every entry.

    **The first version of this test could not catch that mutation and said it could.** It seeded
    an intent with no evidence — which is all the verb will ever write, since `--intent` refuses
    `--evidence` — so gating intents resolved an empty ref list and changed nothing. The battery
    is what showed it: the mutation reddened no test at all.

    The guard is load-bearing on the file, not on the verb. `record.render` attaches evidence to
    either kind; only the CLI refuses it, and a record is a file that outlives the process that
    wrote it. An intent that names an artefact is still a *declaration* — R2's own word — and
    refusing a close over one would fire the gate on units nobody ever claimed to have finished.

    The second half is the ordinary case: a unit declared and not finished is how sessions end,
    R5 already reports it as `lost`, and gating it would teach the operator to pass `--force` by
    reflex — which converts the mechanism into the silent override it was designed not to be.
    """
    path = store.ensure(_ADVISOR, _TOKEN)
    store.append(path, record.render(record.KIND_INTENT, "the unit that cites a vanished thing",
                                     evidence=(_vanishing_artefact(),)))
    store.append(path, record.render(record.KIND_INTENT, "the unit still in flight"))

    close_session(_opts(body))

    text = _record_path().read_text(encoding="utf-8")
    assert "requested 2 · shipped 0 · lost 2" in text
    assert "Override" not in text


# --- what the gate must NOT call a disagreement -------------------------------------------

@pytest.fixture()
def roots(tmp_path) -> evidence.Roots:
    project = tmp_path / "project"
    data = project / ".conclave"
    data.mkdir(parents=True)
    gh_cache = tmp_path / "gh-cache"
    gh_cache.mkdir()
    return evidence.Roots(code=tmp_path / "code", data=data, project=project,
                          gh_cache=gh_cache, index=tmp_path / "index.jsonl")


def test_a_check_that_could_not_be_run_is_not_a_unit_that_lost_its_work(roots):
    """Mutation: treat every `not ok` as a disagreement.

    This is the difference between a gate and a nuisance. Neither ref below observed anything:
    the gh cache holds no snapshot naming the issue, and the feedback index does not exist. A
    session routinely closes in both states — a snapshot is stale after 900 seconds and every
    session outlives that — so a gate that read them as vanished work would refuse on the
    evidence *class*, and the operator would pass `--force` every time.
    """
    entries = [record.Entry(kind=record.KIND_DONE, ts="t", text="closed the issue",
                            evidence=("issue:7",)),
               record.Entry(kind=record.KIND_DONE, ts="t", text="the predicate passed",
                            evidence=("predicate:fb-1/it-1",))]

    checks = evidence.resolve_all(("issue:7", "predicate:fb-1/it-1"), roots)
    assert not any(c.ok for c in checks), "the fixture accidentally made these resolve"
    assert all(c.unknown for c in checks), [(c.ref, c.reason) for c in checks]

    assert gate.disagreements(entries, roots) == ()


def test_one_unit_with_two_bad_refs_reports_both(roots):
    """Mutation: `break` after the first failing ref of a unit.

    The gap an operator has to judge is per-artefact: a missing file and a rebased-away commit
    are different questions with different answers. Collapsing them to one line makes the reader
    open the record to find out which — and the override line, which is what the kill criterion
    counts, would under-report the disagreement it recorded.
    """
    entry = record.Entry(kind=record.KIND_DONE, ts="t", text="shipped it",
                         evidence=("file:gone.md", "commit:0123456"))

    found = gate.disagreements([entry], roots)

    assert len(found) == 2, found
    assert {d.ref for d in found} == {"file:gone.md", "commit:0123456"}
    assert all(d.unit == "shipped it" for d in found)

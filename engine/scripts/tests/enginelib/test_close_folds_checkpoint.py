"""close folds the in-flight checkpoint, in the order that survives a crash (spec 117 T6/D3).

The design doc says close "moves" the checkpoint into `sessions/`. D3 replaces that word, and
the replacement is the only reason this file exists. Close **composes** a session record from
the checkpoint's content: the record is written atomically first, and the checkpoint is
unlinked only afterwards.

The order is the whole requirement. Write-then-unlink, interrupted, leaves both files — the
session record on disk and the checkpoint still beside it, which is a duplicate and therefore
recoverable and loud. Unlink-then-write, interrupted, leaves neither, and what it destroys is
the only record of what the session actually did. Both orders pass a happy-path test, which is
why the load-bearing test here is the one that makes the write fail.
"""
from __future__ import annotations

import os
from datetime import date as _date_cls
from pathlib import Path

import pytest

from enginelib import filing, paths
from enginelib.checkpoint import record, store
from enginelib.filing import CloseSessionOpts, close_session

# A note left where the next reader will need it. These tests raise
# `EngineRootMismatchWarning`, ~19 of them: `ai_root` points CONCLAVE_ENGINE_ROOT at its tmp
# tree on purpose — that is how the copied templates get read instead of this checkout's —
# and `enginelib.paths` warns about exactly that disagreement. This file is the first to run
# `close_session` IN-PROCESS under that fixture, so it is the first to surface it at all.
#
# They are NOT filtered here, and the first version of this file was wrong to try. The
# category's own docstring says the deliberate population "can silence exactly this and
# nothing else. See the repo-root conftest.py." No such filter exists there or anywhere in
# the tree (measured: the name appears in paths.py and in one unrelated comment) — the
# mechanism is documented and unbuilt. Declaring `pytestmark = filterwarnings(...)` locally
# looked like the fix and instead broke COLLECTION of this file under `-p no:warnings`,
# which disables the plugin the mark needs. True warnings are cheaper than a file that
# cannot be collected; the missing mechanism belongs in the P-list, not in a local patch.

_DATE = "2026-04-22"
_ADVISOR = "nexus-ceo"
_TOKEN = "dddddddd-4444"


@pytest.fixture()
def body(tmp_path: Path) -> Path:
    path = tmp_path / "session-body.md"
    path.write_text("What the agent says it did.\n", encoding="utf-8")
    return path


def _opts(body: Path, **kw) -> CloseSessionOpts:
    return CloseSessionOpts(
        advisor=_ADVISOR, slug="folds", date=_DATE, body_file=str(body),
        goal="close the loop", session_id=_TOKEN, **kw,
    )


def _seed_checkpoint(*entries: tuple[str, str, tuple[str, ...]]) -> Path:
    path = store.ensure(_ADVISOR, _TOKEN)
    for kind, text, evidence in entries:
        store.append(path, record.render(kind, text, evidence=evidence))
    return path


def _record_text() -> str:
    return (paths.sessions_dir() / f"{_DATE}-{_ADVISOR}-folds.md").read_text(encoding="utf-8")


def test_the_checkpoint_is_folded_and_then_removed(ai_root, body):
    """The happy path — and it is the test that proves nothing about the ordering."""
    checkpoint = _seed_checkpoint(
        (record.KIND_INTENT, "T6 — the fold", ()),
        (record.KIND_DONE, "T6 — the fold", ("commit:3e2f42f",)),
        (record.KIND_INTENT, "T7 — the glob", ()),
    )
    close_session(_opts(body))

    text = _record_text()
    assert "requested 2 · shipped 1 · lost 1" in text
    assert "T6 — the fold" in text and "commit:3e2f42f" in text
    assert "T7 — the glob" in text
    assert not checkpoint.exists(), "the checkpoint outlived a successful close"


def test_a_failed_record_write_leaves_the_checkpoint_in_place(ai_root, body, monkeypatch):
    """**The D3 instrument.** Mutate the order to unlink-then-write and this goes red.

    Nothing else in this file can tell the two orders apart, because on the path where
    nothing fails they produce identical results.
    """
    checkpoint = _seed_checkpoint((record.KIND_INTENT, "the work that must not vanish", ()))

    def _explode(*a, **kw):
        raise OSError("disk full, as it happens at the worst moment")

    monkeypatch.setattr(filing, "snapshot_write", _explode)

    with pytest.raises(OSError):
        close_session(_opts(body))

    assert checkpoint.is_file(), (
        "the close destroyed the in-flight record before the session record was safe — "
        "this is the unlink-then-write order, and an interrupted close now loses the "
        "only evidence of what the session did"
    )
    assert "the work that must not vanish" in checkpoint.read_text(encoding="utf-8")


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores the mode bits this test relies on")
def test_an_unremovable_checkpoint_does_not_fail_the_close(ai_root, body):
    """The other half of the order: failing to unlink is not failing to close.

    Once the session record is written the close has succeeded. A checkpoint that cannot be
    removed is a duplicate — the one failure mode this design deliberately prefers.

    The directory is made read-only rather than `Path.unlink` monkeypatched: patching the
    method globally also breaks `snapshot_write`'s own tmp-file handling, so the first
    version of this test failed for a reason that had nothing to do with what it asserts.
    """
    checkpoint = _seed_checkpoint((record.KIND_DONE, "shipped", ("commit:3e2f42f",)))
    checkpoint.parent.chmod(0o500)
    try:
        close_session(_opts(body))
    finally:
        checkpoint.parent.chmod(0o755)

    assert "shipped" in _record_text()
    assert checkpoint.is_file(), "the fixture did not actually prevent the unlink"


def test_a_session_with_no_checkpoint_closes_the_way_it_always_did(ai_root, body):
    """`/conclave:done` is reachable without session_init having run.

    The adjacent Now drain already tolerates removing zero rows for exactly this reason, and
    a fold that raised here would make the ledger able to refuse a close — which is the one
    thing 117 is not allowed to do.
    """
    close_session(_opts(body))
    assert "What the agent says it did." in _record_text()


def test_lines_that_did_not_parse_are_carried_over_rather_than_dropped(ai_root, body):
    """Nothing vanishes without the record saying so — applied to the shape a killed
    process actually leaves.

    A torn tail is the expected residue of process death, and it is residue from precisely
    the sessions worth auditing. Dropping it would make the tally quietly wrong exactly
    there — so the fold reports the count and reproduces the bytes.
    """
    checkpoint = _seed_checkpoint((record.KIND_DONE, "complete", ("commit:3e2f42f",)))
    with checkpoint.open("a", encoding="utf-8") as fh:
        fh.write("- [2026-04-22T16:01-0300] done: torn in the mi")

    close_session(_opts(body))

    text = _record_text()
    assert "1 line(s) did not parse" in text
    assert "torn in the mi" in text
    assert "requested 1 · shipped 1 · lost 0" in text, (
        "the torn line was counted as a unit — it is unparseable, not a unit"
    )


def test_the_event_time_survives_the_fold_that_deletes_its_source(ai_root, body):
    """Mutation: drop `at=e.at` from the re-render in `_fold_checkpoint` (T9 producer).

    The fold does not copy lines, it re-renders parsed ones — and step 14b unlinks the
    checkpoint the moment the render lands. So the folded copy is not one of two copies, it is
    the last one, and a field the re-render forgets is not stale afterwards: it is gone, along
    with the only file that still held it. The mutation is invisible to every other test here
    because the tally, the evidence and the text all survive it.
    """
    path = store.ensure(_ADVISOR, _TOKEN)
    store.append(path, record.render(
        record.KIND_DONE, "T9 — the producer", evidence=("commit:3e2f42f",),
        at="2026-04-21T09:08:07+00:00",
    ))

    close_session(_opts(body))

    text = _record_text()
    assert "2026-04-21T09:08:07+00:00" in text, (
        "the folded record lost the event time, and the checkpoint that held it is deleted:\n"
        + text
    )
    assert not path.exists()


def test_a_session_that_outlives_a_midnight_folds_both_of_its_records(ai_root, body):
    """Mutation: look the record up with `record_path(advisor, session_id)` (today's name).

    A session is identified by its **token**; the date in a record's filename says where it was
    opened, and one that crosses a midnight opens a second file under the same token. The
    wall-clock lookup then finds only the current day's, and loses the earlier one twice over:
    its units never reach the tally, and the file left behind is exactly what T7's resume scan
    reads as "a previous session never closed". Found by dogfooding — this instance produced the
    two-file case against itself before any test did.
    """
    first = store.ensure(_ADVISOR, _TOKEN, today="2026-04-21")
    store.append(first, record.render(record.KIND_INTENT, "the unit from before midnight"))
    second = store.ensure(_ADVISOR, _TOKEN, today=_date_cls.today().isoformat())
    store.append(second, record.render(record.KIND_INTENT, "the unit from after it"))

    close_session(_opts(body))

    text = _record_text()
    assert "requested 2 · shipped 0 · lost 2" in text, text
    assert "the unit from before midnight" in text
    assert "the unit from after it" in text
    assert not first.exists(), "the earlier record survived the close that folded it"
    assert not second.exists()


def test_the_fold_finds_the_record_by_token_and_not_by_the_date_at_close(ai_root, body):
    """Mutation: the same wall-clock lookup, seen from its other side.

    The test above needs a record that *is* today's to show the partial loss. This one has none:
    a session opened on another day and closed now folds nothing at all under the old lookup —
    no tally, no units, and the record still on disk — because the name it spells matches no
    file. The two mutations are the same line; the harms are different enough to name apart.
    """
    only = store.ensure(_ADVISOR, _TOKEN, today="2026-04-20")
    store.append(only, record.render(record.KIND_DONE, "the unit from another day",
                                     evidence=("commit:3e2f42f",)))

    close_session(_opts(body))

    text = _record_text()
    assert "requested 1 · shipped 1 · lost 0" in text, text
    assert "the unit from another day" in text
    assert not only.exists()

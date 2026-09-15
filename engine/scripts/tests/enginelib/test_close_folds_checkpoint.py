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
from pathlib import Path

import pytest

from enginelib import filing, paths
from enginelib.checkpoint import record, store
from enginelib.filing import CloseSessionOpts, close_session

# `ai_root` points CONCLAVE_ENGINE_ROOT at its tmp tree on purpose — that is how the copied
# templates and advisor stubs get read instead of this checkout's — and `enginelib.paths`
# warns about exactly that disagreement. This file is the first to run `close_session`
# IN-PROCESS under that fixture, so it is the first to surface the warning at all; the
# subprocess-driven close tests never could.
#
# `EngineRootMismatchWarning`'s own docstring says the deliberate population "can silence
# exactly this and nothing else. See the repo-root conftest.py." No such filter exists there,
# or anywhere else in the tree (measured 2026-09-15: the category name appears in paths.py and
# in one unrelated comment). The mechanism is documented and unbuilt, so this declares it for
# the one file that needs it rather than inventing a repo-wide policy that would change how 33
# other test files report.
pytestmark = pytest.mark.filterwarnings(
    "ignore::enginelib.paths.EngineRootMismatchWarning"
)

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

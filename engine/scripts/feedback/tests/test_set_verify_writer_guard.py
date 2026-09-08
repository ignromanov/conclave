"""test_set_verify_writer_guard.py — #161: the reachability guard moves into the writer.

`cmd_set_verify` is the sanctioned write path for attaching a `verify:` predicate to an
accepted item. Until now the admission test (refuse a predicate whose verdict is `pass`
or `broken`) lived one level up, in `feedback_verify.py`'s `--set-verify` CLI branch —
the writer only validated shape. That guard held only because `cmd_set_verify` had
exactly one caller; it is a one-caller-deep property, not an invariant. These tests call
`cmd_set_verify` DIRECTLY, bypassing the CLI branch entirely, to prove the guard now
lives in the writer itself.
"""
from __future__ import annotations

from pathlib import Path

from feedback_triage import cmd_set_verify


def _accepted_no_verify_meta() -> dict:
    return {"feedback_id": "fb-wg-aaaaaa", "agent": "sage-cto", "agent_type": "advisor",
            "session_ref": "s1", "skill_version": "sha256:aabbcc",
            "created": "2026-07-10T00:00:00Z", "updated_at": "2026-07-10T00:00:00Z",
            "_draft": False, "summary": "t", "below_threshold_count": 0,
            "items": [{"id": "i1", "category": "script-defect", "layer": "skill",
                       "location": {"file": "foo.py"}, "observation": "o",
                       "suggested_fix": "x", "severity": "high", "frequency": "occasional",
                       "evidence": "tc:1", "status": "accepted"}]}


def _layout(tmp_path: Path, target_text: str | None = "still has the BUG\n"):
    """Checkout layout mirroring test_verify.py's _setverify_layout: DATA root under
    .conclave, predicate target a sibling at the checkout (project) root."""
    from briefing.frontmatter_io import write
    data_root = tmp_path / ".conclave"
    if target_text is not None:
        (tmp_path / "foo.py").write_text(target_text)
    d = data_root / "ops" / "feedback" / "2026-07-10"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "sage-writerguard.md"
    write(path, _accepted_no_verify_meta(), "")
    return data_root, path


def test_writer_refuses_a_passing_predicate_when_called_directly(tmp_path):
    """A predicate that already passes must be refused by cmd_set_verify itself, called
    directly with no CLI branch in the path."""
    data_root, path = _layout(tmp_path, "the fix already landed\n")
    before = path.read_bytes()
    pred = {"kind": "grep-absent", "root": "project", "file": "foo.py",
            "pattern": "BUG", "path": None}
    rc = cmd_set_verify(data_root, "fb-wg-aaaaaa", "i1", pred,
                        project_root_path=tmp_path)
    assert rc == 1
    assert path.read_bytes() == before, "a refused predicate must not be written"


def test_writer_refuses_a_broken_predicate_when_called_directly(tmp_path):
    """A predicate whose target is unreadable (born broken) must also be refused."""
    data_root, path = _layout(tmp_path, target_text=None)
    before = path.read_bytes()
    pred = {"kind": "grep-absent", "root": "project", "file": "foo.py",
            "pattern": "BUG", "path": None}
    rc = cmd_set_verify(data_root, "fb-wg-aaaaaa", "i1", pred,
                        project_root_path=tmp_path)
    assert rc == 1
    assert path.read_bytes() == before, "a refused predicate must not be written"


def test_writer_attaches_a_failing_predicate(tmp_path):
    """The healthy path: a predicate that currently fails is attached normally."""
    data_root, path = _layout(tmp_path, "still has the BUG\n")
    pred = {"kind": "grep-absent", "root": "project", "file": "foo.py",
            "pattern": "BUG", "path": None}
    rc = cmd_set_verify(data_root, "fb-wg-aaaaaa", "i1", pred,
                        project_root_path=tmp_path)
    assert rc == 0

    from briefing.frontmatter_io import read_commented
    meta2, _ = read_commented(path)
    item = next(i for i in meta2["items"] if i["id"] == "i1")
    assert item["verify"]["pattern"] == "BUG"


def test_force_bypasses_the_writer_guard(tmp_path):
    """--force's semantics live in the writer now too: force=True attaches an
    already-passing predicate instead of refusing it."""
    data_root, path = _layout(tmp_path, "the fix already landed\n")
    pred = {"kind": "grep-absent", "root": "project", "file": "foo.py",
            "pattern": "BUG", "path": None}
    rc = cmd_set_verify(data_root, "fb-wg-aaaaaa", "i1", pred,
                        force=True, project_root_path=tmp_path)
    assert rc == 0

    from briefing.frontmatter_io import read_commented
    item = next(i for i in read_commented(path)[0]["items"] if i["id"] == "i1")
    assert item["verify"]["pattern"] == "BUG"

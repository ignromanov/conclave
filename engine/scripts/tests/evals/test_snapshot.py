"""The snapshot walk must not descend into the directories it claims to skip.

`take()` filtered `_SKIP_DIRS` out of `Path.rglob("*")`'s results, which is not the same as not
walking them: rglob descended into `.git/` first and discarded the paths afterwards. On CI that
raced git packing objects and the walk itself raised
`FileNotFoundError: .../.git/objects/01` — the per-file `except OSError` in `take()` is inside the
loop body and never runs when the generator is what fails.

That fault is not directly reproducible on every interpreter, and pinning it to the one where it
appeared would make this file dead weight everywhere else: it failed on **py3.11 only**, because
3.13 rewrote pathlib's globbing onto `glob._Globber`, which binds `scandir = staticmethod(os.scandir)`
at class-definition time and swallows OSError while walking. So neither the raise nor an
`os.scandir` monkeypatch reaches rglob on 3.13.

Absence of `.git` files from the RESULT cannot detect the bug either — that was already true while
it was live. What separates the two implementations on every version is where they look: the old
one had to `is_file()` each `.git` entry in order to discard it, the pruning one never sees them.
"""
from __future__ import annotations

import os
import pathlib

from evals.snapshot import take


def test_the_walk_never_touches_an_entry_inside_a_skipped_dir(tmp_path, monkeypatch):
    """Asserts the pruning itself, not its visible consequence.

    Post-filtering is only possible by inspecting the entry first, so a single `is_file()` call on
    anything under `.git/` proves the walk went in there.
    """
    (tmp_path / "work.md").write_text("real content\n", encoding="utf-8")
    objects = tmp_path / ".git" / "objects" / "01"
    objects.mkdir(parents=True)
    (objects / "deadbeef").write_bytes(b"object")

    inspected: list[str] = []
    real_is_file = pathlib.Path.is_file

    def recording_is_file(self, *args, **kwargs):
        inspected.append(str(self))
        return real_is_file(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "is_file", recording_is_file)
    snap = take(tmp_path)

    assert "work.md" in snap.files, "the real file must still be captured"
    trespass = [p for p in inspected if f"{os.sep}.git{os.sep}" in p]
    assert not trespass, (
        "the walk inspected entries inside a skipped dir — the skip list is being applied "
        f"after the walk, not during it: {trespass}"
    )


def test_skipped_dirs_contribute_nothing_to_the_snapshot(tmp_path):
    (tmp_path / "kept.md").write_text("kept\n", encoding="utf-8")
    for skipped in (".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".venv"):
        d = tmp_path / skipped / "nested"
        d.mkdir(parents=True)
        (d / "noise.md").write_text("noise\n", encoding="utf-8")

    snap = take(tmp_path)

    assert set(snap.files) == {"kept.md"}

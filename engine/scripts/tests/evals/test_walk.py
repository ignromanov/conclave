"""The eval scans walk a tree that contains a live `.git`. They must not enter it.

Not a style preference. `Path.rglob` descends first and lets the caller filter after, so a
scan racing `git` packing objects hit `FileNotFoundError` on `.git/objects/<xx>` raised by
the WALK, where no per-file `except OSError` can catch it. Measured 2026-09-15, five
trials per interpreter: 3.11.14 raised 5 of 5; 3.13.7 and 3.14.5 suppressed 3 of 3 —
because 3.13 rewrote pathlib globbing onto `os.scandir` with the error swallowed. The
suppressed half is the worse one: the scan walks short and still reports "no leaks".

`snapshot.py` diagnosed and fixed this for itself; `fixture.py` and `traps.py` kept the
unpruned walk and CI went red on py3.11 while py3.13 passed the same commit.

Every test here names the mutation it reddens under, and they come in pairs: a prune
assertion alone is satisfied by a walk that finds nothing at all, so each is paired with
one that proves the walk still reaches ordinary files.
"""
from __future__ import annotations

from pathlib import Path

from evals.fixture import CHARTER_RELPATH, find_norm_carriers, find_real_path_carriers
from evals.walk import SKIP_DIRS, walk_files

_NORM_TEXT = "The engine is append-only: never-silent-delete is a mandatory lifecycle rule.\n"


def _tree(root: Path) -> Path:
    """A fixture-shaped tree: real work, plus the `.git` that `fixture.py` creates on it."""
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "notes.md").write_text("ordinary prose, no norms\n", encoding="utf-8")
    objects = root / ".git" / "objects" / "d6"
    objects.mkdir(parents=True)
    (objects / "0badc0ffee").write_bytes(b"\x78\x9c binary git object")
    return root


def test_the_walk_yields_nothing_under_a_pruned_directory(tmp_path):
    """Reddens under: dropping the `dirnames[:] = [...]` prune in `walk_files`."""
    root = _tree(tmp_path)
    for skip in SKIP_DIRS:
        d = root / skip / "nested"
        d.mkdir(parents=True, exist_ok=True)
        (d / "f.txt").write_text("x", encoding="utf-8")

    walked = {p.relative_to(root).parts[0] for p in walk_files(root)}
    assert walked.isdisjoint(SKIP_DIRS), f"the walk entered machinery: {walked & SKIP_DIRS}"


def test_the_walk_still_reaches_ordinary_files(tmp_path):
    """Pairs with the test above: a walk that yields nothing would satisfy it trivially.

    Reddens under: pruning every directory instead of only `SKIP_DIRS`.
    """
    root = _tree(tmp_path)
    deep = root / "a" / "b" / "c"
    deep.mkdir(parents=True)
    (deep / "buried.md").write_text("x", encoding="utf-8")

    walked = {p.relative_to(root).as_posix() for p in walk_files(root)}
    assert "a/b/c/buried.md" in walked, "the walk stopped short of a nested file"
    assert "docs/notes.md" in walked


def test_a_norm_carrier_hidden_in_dot_git_is_not_a_leak(tmp_path):
    """`fixture.py` runs `git init` AFTER the strip, so the objects hold only stripped
    content — `.git` cannot carry the charter, and the scans lose no coverage by skipping
    it. What they lose by entering it is the race.

    Reddens under: restoring `root.rglob("*")` in `find_norm_carriers`.
    """
    root = _tree(tmp_path)
    (root / ".git" / "COMMIT_EDITMSG").write_text(_NORM_TEXT, encoding="utf-8")
    (root / ".git" / "description.txt").write_text(_NORM_TEXT, encoding="utf-8")

    assert find_norm_carriers(root) == [], "the scan reported a leak inside its own .git"


def test_a_norm_carrier_in_the_work_tree_is_still_found(tmp_path):
    """The paired assertion: skipping `.git` must not cost the detection it exists for.

    Reddens under: any change that makes `find_norm_carriers` return nothing.
    """
    root = _tree(tmp_path)
    (root / "docs" / "VISION.md").write_text(_NORM_TEXT, encoding="utf-8")

    assert find_norm_carriers(root) == ["docs/VISION.md"]


def test_a_charter_inside_dot_git_does_not_trip_the_stray_scan(tmp_path):
    """`assert_no_leakage` and `assert_seed_safe` both scan for a file named
    `constitution.md` anywhere under the root. Both used `rglob`, and both were in the
    four tests CI failed on.

    Reddens under: restoring `fx.root.rglob(CHARTER_RELPATH)`.
    """
    root = _tree(tmp_path)
    (root / ".git" / CHARTER_RELPATH).write_text("charter\n", encoding="utf-8")

    strays = [p for p in walk_files(root) if p.name == CHARTER_RELPATH]
    assert strays == [], "a path under .git was offered as a charter stray"


def test_a_charter_in_the_work_tree_is_still_a_stray(tmp_path):
    """Paired with the test above, so the scan cannot pass by seeing nothing."""
    root = _tree(tmp_path)
    (root / "docs" / CHARTER_RELPATH).write_text("charter\n", encoding="utf-8")

    strays = [p.relative_to(root).as_posix() for p in walk_files(root)
              if p.name == CHARTER_RELPATH]
    assert strays == [f"docs/{CHARTER_RELPATH}"]


def test_a_real_path_inside_dot_git_is_not_reported(tmp_path):
    """The third `rglob` in `fixture.py`, on the same tree and with the same race."""
    root = _tree(tmp_path)
    (root / ".git" / "config.txt").write_text(f"worktree = {Path.home()}\n", encoding="utf-8")

    assert find_real_path_carriers(root) == [], "a real path under .git was called a leak"

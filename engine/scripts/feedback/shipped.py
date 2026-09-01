"""shipped.py — is a predicate's evidence actually in the shipped tree? (#160)

`feedback_verify` evaluates predicates by reading the working tree, which is the right
snapshot for reporting ("how does it stand right now") and for the `--set-verify`
admission test. It is the wrong snapshot for `--apply`, which writes `status=resolved`:
a branch that is never merged, or an edit that is never committed, closes an item exactly
as well as shipped code, and afterwards a false close is indistinguishable from a true one.

This module answers one question per target — *is what I just read also what shipped* —
and it lives outside `feedback_verify` on purpose. That module states, and keeps, the
invariant "file-read + regex; NO shell exec"; git belongs to the impure layer that calls it.

The check is deliberately conservative. A target that differs from the ref for an unrelated
reason is held back rather than closed, and held items are reported, never silently dropped:
they close on the next sweep once the work lands.
"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from pathlib import Path

# A tree that is not version controlled is an installed artefact — a marketplace plugin
# is unpacked, not cloned — so what is on disk IS what shipped. Closing against it is
# correct, and the snapshot name says which case it was.
UNTRACKED_TREE = "installed tree (not version controlled)"


def _git(repo: Path, *args: str) -> tuple[int, str]:
    res = subprocess.run(["git", "-C", str(repo), *args],
                         capture_output=True, text=True)
    return res.returncode, res.stdout.strip()


@lru_cache(maxsize=64)
def repo_of(directory: Path) -> Path | None:
    """The git top level containing `directory`, or None when it is not in a repo."""
    if not directory.is_dir():
        return None
    rc, out = _git(directory, "rev-parse", "--show-toplevel")
    return Path(out) if rc == 0 and out else None


@lru_cache(maxsize=64)
def shipped_ref(repo: Path) -> str:
    """The ref that stands for 'shipped', most authoritative first.

    The upstream of the current branch is the honest answer: work is shipped when it has
    landed there. `origin/HEAD` covers a detached or never-pushed branch. `HEAD` is the
    floor — it no longer proves the work is merged, only that it is committed, which still
    catches the case the issue measured (an uncommitted edit closing an item)."""
    for ref in ("@{upstream}", "origin/HEAD"):
        rc, _ = _git(repo, "rev-parse", "--verify", "--quiet", ref)
        if rc == 0:
            rc2, name = _git(repo, "rev-parse", "--abbrev-ref", ref)
            return name if rc2 == 0 and name else ref
    return "HEAD (no upstream — committed, not proven merged)"


def is_shipped(target: Path) -> tuple[bool, str]:
    """(shipped, snapshot) for one absolute target path.

    shipped=False means the working tree disagrees with the ref about this file, so a
    verdict read off disk is evidence about unshipped work."""
    repo = repo_of(target.parent if target.parent.is_dir() else target.parent.parent)
    if repo is None:
        return True, UNTRACKED_TREE
    ref = shipped_ref(repo)
    bare_ref = ref.split(" ")[0]

    # Present but untracked: `git diff <ref>` cannot see it, so it would read as
    # unchanged. A file git has never heard of has certainly not shipped.
    if target.exists():
        rc, _ = _git(repo, "ls-files", "--error-unmatch", "--", str(target))
        if rc != 0:
            return False, ref

    rc, out = _git(repo, "diff", "--name-only", bare_ref, "--", str(target))
    if rc != 0:
        # The ref does not resolve (a repo with no commits yet). Cannot prove shipped.
        return False, ref
    return (out == ""), ref

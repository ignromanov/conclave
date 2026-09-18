"""The document the charter's amendment rule requires, and nothing has ever produced.

`constitution.md` §6 gates the `mechanical` tier on evidence, and names the evidence:

    A principle MUST NOT be tagged `mechanical` until its named check exists and has been
    observed failing on a violation. A check never seen red is a check never seen.
    ... it is gated on a document — and the document is a failing test.

`test_constitution.py` closes half of that and says so in its own docstring: it refuses a tag
whose check is absent, and states plainly that it "cannot verify that history". So the required
document has no writer. A rule that obliges a record nobody produces is the shape this engine
keeps finding in itself — a consumer with no producer (#116), a CLI no protocol invokes (093) —
here in the governing document rather than in a script.

This module is the writer. A falsification is a mutation small enough to read, applied to a copy
of the tree, whose only job is to make one named check go red.

Two design choices, both load-bearing:

**The copy is of the WORKING TREE, not of `HEAD`.** `git archive HEAD` is how the eval fixtures
are built and would have been the cheaper call, but it verifies the last commit rather than the
edit in front of you: a session that breaks a check and adds its falsification in the same change
would be graded on the commit before it, and pass on evidence about different code. The copy is
made from `git ls-files`, so it is the tracked tree as it stands.

**Each falsification is asserted green FIRST, then red.** A check that is already failing would
otherwise satisfy "the mutation makes it fail" without the mutation doing anything, and a
permanently red check would certify every principle that names it.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_REL = "engine/scripts"


@dataclass(frozen=True)
class Falsification:
    """One mutation, and the charter principle whose check it must redden."""

    principle: str
    """The charter numeral, exactly as `### 0.` / `### I.` spells it."""

    path: str
    """Repo-relative file to mutate."""

    old: str
    """Text to replace. MUST occur exactly once, or the falsification is not the one described."""

    new: str

    destroys: str
    """What the mutation breaks, in the terms of the principle. Read by a human, not by code."""


# Keyed by the id a principle names in its `**Falsified by**:` line.
#
# Adding a principle to the `mechanical` tier is a **full review** amendment under §6 — a spec and
# the operator's approval — so this registry does not grow by a session's own decision. What a
# session may do, fast-track, is record the evidence a tag already required. That is what these
# two are.
FALSIFICATIONS: dict[str, Falsification] = {
    "p0-a-tier-claims-a-check-it-does-not-have": Falsification(
        principle="0",
        path="constitution.md",
        old="**Tier**: `declaratory` — **none of the three mechanisms exists in code.**",
        new="**Tier**: `mechanical` — **none of the three mechanisms exists in code.**",
        destroys=(
            "Principle III is relabelled `mechanical` while naming no check — the charter "
            "claiming an enforcement it does not have, which is the whole of Principle 0."
        ),
    ),
    "p1-archiving-a-review-drops-its-second-item": Falsification(
        principle="I",
        path="engine/scripts/feedback/feedback_archive.py",
        old='                "items": items,',
        new='                "items": items[:1],',
        destroys=(
            "The archive row keeps only the first item, so archiving a two-item review destroys "
            "the second one — the exact loss the check was written for, restored."
        ),
    ),
}


def working_tree_copy(dest: Path) -> Path:
    """Copy every tracked file, as it is on disk right now, into *dest*.

    `git ls-files` rather than `git archive`: the archive would emit the committed blob and the
    point is to grade the tree in front of us. Untracked files are excluded deliberately — a
    falsification that depends on a file nobody has committed is not reproducible by anyone else.
    """
    listing = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
        check=True, capture_output=True, text=True,
    ).stdout
    names = [n for n in listing.split("\0") if n]
    if not names:
        raise RuntimeError("git ls-files returned nothing — the copy would be an empty tree, "
                           "and a check that passes over an empty tree proves nothing")
    for name in names:
        src = REPO_ROOT / name
        if not src.is_file():          # a deleted-but-tracked path
            continue
        out = dest / name
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, out)
    return dest


def apply(tree: Path, f: Falsification) -> None:
    """Plant *f* in *tree*, refusing an anchor that is not unique.

    The count assertion is not ceremony: an anchor that matches twice mutates a second site
    nobody described, and an anchor that matches zero times leaves the tree pristine while the
    run below reports a check that "did not redden" — a false verdict about a real gate.
    """
    p = tree / f.path
    s = p.read_text(encoding="utf-8")
    n = s.count(f.old)
    if n != 1:
        raise AssertionError(
            f"falsification for principle {f.principle}: anchor occurs {n} times in {f.path}, "
            "expected exactly 1 — the mutation no longer describes this code"
        )
    p.write_text(s.replace(f.old, f.new), encoding="utf-8")


def run_check(tree: Path, check: str) -> tuple[bool, str]:
    """Run one `path::test_name` inside *tree*. Returns (passed, output tail).

    `check` is spelled relative to `engine/scripts/`, the way the charter writes it.
    """
    rel_path, test_name = check.split("::", 1)
    target = f"{SCRIPTS_REL}/{rel_path}::{test_name}"
    r = subprocess.run(
        [sys.executable, "-m", "pytest", target,
         "-o", "addopts=-q --tb=line", "-p", "no:cacheprovider"],
        cwd=tree, capture_output=True, text=True,
    )
    return r.returncode == 0, (r.stdout or r.stderr)[-1500:]

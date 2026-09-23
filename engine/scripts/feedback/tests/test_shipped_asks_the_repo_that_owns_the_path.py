"""A predicate's evidence belongs to the repo that tracks it, not to the one it is spelled
through (#323).

THE REPORTED SYMPTOM. Six accepted items carried predicates under `.claude/`. The work was
committed and pushed; every sweep since still printed `HELD ... evidence is not in
origin/master ... (land the work; the next sweep closes it)`. The work was landed. Because a
held item is never closed by `--apply` and is still counted as covered by
`predicate-coverage`, the backlog reported a closing mechanism that could not fire.

THE TICKET'S DIAGNOSIS IS NOT THE MECHANISM. #323 states that `shipped.py` "resolves a
`--root project` path against the project root and asks **that** checkout's git", and
prescribes resolving the owning repository from the path instead. Executed against a synthetic
deployment shape #1, `repo_of` was already doing exactly that: it returned the DATA repo, not
the product repo. The prescription was already in the code.

The failure is one step further on. `.claude` is a symlink into `.conclave/`, so the path
*handed* to git is the logical one while the repo git resolved is the physical one, and git
refuses it outright:

    fatal: /<product>/.claude/hooks/test_bash_gate_hazards.py is outside repository
           at '/<product>/.conclave'                                      (rc=128)

`is_shipped` folded any non-zero return code into its domain answer, so **an invocation that
could not run was reported as "this file did not ship"** — a wiring error wearing the costume
of evidence. That is the whole defect, and the symlink is only the way it was reached.

WHY THE FIX IS A RELATIVE PATHSPEC AND NOT A `realpath`. Resolving the target does make this
case work — measured, `shipped=True` the moment the path is realpath'd. But it repairs one
route into the class and leaves the class: any future arrangement where the target's spelling
and the repo's identity disagree returns "unshipped" again, silently, with the same reassuring
sentence telling the operator to land work that is already landed. Asking git for a path
*relative to the repository it just named* cannot be outside that repository. The class is
removed by construction rather than handled.

WHY A SYNTHETIC TREE. On conclave-self the DATA root is a plain subdirectory and `.claude` is
not a symlink, so defect and fix agree on every path and the suite stays green over either —
the same blindness recorded for #170. The fixture below builds shape #1 from
`docs/architecture/instance-contract.md` §6 for real: a product repo that gitignores both
`.conclave` and `.claude`, a DATA repo inside it with its own origin, and the symlink across.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import shipped
from shipped import is_shipped, repo_of


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


class Shape1:
    """Deployment shape #1: DATA at `<repo>/.conclave/`, `.claude` a symlink into it."""

    def __init__(self, product: Path, data: Path, hook: Path, physical: Path) -> None:
        self.product = product
        self.data = data
        self.hook = hook          # spelled through the symlink, as a predicate spells it
        self.physical = physical  # the same file by its real path


@pytest.fixture
def shape1(tmp_path: Path) -> Shape1:
    origin = tmp_path / "data-origin.git"
    subprocess.run(["git", "init", "--bare", "-q", str(origin)], check=True)

    product = tmp_path / "product"
    product.mkdir()
    _git(product.parent, "init", "-q", "-b", "master", str(product))
    _git(product, "config", "user.email", "p@t")
    _git(product, "config", "user.name", "p")
    (product / ".gitignore").write_text(".conclave\n.claude\n")
    (product / "app.py").write_text("x = 1\n")
    _git(product, "add", "-A")
    _git(product, "commit", "-qm", "the product, which knows nothing of the agent tree")

    data = product / ".conclave"
    hooks = data / ".claude" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "test_bash_gate_hazards.py").write_text("# the fix, landed\n")
    _git(data.parent, "init", "-q", "-b", "master", str(data))
    _git(data, "config", "user.email", "d@t")
    _git(data, "config", "user.name", "d")
    _git(data, "remote", "add", "origin", str(origin))
    _git(data, "add", "-A")
    _git(data, "commit", "-qm", "land the hook and its test")
    _git(data, "push", "-q", "-u", "origin", "master")
    _git(data, "remote", "set-head", "origin", "master")

    (product / ".claude").symlink_to(Path(".conclave/.claude"))

    shipped.repo_of.cache_clear()
    shipped.shipped_ref.cache_clear()
    return Shape1(
        product=product,
        data=data,
        hook=product / ".claude" / "hooks" / "test_bash_gate_hazards.py",
        physical=data / ".claude" / "hooks" / "test_bash_gate_hazards.py",
    )


# ------------------------------------------------------- the fixture is what it claims to be


def test_the_fixture_is_the_deployment_shape_the_defect_needs(shape1: Shape1) -> None:
    """Anti-vacuity, and the ticket's own evidence re-executed rather than quoted.

    Every assertion below is meaningless if the two repos are not genuinely separate and the
    product is not genuinely blind to the agent tree."""
    assert shape1.hook.is_file() and shape1.hook.resolve() == shape1.physical.resolve()
    assert (shape1.product / ".claude").is_symlink()

    ignored = subprocess.run(
        ["git", "-C", str(shape1.product), "check-ignore", "-v", ".claude"],
        capture_output=True, text=True,
    )
    assert ignored.returncode == 0, "the product repo does not ignore .claude — not shape #1"

    known = subprocess.run(
        ["git", "-C", str(shape1.product), "ls-files", "--error-unmatch", "--",
         ".claude/hooks/test_bash_gate_hazards.py"],
        capture_output=True, text=True,
    )
    assert known.returncode != 0, "the product repo tracks the hook — not shape #1"

    tracked = _git(shape1.data, "ls-tree", "origin/master", "--name-only", ".claude/hooks/")
    assert "test_bash_gate_hazards.py" in tracked.stdout, "the work is not actually landed"


def test_the_owning_repo_was_never_the_thing_that_was_wrong(shape1: Shape1) -> None:
    """The ticket's stated cause, checked. `repo_of` already answers DATA, not the product.

    Recorded because the prescribed fix — 'resolve the owning repository from the path' — was
    already implemented, and shipping it again would have left the defect in place while the
    issue closed."""
    assert repo_of(shape1.hook.parent) == shape1.data.resolve()
    assert repo_of(shape1.hook.parent) != shape1.product.resolve()


# ----------------------------------------------------------------------------- the defect


def test_a_landed_hook_reached_through_the_symlink_is_shipped(shape1: Shape1) -> None:
    """The reported symptom, as a test. Committed, pushed, present in `origin/master`."""
    ok, snapshot = is_shipped(shape1.hook)
    assert ok is True, (
        f"landed work read as unshipped against {snapshot} — the sweep would print HELD "
        "and tell the operator to land work that is already in origin/master"
    )
    assert "origin/master" in snapshot


def test_the_answer_does_not_depend_on_how_the_path_is_spelled(shape1: Shape1) -> None:
    """Equivalence over a hand-written expectation.

    The two paths name one file on one disk in one repository. Any difference in the verdict
    is the instrument reporting on itself rather than on the evidence — which is why asserting
    only "the symlinked path says True" would be too weak: it passes for a check that has
    stopped looking at anything."""
    assert is_shipped(shape1.hook) == is_shipped(shape1.physical)


# --------------------------------------- and the fix must not turn the check into a stamp


def test_an_uncommitted_edit_through_the_symlink_is_still_not_shipped(shape1: Shape1) -> None:
    """#160's whole purpose survives the repair: on-disk work is not shipped work."""
    shape1.hook.write_text("# edited, committed nowhere\n")
    ok, _ = is_shipped(shape1.hook)
    assert ok is False


def test_an_untracked_file_through_the_symlink_is_not_shipped(shape1: Shape1) -> None:
    new = shape1.hook.parent / "test_added_today.py"
    new.write_text("def test_thing(): ...\n")
    ok, _ = is_shipped(new)
    assert ok is False


def test_work_committed_but_not_pushed_through_the_symlink_is_not_shipped(
    shape1: Shape1,
) -> None:
    """The #259 case, reached through the symlink: committed locally is not landed."""
    shape1.hook.write_text("# committed to the local branch only\n")
    _git(shape1.data, "add", "-A")
    _git(shape1.data, "commit", "-qm", "local only")
    shipped.repo_of.cache_clear()
    shipped.shipped_ref.cache_clear()
    ok, _ = is_shipped(shape1.hook)
    assert ok is False

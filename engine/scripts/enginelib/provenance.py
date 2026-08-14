"""provenance.py — which checkout is this process actually running? (GH#126)

`site-packages/_editable_impl_conclave_engine.pth` hard-codes the MAIN checkout's
`engine/scripts` onto `sys.path` for every Python process on the machine. Inside a worktree a
bare `python -m engine` therefore imports the main checkout's code and reports on it as if it
were the caller's own tree. `CONCLAVE_ENGINE_ROOT` does not fix this — it governs data-root
resolution, not imports — which is why this survived three earlier encounters with GH#86.

`pytest` is immune by accident: `pytest.ini`'s `pythonpath` is inserted ahead of the `.pth`
entry. So the suite is trustworthy and every hand-run `python -m engine` verification inside a
worktree silently is not. That asymmetry is the whole danger: the trap fires precisely on the
ad-hoc runs nobody gates.

No process I/O here — this module decides, `engine/cmd` prints. `message()` returns a string,
which is not I/O.
"""
from dataclasses import dataclass
from pathlib import Path

# What makes a directory a Conclave CODE checkout: the dispatcher's own entrypoint, at the
# one path every checkout has and nothing else does.
_MARKER = Path("engine") / "scripts" / "engine" / "__main__.py"


def checkout_root_of(path: Path) -> Path | None:
    """The nearest enclosing Conclave CODE checkout, or None if `path` is not inside one.

    Nearest, not outermost: `worktrees/<name>/` sits inside the main checkout and is itself a
    full checkout, so the outermost match would call every worktree the main tree and see no
    mismatch at all — the detector would be blind to the only case it exists for.
    """
    here = path.resolve()
    for d in (here, *here.parents):
        if (d / _MARKER).is_file():
            return d
    return None


@dataclass(frozen=True)
class TreeMismatch:
    """The imported code and the caller are in different checkouts."""

    running_from: Path
    standing_in: Path

    def message(self) -> str:
        return (
            f"WARNING: this ran {self.running_from}, not the tree you are standing in.\n"
            f"  imported engine: {self.running_from}\n"
            f"  current tree:    {self.standing_in}\n"
            f"  The editable install pins the main checkout onto sys.path (GH#126), so this\n"
            f"  result describes another branch. Re-run with both pins:\n"
            f'    CONCLAVE_ENGINE_ROOT="$PWD/engine" PYTHONPATH="$PWD/engine/scripts" '
            f"python -m engine ...\n"
        )


def diagnose_tree(*, module_file: Path, cwd: Path) -> TreeMismatch | None:
    """Report a cross-tree run, or None when there is nothing to claim.

    Silent unless BOTH sides resolve to a checkout and they differ. A consumer running an
    installed plugin from their own project has no second tree to compare against; warning
    there would earn the detector an off-switch, and the trap it catches is ours, not theirs.
    """
    standing_in = checkout_root_of(cwd)
    if standing_in is None:
        return None
    running_from = checkout_root_of(module_file)
    if running_from is None or running_from == standing_in:
        return None
    return TreeMismatch(running_from=running_from, standing_in=standing_in)

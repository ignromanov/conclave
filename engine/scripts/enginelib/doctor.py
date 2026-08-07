"""enginelib/doctor.py — First-Launch preflight checks (#49c).

I/O-free of stdout/argparse/sys.exit (file reads + an optional --fix seed are OK).
The CLI adapter (engine/cmd/doctor.py) formats Checks and maps exit_code().

Asserts the preconditions that silently broke a real First Launch: a resolvable
data root, a well-formed hot.md (so `engine file decision` can't crash on a
missing section header), and — when an advisor is given — that it is discoverable
in the instance registry.

Also reports local branches with no common ancestor with the default branch (#58).
Nothing else notices those: they look ordinary in `git branch`, and only a merge
attempt reveals that the work on them cannot be integrated at all.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

_HOT_SECTIONS = ("## Now", "## Open threads", "## Recent decisions", "## Watch")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _hot_check(root: Path, fix: bool) -> Check:
    hot = root / "agent-memory" / "hot.md"
    if hot.is_file():
        text = hot.read_text(encoding="utf-8")
        missing = [s for s in _HOT_SECTIONS if s not in text]
        if not missing:
            return Check("hot.md", True, "well-formed")
        # Malformed: never silently clobber — a raw file may hold real content.
        return Check("hot.md", False, f"missing sections: {', '.join(missing)} (manual repair)")
    if fix:
        from enginelib.memory import hot as hotmod
        hotmod.init(hot_path=hot)
        return Check("hot.md", True, f"seeded skeleton at {hot}")
    return Check("hot.md", False, f"missing ({hot}) — run `engine doctor --fix` to seed")


def _advisor_check(root: Path, advisor: str) -> Check:
    from enginelib.advisors import known_advisors, with_meta
    known = known_advisors(root)
    ok = advisor in with_meta(known)
    if ok:
        return Check(f"advisor:{advisor}", True, "in instance registry")
    listing = ", ".join(sorted(known)) or "(none hired)"
    return Check(f"advisor:{advisor}", False, f"not in registry — known: {listing}")


def _git(repo: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    return proc.returncode, proc.stdout.strip()


def _default_branch(repo: Path) -> str | None:
    """The branch orphans are measured against — derived, never assumed to be `master`."""
    code, out = _git(repo, "symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
    if code == 0 and out:
        return out.rsplit("/", 1)[-1]
    for name in ("master", "main"):
        code, _ = _git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}")
        if code == 0:
            return name
    return None


def _orphan_branches(repo: Path) -> list[str]:
    """Local branches sharing no ancestor with the default branch.

    `git merge-base` exits non-zero with no output when two histories are disjoint,
    which is the only signal git gives for it — there is no error message to grep.
    """
    code, _ = _git(repo, "rev-parse", "--show-toplevel")
    if code != 0:
        return []            # not a git repo: nothing measurable, not a failure
    base = _default_branch(repo)
    if base is None:
        return []
    code, out = _git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    if code != 0:
        return []
    orphans = []
    for branch in (ln.strip() for ln in out.splitlines()):
        if not branch or branch == base:
            continue
        if _git(repo, "merge-base", base, branch)[0] != 0:
            orphans.append(branch)
    return orphans


def _merge_base_check(repos: list[Path]) -> Check:
    # Dedupe by git toplevel, not by the path handed in: CODE root and engine root are
    # different paths in the SAME repository, and in a single-repo instance the DATA root
    # is a third. Labelling by toplevel also names the repository rather than whichever
    # subdirectory the caller happened to pass.
    seen: set[str] = set()
    findings: list[str] = []
    for repo in repos:
        code, top = _git(repo, "rev-parse", "--show-toplevel")
        if code != 0 or not top or top in seen:
            continue
        seen.add(top)
        findings += [f"{Path(top).name}:{b}" for b in _orphan_branches(repo)]
    if not findings:
        return Check("merge-base", True, "every local branch shares history with its default branch")
    return Check(
        "merge-base", False,
        f"no common ancestor with the default branch: {', '.join(findings)} — "
        "`git merge` can never integrate these; recover with `git format-patch` / "
        "`git diff` + apply, or delete the branch once its work has landed",
    )


def run_checks(
    root: Path,
    advisor: str | None = None,
    fix: bool = False,
    repos: list[Path] | None = None,
) -> list[Check]:
    """Return the preflight Checks for a data root.

    - data-root: the root exists as a directory.
    - hot.md: exists and carries all canonical sections (seeded when fix=True).
    - advisor:<id>: discoverable via known_advisors (forge accepted as META).
    - merge-base: no local branch is stranded off the default branch's history (#58).

    `repos` is passed in rather than discovered here. Resolving CODE/DATA roots from the
    environment is the CLI adapter's job; doing it inside the pure core would make every
    hermetic test read whatever repository the developer happens to be standing in —
    the same ambient-root coupling that made a suite pass while its isolation did nothing.
    """
    checks: list[Check] = [
        Check("data-root", root.is_dir(), str(root)),
        _hot_check(root, fix),
        _merge_base_check(repos if repos is not None else [root]),
    ]
    if advisor:
        checks.append(_advisor_check(root, advisor))
    return checks


def exit_code(checks: list[Check]) -> int:
    """0 when every check passed, 1 otherwise."""
    return 0 if all(c.ok for c in checks) else 1

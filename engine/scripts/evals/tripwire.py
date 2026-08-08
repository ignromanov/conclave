"""tripwire.py — abort a running eval the moment it discovers it has touched a real repo.

Root cause of the pilot2 escape (spec 104 P0): fixtures were built INSIDE the real DATA tree
(`<data>/eval/runs/<run-id>/fixtures`), one `cd` or absolute path away from the real CODE and DATA
repos. Moving fixtures to the system tempdir (see `_pilot`/`_run` in `engine/cmd/eval.py`) closes
that specific hole, but it is not a proof the agent can never reach the real trees by some other
path (a leaked absolute path in seeded content, an inherited env var, a symlink). This is the
backstop: fingerprint the real CODE and DATA repos' git state once at run start, re-check after
every trial, and abort loudly — before more trials compound the damage — the instant either one
changes in a way the run itself did not authorize.

A repo write the harness itself performs deliberately (the pilot/run appending to its own
`eval/runs/<run-id>/trials.jsonl` and `.transcript` files inside DATA) is not an escape and must not
trip the wire; `ignore` carves that path back out of the watched status.

`DirWatch`/`watch_dir`/`check_dir` extend the same idea to a plain directory that is not a git
repo at all: the operator's real `~/.claude/projects/` (spec 104 P0 hardening, 2026-07-27). Even
with sub-task 1's `--no-session-persistence` in place, a NEW FILE appearing there mid-run is
exactly the pilot3 leak shape (a session transcript, or the durable auto-memory write one t04
trial made) and must abort the run the same way a CODE/DATA fingerprint change does. Files, not
directory entries — see `DirWatch` for why the distinction cost a rehearsal run to learn.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path


@dataclass(frozen=True)
class Fingerprint:
    label: str
    root: Path
    head: str     # "" when `root` is not a git repo — nothing to watch
    status: str
    ignore: tuple[str, ...] = field(default=())


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return proc.stdout.strip()


def fingerprint(root: Path, label: str, ignore: tuple[str, ...] = ()) -> Fingerprint:
    """HEAD sha + a `git status --porcelain` fingerprint for `root`, with `ignore` (paths relative
    to `root`) excluded from the status — the run's own writes to its output dir are expected and
    must not be mistaken for an escape."""
    if not (root / ".git").is_dir():
        return Fingerprint(label=label, root=root, head="", status="", ignore=ignore)
    head = _git(root, "rev-parse", "HEAD")
    status_args = ["status", "--porcelain", "--", "."]
    status_args += [f":(exclude){rel}" for rel in ignore]
    status = _git(root, *status_args)
    return Fingerprint(label=label, root=root, head=head, status=status, ignore=ignore)


def check(baseline: Fingerprint) -> str | None:
    """Re-fingerprint `baseline.root` (same `ignore`) and compare to `baseline`. Returns a
    human-readable description of what changed, or None if nothing did (including the case where
    `root` was never a git repo — nothing to watch)."""
    if not (baseline.root / ".git").is_dir():
        return None
    current = fingerprint(baseline.root, baseline.label, ignore=baseline.ignore)
    if current.head != baseline.head:
        return (
            f"{baseline.label} repo HEAD changed: "
            f"{baseline.head or '(none)'} -> {current.head or '(none)'}"
        )
    if current.status != baseline.status:
        return f"{baseline.label} repo working tree changed (git status differs from the baseline)"
    return None


@dataclass(frozen=True)
class DirWatch:
    """A non-git directory watched by the set of FILES beneath it — `~/.claude/projects/` has no
    `.git`, so `Fingerprint`'s HEAD+status approach does not apply.

    Files, not entry names. v1 watched top-level entry names, and the 2026-07-27 rehearsal died on
    its first trial against an EMPTY `<project>/memory/` pair: `--no-session-persistence` does stop
    the transcript write, but the CLI mkdir's that scaffold unconditionally, and a name-set diff
    cannot tell an empty scaffold from a leaked transcript. Under a name watch no run could ever
    start; under a file watch the scaffold is tolerated and everything that would actually carry
    data out — a transcript, or the durable `memory/MEMORY.md` auto-memory write pilot3's t04 trial
    made — still aborts the run.

    Honest scope: an empty directory leaks nothing today, but it IS the open channel's mouth. This
    watches the channel for cargo rather than sealing it; sealing it needs `--bare`, which this
    machine cannot authenticate and which would change the very environment the run measures."""
    label: str
    path: Path
    baseline: frozenset[str]
    scope_token: str | None = None


def _files_under(path: Path, scope_token: str | None = None) -> frozenset[str]:
    """Posix relpaths of every file beneath `path`, recursively. Directories are not members:
    creating one leaks nothing. Measured at 1873 files in 23 ms on the operator's real projects
    dir — cheap enough to re-walk after every trial.

    With `scope_token`, only files whose TOP-LEVEL entry name contains that token are members —
    see `watch_dir`."""
    if not path.is_dir():
        return frozenset()
    rels = (p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file())
    if scope_token is None:
        return frozenset(rels)
    return frozenset(r for r in rels if scope_token in r.split("/", 1)[0])


def watch_dir(path: Path, label: str, scope_token: str | None = None) -> DirWatch:
    """Snapshot the files beneath `path`. `path` not existing yet is not an error — the baseline is
    just empty, and any file appearing later trips the wire the same as any other.

    `scope_token` narrows the watch to top-level entries whose name contains it. This exists for
    `~/.claude/projects/`, which — unlike DATA — is ONE directory per machine and cannot be cloned
    away from the operator's concurrent sessions: the 2026-07-27 rehearsal died on trial 5 when a
    parallel forge session wrote its own auto-memory there. Pass this run's fixture workdir name
    (`conclave-work-<rand>`, which is already `[a-z0-9-]` only and so survives whatever escaping
    the CLI applies when it derives a project-dir name from a cwd). Every trial's cwd is inside
    that workdir, so every project dir a TRIAL produces carries the token, and every project dir
    anyone ELSE produces does not.

    Residual scope, stated rather than implied: an agent that escaped its fixture and launched a
    nested CLI from some other cwd would produce a project dir without the token, invisible to
    this watch. That escape is what the CODE and DATA git fingerprints are for; this watch covers
    the channel the trial itself opens."""
    return DirWatch(
        label=label, path=path, baseline=_files_under(path, scope_token), scope_token=scope_token
    )


# Writes the CLI itself makes into a project dir that are the harness's own footprint rather than
# anything the agent did with a repo. Swept after each trial and counted in the run's report — not
# silently permitted, and deliberately narrow: content (transcripts, `memory/MEMORY.md`) is never
# tolerated. Discovered by rehearsal-n2d trial 14, where a trial's agent spawned an Explore
# subagent and `--no-session-persistence` did not cover the subagent metadata write.
TOLERATED_PROJECT_WRITES = (
    "*/subagents/*.meta.json",
    # A CONTENT-BEARING spill, tolerated only conditionally — see `sweep_tolerated`. Discovered by
    # scored-001 trial 16 (2026-07-29): a trial's Grep spilled 32 KB of its own output here, past
    # --no-session-persistence.
    "*/tool-results/*",
)

# Patterns whose match is arbitrary tool output rather than harness bookkeeping, and so may only be
# swept once its content is known to name nothing real. Kept as a separate set because the
# distinction is the whole guarantee: metadata is tolerated by NAME, content only by INSPECTION.
CONTENT_BEARING_PROJECT_WRITES = ("*/tool-results/*",)


def sweep_tolerated(
    baseline: DirWatch,
    patterns: tuple[str, ...],
    content_bearing: tuple[str, ...] = CONTENT_BEARING_PROJECT_WRITES,
) -> list[str]:
    """Delete the NEW files under `baseline` matching any of `patterns` and return their relpaths.

    Called after each trial, BEFORE `check_dir`, so a tolerated write neither aborts the run nor
    accumulates on the operator's disk. Everything else is left exactly where it is, for
    `check_dir` to fire on.

    A file also matching `content_bearing` is swept ONLY if it names no path that exists on disk.
    That asymmetry is deliberate. `subagents/*.meta.json` is the CLI's own bookkeeping and can be
    tolerated by name; `tool-results/*` is whatever a tool returned, and a trial that READ a real
    repo would deposit that content here — a channel no git fingerprint covers, since CODE and DATA
    are watched for mutations and a read is not one. Sweeping such a file would destroy the only
    evidence the trial reached outside its fixture, so it is left for `check_dir` to abort on. The
    "does this name something real" test is `fixture.real_path_tokens`, the same one the fixture
    builder applies to seeded content, so the two cannot drift apart."""
    from evals.fixture import real_path_tokens

    swept: list[str] = []
    for rel in sorted(_files_under(baseline.path, baseline.scope_token) - baseline.baseline):
        if not any(fnmatch(rel, pat) for pat in patterns):
            continue
        path = baseline.path / rel
        if any(fnmatch(rel, pat) for pat in content_bearing):
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue  # unreadable: not swept, so `check_dir` still fires on it
            if real_path_tokens(text):
                continue
        path.unlink(missing_ok=True)
        swept.append(rel)
    return swept


def check_dir(baseline: DirWatch) -> str | None:
    """Re-walk `baseline.path` and compare files to `baseline`. Returns a human-readable
    description of what appeared, or None if nothing new did."""
    new = _files_under(baseline.path, baseline.scope_token) - baseline.baseline
    if not new:
        return None
    sample = ", ".join(sorted(new)[:3])
    more = f" (+{len(new) - 3} more)" if len(new) > 3 else ""
    return f"{baseline.label}: new file appeared under {baseline.path}: {sample}{more}"

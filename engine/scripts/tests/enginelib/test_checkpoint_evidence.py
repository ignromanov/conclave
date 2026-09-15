"""test_checkpoint_evidence.py — the check that stands between a `--done` line and R5's M.

Spec 117 T3. The mutation the whole file exists for is one line: make `resolve` return
`Check(ref, True, ...)` unconditionally. Every test below goes green under it, which is what
"the agent's say-so wearing a syntax" means in practice — so each test is also named by the
*narrower* mutation it alone catches.

Hermetic by construction rather than by discipline: `Roots` names every location a resolver
reaches, so these tests pin all five and touch no ambient state. The `git` binary is the one
exception and it is the instrument under test — the repositories are real, built in tmp_path.
"""
from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from enginelib.checkpoint.evidence import Roots, resolve, resolve_all


def _git(cwd, *args) -> str:
    env = {
        "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd),
    }
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, env=env, check=True
    ).stdout.strip()


@pytest.fixture()
def roots(tmp_path) -> Roots:
    # Plugin-mode shape, on purpose: the engine checkout is somewhere else entirely and the
    # instance is project/ with its DATA root inside it. On the dogfooding instance the two
    # collapse — `project_root()` and the CODE checkout are measurably the SAME directory —
    # so a fixture built in that shape cannot tell "searched CODE" from "searched the project",
    # and every assertion below about which tree `file:` reads would be true either way.
    code, project = tmp_path / "code", tmp_path / "project"
    project.mkdir()
    data = project / ".conclave"
    for repo in (code, data):
        repo.mkdir()
        _git(repo, "init", "-q", "-b", "master")
        # Distinct content per repo, and it is load-bearing. Seeded identically, the two
        # repositories produce the SAME commit sha — same tree, same message, same author,
        # same second — and the "a commit in either repository counts" test below then asserts
        # nothing at all: it looks up a DATA sha that CODE also has. Caught by the mutation
        # (restrict the search to CODE and the test stayed green), not by reading it.
        (repo / "seed.txt").write_text(f"seed for {repo.name}\n", encoding="utf-8")
        _git(repo, "add", "seed.txt")
        _git(repo, "commit", "-qm", f"seed {repo.name}")
    gh_cache = tmp_path / "gh-cache"
    gh_cache.mkdir()
    return Roots(
        code=code, data=data, project=project, gh_cache=gh_cache, index=tmp_path / "index.jsonl"
    )


def _snapshot(roots: Roots, name: str, *, number: int, state: str, age_seconds: int, ttl: int = 900):
    stamp = (datetime.now(UTC) - timedelta(seconds=age_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
    items = [{"number": number, "state": state, "title": "t", "labels": []}]
    (roots.gh_cache / name).write_text(
        f'---\ntype: gh-snapshot\ncaptured_at: "{stamp}"\nttl_seconds: {ttl}\n---\n\n'
        f"```json\n{json.dumps(items)}\n```\n",
        encoding="utf-8",
    )


# --- commit: -----------------------------------------------------------------------------

def test_a_revision_expression_is_refused_where_an_object_name_is_accepted(roots):
    """Mutation: drop `_SHA_RE` and pass the ref straight to `git cat-file`.

    `cat-file -e` takes a *revision expression*, so `HEAD` and `master` resolve in every
    repository that has any commit at all. Without the guard, `--evidence commit:HEAD` is a
    check that cannot fail — a constant True wearing the shape of an executed check, which is
    the exact thing R6 forbids. The positive half is in the same test so the guard cannot be
    "fixed" by refusing everything.
    """
    sha = _git(roots.code, "rev-parse", "HEAD")

    assert resolve(f"commit:{sha}", roots).ok
    assert resolve(f"commit:{sha[:7]}", roots).ok
    for expr in ("HEAD", "master", "HEAD~0", "master@{0}"):
        check = resolve(f"commit:{expr}", roots)
        assert not check.ok, f"{expr} resolved as evidence"
        assert "hex object name" in check.reason


def test_a_commit_in_either_repository_counts_and_one_in_neither_does_not(roots):
    """Mutation: check only CODE.

    The work of one session lands in two repositories — a plan in DATA, its implementation in
    CODE — and an evidence class that only knows about one of them would refuse half of the
    real completions, which trains the operator to stop attaching evidence at all.
    """
    data_sha = _git(roots.data, "rev-parse", "HEAD")
    assert data_sha != _git(roots.code, "rev-parse", "HEAD"), "the fixture stopped distinguishing the repos"

    assert resolve(f"commit:{data_sha}", roots).ok
    assert not resolve("commit:" + "d" * 40, roots).ok


# --- file: -------------------------------------------------------------------------------

def test_an_artefact_outside_the_instance_is_not_evidence(roots):
    """Mutation: drop the containment check in `_file`.

    `/etc/hosts` exists and is non-empty on every machine this will ever run on. Containment
    is what keeps `file:` a statement about work that was done here rather than a statement
    about the operating system — the same threat feedback_verify calls T6, arriving as
    evidence laundering instead of as a read oracle.
    """
    outside = roots.project.parent / "outside.txt"
    outside.write_text("not mine\n", encoding="utf-8")

    assert not resolve(f"file:{outside}", roots).ok
    assert not resolve("file:/etc/hosts", roots).ok
    assert not resolve("file:../outside.txt", roots).ok


def test_an_empty_artefact_is_refused_and_the_refusal_says_empty(roots):
    """Mutation: drop the `st_size == 0` branch, or fold it into "not found".

    A dispatched agent returning an **empty** file is this instance's measured failure mode —
    six of six agents, one session. The refusal has to name it: told "not found", the operator
    goes looking for a path that is right there, and the actual defect (the agent wrote
    nothing) stays invisible for another six runs.
    """
    (roots.data / "report.md").write_text("", encoding="utf-8")
    empty = resolve("file:report.md", roots)

    assert not empty.ok
    assert "empty" in empty.reason

    (roots.data / "report.md").write_text("findings\n", encoding="utf-8")
    assert resolve("file:report.md", roots).ok


def test_a_source_file_in_the_engine_checkout_is_not_an_artefact(roots):
    """Mutation: put `roots.code` back in `_file`'s search list.

    `file:` exists for what a dispatched agent *wrote* — a report, a research note, a returned
    analysis — and those land in the instance, never in the engine distribution. Letting it
    reach the CODE tree would make "this source file exists" an evidence class, which is the
    weakest check in the set and is already covered, better, by `commit:`: a commit is work that
    happened rather than a path that exists, and it resolves the same from any checkout because
    worktrees share one object database. A `file:` ref has no such immunity — the CODE root is
    whatever `CONCLAVE_ENGINE_ROOT` says, which in a worktree is somebody else's tree.
    """
    (roots.code / "engine.py").write_text("real source, real content\n", encoding="utf-8")

    check = resolve("file:engine.py", roots)
    assert not check.ok
    assert "commit:" in check.reason


# --- issue: ------------------------------------------------------------------------------

def test_an_issue_in_no_snapshot_is_refused_rather_than_assumed_closed(roots):
    """Mutation: treat an issue the cache does not mention as resolved.

    The gh-cache is per-advisor and label-scoped: an issue owned by somebody else is missing
    from it for a reason that has nothing to do with whether it closed. Absence is not
    evidence — the rule this instance has had to relearn every time a grep returned zero
    because it was pointed at the wrong tree.
    """
    _snapshot(roots, "sage-cto.md", number=309, state="closed", age_seconds=10)

    assert resolve("issue:309", roots).ok
    assert not resolve("issue:404", roots).ok
    assert not resolve("issue:not-a-number", roots).ok


def test_an_open_issue_and_a_snapshot_past_its_ttl_are_both_refused(roots):
    """Mutation: drop the TTL comparison, or the `state == "closed"` comparison.

    Two different lies. An open issue is simply not done. A stale snapshot is worse: an issue
    closed at capture and reopened since reads as evidence forever, so the TTL is the only
    thing bounding how long a completion record can outlive the completion. A cache consulted
    past its own declared validity is a memory of state, not a reading of it.
    """
    _snapshot(roots, "a.md", number=1, state="open", age_seconds=10)
    _snapshot(roots, "b.md", number=2, state="closed", age_seconds=3600, ttl=900)

    still_open = resolve("issue:1", roots)
    assert not still_open.ok and "not closed" in still_open.reason

    stale = resolve("issue:2", roots)
    assert not stale.ok and "ttl" in stale.reason


def test_the_newest_snapshot_wins_when_two_advisors_cached_the_same_issue(roots):
    """Mutation: take the first matching snapshot, or the alphabetically last.

    Five advisors each keep a snapshot and their refreshes are hours apart, so the same issue
    number appears in several files in several states. Reading any file but the newest reports
    a state that was true once — and would let a reopened issue keep passing as evidence from
    whichever advisor's cache went stale first.
    """
    _snapshot(roots, "keel-coo.md", number=7, state="closed", age_seconds=60)
    _snapshot(roots, "sage-cto.md", number=7, state="open", age_seconds=5)

    assert not resolve("issue:7", roots).ok


# --- predicate: --------------------------------------------------------------------------

def _index(roots: Roots, *rows: dict) -> None:
    roots.index.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_a_broken_predicate_is_refused_and_not_reported_as_merely_failing(roots):
    """Mutation: use `evaluate_predicate` instead of `classify_predicate`.

    The bool view folds `broken` into False, which loses the distinction 093 paid to learn:
    "cannot confirm" and "not done yet" are different facts. A predicate whose target file was
    renamed away reports the same red as one that is honestly unmet, and the rotted check then
    hides behind an unfinished unit for as long as nobody reads the reason.
    """
    (roots.project / "shipped.py").write_text("def checkpoint(): ...\n", encoding="utf-8")
    _index(
        roots,
        {"feedback_id": "fb-1", "item_id": "it-1",
         "verify": {"kind": "file-contains", "root": "project", "file": "shipped.py",
                    "pattern": "checkpoint"}},
        {"feedback_id": "fb-2", "item_id": "it-2",
         "verify": {"kind": "file-contains", "root": "project", "file": "gone.py",
                    "pattern": "checkpoint"}},
        {"feedback_id": "fb-3", "item_id": "it-3", "verify": None},
    )

    assert resolve("predicate:fb-1/it-1", roots).ok

    broken = resolve("predicate:fb-2/it-2", roots)
    assert not broken.ok and "broken" in broken.reason

    assert not resolve("predicate:fb-3/it-3", roots).ok
    assert not resolve("predicate:fb-9/it-9", roots).ok
    assert not resolve("predicate:no-item-id", roots).ok


# --- the class itself --------------------------------------------------------------------

def test_a_ref_naming_no_class_refuses_instead_of_being_ignored(roots):
    """Mutation: return `Check(ref, True, ...)` for anything unrecognised, or skip it.

    A typo — `commmit:`, `sha:`, a bare sha — must not become a free pass, and it must not
    silently vanish from the evidence list either: a `--done` line whose only evidence was
    dropped is a line with no evidence, and that is the diary R6 was written against.
    """
    for ref in ("", "3ffe83c", "commmit:3ffe83c", "sha:3ffe83c", "file", "predicate"):
        assert not resolve(ref, roots).ok

    checks = resolve_all(("commit:HEAD", "file:/etc/hosts"), roots)
    assert len(checks) == 2 and not any(c.ok for c in checks)

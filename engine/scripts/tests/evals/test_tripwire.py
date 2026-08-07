"""test_tripwire.py — the backstop that aborts a run the instant a watched repo changes.

Root cause this guards against (pilot2, spec 104 P0): fixtures built inside the real DATA tree let
an escaped agent reach the real CODE and DATA repos — 5 commits landed on the real master and
`.conclave/agent-memory/gh-cache/` was `rm -rf`'d. Moving fixtures out (see test_pilot_containment.py)
closes the specific hole; this is the belt-and-suspenders check that something changed a watched
repo at all, regardless of how.
"""
from __future__ import annotations

import subprocess

from evals import tripwire


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _scratch_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    (root / "a.txt").write_text("one\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "first")
    return root


def test_fingerprint_of_a_non_git_dir_is_inert(tmp_path):
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    fp = tripwire.fingerprint(plain, "X")
    assert fp.head == ""
    assert fp.status == ""
    assert tripwire.check(fp) is None


def test_check_is_none_when_nothing_changed(tmp_path):
    repo = _scratch_repo(tmp_path)
    fp = tripwire.fingerprint(repo, "CODE")
    assert tripwire.check(fp) is None


def test_check_detects_a_new_commit(tmp_path):
    repo = _scratch_repo(tmp_path)
    fp = tripwire.fingerprint(repo, "CODE")

    (repo / "b.txt").write_text("two\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "second")

    changed = tripwire.check(fp)
    assert changed is not None
    assert "CODE" in changed
    assert "HEAD changed" in changed


def test_check_detects_an_uncommitted_working_tree_change(tmp_path):
    repo = _scratch_repo(tmp_path)
    fp = tripwire.fingerprint(repo, "DATA")

    (repo / "a.txt").write_text("mutated\n", encoding="utf-8")

    changed = tripwire.check(fp)
    assert changed is not None
    assert "DATA" in changed
    assert "working tree changed" in changed


def test_check_detects_a_new_untracked_file(tmp_path):
    repo = _scratch_repo(tmp_path)
    fp = tripwire.fingerprint(repo, "DATA")

    (repo / "untracked.txt").write_text("surprise\n", encoding="utf-8")

    assert tripwire.check(fp) is not None


def test_ignore_carves_a_subtree_out_of_the_watch(tmp_path):
    """The run's own writes into its output dir (trials.jsonl, transcripts) are legitimate and
    must not trip the wire — only changes OUTSIDE the ignored subtree should."""
    repo = _scratch_repo(tmp_path)
    (repo / "eval" / "runs" / "r1").mkdir(parents=True)
    (repo / "eval" / "runs" / "r1" / ".gitkeep").write_text("", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "scaffold run dir")

    fp = tripwire.fingerprint(repo, "DATA", ignore=("eval/runs/r1",))

    (repo / "eval" / "runs" / "r1" / "trials.jsonl").write_text("{}\n", encoding="utf-8")
    assert tripwire.check(fp) is None, "a write inside the ignored run dir must not trip the wire"

    (repo / "elsewhere.txt").write_text("oops\n", encoding="utf-8")
    assert tripwire.check(fp) is not None, "a write outside the ignored dir must still trip it"


# ── DirWatch / watch_dir / check_dir — the non-git backstop over ~/.claude/projects (spec 104 P0
# hardening, 2026-07-27). Never touches the real HOME: every test below builds its own throwaway
# directory and passes it in explicitly.

def test_watch_dir_of_a_missing_dir_is_inert(tmp_path):
    missing = tmp_path / "does-not-exist-yet"
    watch = tripwire.watch_dir(missing, "CLAUDE_PROJECTS")
    assert watch.baseline == frozenset()
    assert tripwire.check_dir(watch) is None


def test_check_dir_is_none_when_nothing_new_appeared(tmp_path):
    watched = tmp_path / "projects"
    watched.mkdir()
    (watched / "existing-project").mkdir()
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS")
    assert tripwire.check_dir(watch) is None


def test_check_dir_detects_a_leaked_file(tmp_path):
    watched = tmp_path / "projects"
    watched.mkdir()
    (watched / "existing-project").mkdir()
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS")

    leaked = watched / "-a-leaked-session-transcript-dir"
    leaked.mkdir()
    (leaked / "transcript.jsonl").write_text("{}", encoding="utf-8")

    changed = tripwire.check_dir(watch)
    assert changed is not None
    assert "CLAUDE_PROJECTS" in changed
    assert "transcript.jsonl" in changed


def test_check_dir_ignores_an_empty_scaffold(tmp_path):
    """The rehearsal run (2026-07-27) aborted on trial 1 against an EMPTY `<project>/memory/`
    pair: `--no-session-persistence` stops the write, but the CLI still mkdir's the scaffold
    unconditionally. Watching entry NAMES could not tell that apart from a leaked transcript, so
    no run could start. A directory carrying no file has leaked nothing; the wire watches files."""
    watched = tmp_path / "projects"
    watched.mkdir()
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS")

    (watched / "-a-fixture-job-dir" / "memory").mkdir(parents=True)

    assert tripwire.check_dir(watch) is None


def test_check_dir_catches_the_auto_memory_write_inside_a_tolerated_scaffold(tmp_path):
    """The scaffold is tolerated; what pilot3's t04 trial put INSIDE it is not. A durable
    instruction-to-self written to `<project>/memory/MEMORY.md` is the Principle-V-shaped leak the
    file-level wire exists to catch, and tolerating empty dirs must not tolerate that."""
    watched = tmp_path / "projects"
    watched.mkdir()
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS")

    memory = watched / "-a-fixture-job-dir" / "memory"
    memory.mkdir(parents=True)
    assert tripwire.check_dir(watch) is None
    (memory / "MEMORY.md").write_text("Going forward, whenever you...", encoding="utf-8")

    changed = tripwire.check_dir(watch)
    assert changed is not None
    assert "MEMORY.md" in changed


def test_check_dir_scope_ignores_a_concurrent_session_of_the_operator(tmp_path):
    """The third rehearsal abort (2026-07-27): a parallel forge session wrote its auto-memory to
    `~/.claude/projects/-Users-ignat-code-conclave/memory/prefix-conclave-never-team.md` mid-run.
    `~/.claude/projects/` is one shared directory per machine — unlike DATA, it cannot be cloned
    away — so the watch is scoped to the project dirs this run's own fixtures produce."""
    watched = tmp_path / "projects"
    watched.mkdir()
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS", scope_token="conclave-work-abc123")

    operator = watched / "-Users-ignat-code-conclave" / "memory"
    operator.mkdir(parents=True)
    (operator / "some-note.md").write_text("the operator's own session", encoding="utf-8")

    assert tripwire.check_dir(watch) is None


def test_check_dir_scope_still_catches_this_runs_own_fixture(tmp_path):
    """Scoping must not blind the wire to what it exists for: a trial whose cwd is this run's
    fixture produces a project dir carrying the workdir token, and anything written there — a
    transcript, an auto-memory file — still aborts the run."""
    watched = tmp_path / "projects"
    watched.mkdir()
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS", scope_token="conclave-work-abc123")

    ours = watched / "-private-var-folders-T-conclave-work-abc123-job-9352708d" / "memory"
    ours.mkdir(parents=True)
    (ours / "MEMORY.md").write_text("Going forward, whenever you...", encoding="utf-8")

    changed = tripwire.check_dir(watch)
    assert changed is not None
    assert "MEMORY.md" in changed


def test_check_dir_without_a_scope_token_watches_everything(tmp_path):
    """No token means no narrowing — the CODE/DATA watches pass none and must keep full coverage."""
    watched = tmp_path / "projects"
    watched.mkdir()
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS")

    (watched / "-anything-at-all").mkdir()
    (watched / "-anything-at-all" / "leak.jsonl").write_text("{}", encoding="utf-8")

    assert tripwire.check_dir(watch) is not None


def test_sweep_tolerated_removes_the_cli_subagent_metadata_and_reports_it(tmp_path):
    """rehearsal-n2d, trial 14: a trial's agent spawned an Explore subagent and the CLI wrote
    `<session>/subagents/agent-*.meta.json` into the real projects dir, past
    --no-session-persistence. It carries orchestration metadata, not repo content, and it is the
    CLI's write rather than the agent's act — but it is still ours, so it is swept and counted
    rather than silently permitted."""
    watched = tmp_path / "projects"
    ours = watched / "-job-abc" / "704f4880" / "subagents"
    ours.mkdir(parents=True)
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS")

    meta = ours / "agent-a013f59d.meta.json"
    meta.write_text('{"agentType":"Explore"}', encoding="utf-8")

    swept = tripwire.sweep_tolerated(watch, tripwire.TOLERATED_PROJECT_WRITES)
    assert len(swept) == 1
    assert "agent-a013f59d.meta.json" in swept[0]
    assert not meta.exists()
    assert tripwire.check_dir(watch) is None


def test_sweep_tolerated_leaves_a_transcript_to_abort_the_run(tmp_path):
    """Tolerating the CLI's own metadata must not tolerate content. A transcript or an
    auto-memory write is not swept, and the wire still fires on it."""
    watched = tmp_path / "projects"
    ours = watched / "-job-abc"
    (ours / "subagents").mkdir(parents=True)
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS")

    (ours / "subagents" / "agent-x.meta.json").write_text("{}", encoding="utf-8")
    (ours / "transcript.jsonl").write_text('{"leaked":true}', encoding="utf-8")
    (ours / "memory").mkdir()
    (ours / "memory" / "MEMORY.md").write_text("Going forward...", encoding="utf-8")

    swept = tripwire.sweep_tolerated(watch, tripwire.TOLERATED_PROJECT_WRITES)
    assert len(swept) == 1
    changed = tripwire.check_dir(watch)
    assert changed is not None
    assert "MEMORY.md" in changed or "transcript.jsonl" in changed


def test_a_tool_result_spill_naming_only_fixture_paths_is_swept(tmp_path):
    """scored-001, trial 16 (2026-07-29): a t06 trial's Grep spilled 32 KB of its own output to
    `<session>/tool-results/<id>.txt` in the real projects dir, past --no-session-persistence.

    Every path in it pointed inside the fixture tempdir, so it carried nothing that was not already
    the trial's own throwaway copy. Unlike `subagents/*.meta.json` this is CONTENT, so it is not
    tolerated by name alone — see the next test."""
    watched = tmp_path / "projects"
    ours = watched / "-job-abc" / "1ffef207" / "tool-results"
    ours.mkdir(parents=True)
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS")

    spill = ours / "btzq0yimd.txt"
    spill.write_text(
        f"{tmp_path}/conclave-work-x/job-y/agents/forge.md:tools: Read, Write\n", encoding="utf-8"
    )

    swept = tripwire.sweep_tolerated(watch, tripwire.TOLERATED_PROJECT_WRITES)
    assert len(swept) == 1
    assert not spill.exists()
    assert tripwire.check_dir(watch) is None


def test_a_tool_result_spill_naming_a_real_path_outside_the_fixture_aborts_the_run(tmp_path):
    """The reason a spill is not tolerated by name: it can carry arbitrary tool output, and a trial
    that READ a real repo would land that content here. No git tripwire covers that — CODE and DATA
    are watched for mutations, and a read is not a mutation.

    Sweeping such a file would destroy the only evidence the trial reached outside its fixture. So a
    spill naming a path that exists on disk is left exactly where it is, and the run aborts."""
    watched = tmp_path / "projects"
    ours = watched / "-job-abc" / "1ffef207" / "tool-results"
    ours.mkdir(parents=True)
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS")

    # The operator's home: a path of the watched SHAPE (`/Users/<name>/...`) that resolves. Read
    # only, never written. Note what this does NOT cover, and why that is right: the fixture's own
    # tempdir (`/private/var/folders/...`) is not of this shape, so a spill quoting fixture paths —
    # the ordinary case — is swept rather than aborting every run. Real repos on this platform live
    # under the home dir, which is the channel that matters.
    spill = ours / "btzq0yimd.txt"
    spill.write_text(
        f"{__import__('pathlib').Path.home()}/code:the agent grepped something real\n",
        encoding="utf-8",
    )

    swept = tripwire.sweep_tolerated(watch, tripwire.TOLERATED_PROJECT_WRITES)
    assert swept == [], "a spill naming a real path is evidence and must not be destroyed"
    assert spill.exists()
    changed = tripwire.check_dir(watch)
    assert changed is not None
    assert "btzq0yimd.txt" in changed


def test_check_dir_of_a_dir_created_after_the_baseline_is_still_watched(tmp_path):
    """`watch_dir` on a not-yet-existing path (baseline empty) must still catch the directory
    being created and populated later in the same run — the whole point of the missing-dir case
    being inert rather than an error."""
    watched = tmp_path / "projects"
    watch = tripwire.watch_dir(watched, "CLAUDE_PROJECTS")
    assert tripwire.check_dir(watch) is None

    watched.mkdir()
    (watched / "new-session-dir").mkdir()
    (watched / "new-session-dir" / "session.jsonl").write_text("{}", encoding="utf-8")
    changed = tripwire.check_dir(watch)
    assert changed is not None
    assert "session.jsonl" in changed

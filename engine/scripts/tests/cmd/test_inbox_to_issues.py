"""tests/cmd/test_inbox_to_issues.py — port of inbox-to-gh.bats (8 cases).

Hermetic: bare tmp_path as CONCLAVE_AI_ROOT.
Fake gh binary logs calls to GH_LOG (mirrors bats stub approach).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from tests.cmd.helpers import run_engine

_SCRIPTS_DIR = Path(__file__).resolve().parents[2]

_INBOX_CONTENT = """\
# Inbox — nexus

- First item p0 — urgent thing
- [ ] Second item p1 — medium thing
- [x] Already done — ignore
- Third plain item

Some prose that is not a bullet.
"""

# Fake gh binary: records invocation to GH_LOG (mirrors bats fixture).
_FAKE_GH = """\
#!/usr/bin/env bash
printf '%s\\n' "gh $*" >>"$GH_LOG"
"""


def _setup(tmp: Path) -> tuple[Path, Path, dict]:
    """Seed inbox file, fake gh binary, env. Returns (inbox, gh_log, env)."""
    inbox = tmp / "inbox.md"
    inbox.write_text(_INBOX_CONTENT)

    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(_FAKE_GH)
    gh.chmod(0o755)

    gh_log = tmp / "gh-calls.log"
    gh_log.write_text("")

    env = {
        **os.environ,
        "CONCLAVE_AI_ROOT": str(tmp),
        "GH_LOG": str(gh_log),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
    }
    return inbox, gh_log, env


# Case 1: parses bulleted items; done items skipped.
def test_parses_bullets(tmp_path):
    inbox, gh_log, env = _setup(tmp_path)
    result = run_engine("inbox", "to-issues", "--advisor", "nexus", "--file", str(inbox), env=env)
    assert result.returncode == 0
    assert "First item" in result.stdout
    assert "Second item" in result.stdout
    assert "Third plain item" in result.stdout
    assert "Already done" not in result.stdout


# Case 2: --advisor flag labels issues advisor:<name> (always-quoted shq).
def test_advisor_label(tmp_path):
    inbox, gh_log, env = _setup(tmp_path)
    result = run_engine("inbox", "to-issues", "--advisor", "nexus", "--file", str(inbox), env=env)
    assert result.returncode == 0
    assert "--label 'advisor:nexus'" in result.stdout


# Case 3: priority markers p0/p1 detected and emitted as labels.
def test_priority_labels(tmp_path):
    inbox, gh_log, env = _setup(tmp_path)
    result = run_engine("inbox", "to-issues", "--advisor", "nexus", "--file", str(inbox), env=env)
    assert result.returncode == 0
    assert "--label 'p0'" in result.stdout
    assert "--label 'p1'" in result.stdout


# Case 3b: p0/p1 as substrings of larger tokens must NOT be detected (word-boundary guard).
def test_priority_negative(tmp_path):
    inbox = tmp_path / "inbox.md"
    inbox.write_text(
        "# Inbox — nexus\n\n"
        "- Fix the sp0t on the wall\n"
        "- Ticket p10 needs triage\n"
        "- Rename var p1x to something clearer\n"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(_FAKE_GH)
    gh.chmod(0o755)
    gh_log = tmp_path / "gh-calls.log"
    gh_log.write_text("")
    env = {
        **os.environ,
        "CONCLAVE_AI_ROOT": str(tmp_path),
        "GH_LOG": str(gh_log),
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
    }
    result = run_engine("inbox", "to-issues", "--advisor", "nexus", "--file", str(inbox), env=env)
    assert result.returncode == 0
    assert "--label 'p0'" not in result.stdout
    assert "--label 'p1'" not in result.stdout


# Case 4: --dry-run prints commands, gh seam NOT called.
def test_dry_run_prints_no_gh(tmp_path):
    inbox, gh_log, env = _setup(tmp_path)
    result = run_engine(
        "inbox", "to-issues", "--advisor", "nexus", "--file", str(inbox), "--dry-run",
        env=env,
    )
    assert result.returncode == 0
    assert "gh issue create" in result.stdout
    assert gh_log.read_text() == ""  # fake gh binary was NOT invoked


# Case 5: --execute invokes gh with issue create + advisor:nexus.
def test_execute_calls_gh(tmp_path):
    inbox, gh_log, env = _setup(tmp_path)
    result = run_engine(
        "inbox", "to-issues", "--advisor", "nexus", "--file", str(inbox), "--execute",
        env=env,
    )
    assert result.returncode == 0
    log = gh_log.read_text()
    assert "issue create" in log
    assert "advisor:nexus" in log


# Case 6: --skip-stale prompts per item; stdin n/y/y → First skipped, 2 issues.
def test_skip_stale_stdin(tmp_path):
    inbox, gh_log, env = _setup(tmp_path)
    # run_engine doesn't support stdin; use subprocess.run directly.
    result = subprocess.run(
        [
            sys.executable, "-m", "engine",
            "inbox", "to-issues",
            "--advisor", "nexus",
            "--file", str(inbox),
            "--execute",
            "--skip-stale",
        ],
        input="n\ny\ny\n",
        capture_output=True,
        text=True,
        cwd=str(_SCRIPTS_DIR),
        env=env,
    )
    assert result.returncode == 0
    log_lines = [ln for ln in gh_log.read_text().splitlines() if ln.strip()]
    assert len(log_lines) == 2
    assert not any("First item" in ln for ln in log_lines)
    assert any("Second item" in ln for ln in log_lines)
    assert any("Third plain item" in ln for ln in log_lines)


# Case 7: required args enforced (missing --advisor, missing --file → exit != 0).
def test_required_args(tmp_path):
    inbox, gh_log, env = _setup(tmp_path)
    r1 = run_engine("inbox", "to-issues", "--file", str(inbox), env=env)
    assert r1.returncode != 0
    r2 = run_engine("inbox", "to-issues", "--advisor", "nexus", env=env)
    assert r2.returncode != 0


# Case 8: engine inbox to-issues does NOT commit to git.
def test_does_not_commit(tmp_path):
    inbox, gh_log, env = _setup(tmp_path)

    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "T",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "T",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "add", "."], cwd=str(tmp_path), check=True, env=git_env)
    subprocess.run(
        ["git", "commit", "-q", "-m", "init"],
        cwd=str(tmp_path), check=True, env=git_env,
    )

    before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(tmp_path), capture_output=True, text=True, check=True,
    ).stdout.strip()

    run_engine(
        "inbox", "to-issues", "--advisor", "nexus", "--file", str(inbox), "--execute",
        env=env,
    )

    after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(tmp_path), capture_output=True, text=True, check=True,
    ).stdout.strip()

    assert before == after

"""tests/cmd/test_briefing_build.py — integration tests for `engine briefing build`.

Ports 8 briefing-build.bats cases and 2 regen-trigger.bats cases.
Uses the ai_root fixture (hermetic DATA+CODE tree; 6 canonical advisors
already seeded → registry gate is non-empty).
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.cmd.helpers import run_engine


def _seed_progress(ai_root: Path) -> None:
    """Create a minimal progress-summary.md so project-state scan has content."""
    p = ai_root / "progress-summary.md"
    if not p.exists():
        p.write_text("# Progress Summary\n\n**Phase**: P1 | **v1.0 DEPLOYED** Mar 28\n")


# ---------------------------------------------------------------------------
# Case 1 — verb registered
# ---------------------------------------------------------------------------
# NOTE: briefing-build.bats case 1 tested shim executability (`-x "$REAL_SHIM"`).
# No CLI equivalent now that the shim is deleted. Substituted with:
# `engine briefing --help` exits 0 and output includes "build" (verb is registered).

def test_briefing_verb_registered(ai_root):
    r = run_engine("briefing", "--help")
    assert r.returncode == 0
    assert "build" in r.stdout


# ---------------------------------------------------------------------------
# Case 2 — build --help exits 0 and output contains "advisor"
# ---------------------------------------------------------------------------

def test_build_help(ai_root):
    r = run_engine("briefing", "build", "--help")
    assert r.returncode == 0
    assert "advisor" in r.stdout


# ---------------------------------------------------------------------------
# Case 3 — unknown advisor → exit 1, "is not in the instance registry"
# ---------------------------------------------------------------------------
# NOTE: briefing-build.bats case 3 asserted "not canonical" (hardcoded list).
# The CURRENT briefing package prints "is not in the instance registry"
# (registry-gated via _registry_advisors()). ai_root seeds 6 canonical advisors
# → registry is non-empty → unknown advisor is rejected with the current message.

def test_unknown_advisor_exit1(ai_root):
    r = run_engine("briefing", "build", "totally-unknown-advisor")
    assert r.returncode == 1
    assert "is not in the instance registry" in r.stderr


# #52 — --advisor alias mirrors the positional form (parity with file/session CLIs)
def test_advisor_flag_alias_builds(ai_root):
    _seed_progress(ai_root)
    r = run_engine("briefing", "build", "--advisor", "kai-cto")
    assert r.returncode == 0, f"stderr: {r.stderr[:400]}"
    assert (ai_root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md").is_file()


def test_no_advisor_arg_exit2(ai_root):
    r = run_engine("briefing", "build")
    assert r.returncode == 2
    assert "advisor required" in r.stderr


# ---------------------------------------------------------------------------
# #38 — forge is a META advisor, not a domain hire
# ---------------------------------------------------------------------------
# _registry_advisors() enumerates DOMAIN advisors and strips forge as a lifecycle
# skill. Gating admission on that enumeration rejected the one advisor guaranteed
# to exist in every instance, so every forge session started on a stale briefing.
# Enumerate on the roster; gate on lifecycle membership.

def test_forge_meta_advisor_builds(ai_root):
    _seed_progress(ai_root)
    r = run_engine("briefing", "build", "forge")
    assert "is not in the instance registry" not in r.stderr
    assert r.returncode == 0, f"stderr: {r.stderr[:400]}"
    assert (ai_root / "agent-memory" / "advisors" / "briefings" / "forge.md").is_file()


def test_forge_meta_advisor_regenerates(ai_root):
    """The mutation path, not the session-init one.

    briefing.regen gates on known_advisors(), which excludes META by design, so
    `file decision` / `session close` / `mention create` / the post-commit hook all
    declined to refresh forge — and returned 0, leaving the refusal invisible.
    """
    _seed_progress(ai_root)
    scripts_dir = Path(__file__).resolve().parents[2]  # engine/scripts
    r = subprocess.run(
        [sys.executable, "-m", "briefing.regen", "forge"],
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert "skipping unknown advisor: forge" not in r.stderr
    assert r.returncode == 0, f"stderr: {r.stderr[:400]}"
    assert (ai_root / "agent-memory" / "advisors" / "briefings" / "forge.md").is_file()


# ---------------------------------------------------------------------------
# #14 — freshness is a fact, not an estimate
# ---------------------------------------------------------------------------
# session_init regenerated on an mtime guard (>24h), which is wrong in both
# directions: a 2h-old briefing counted as fresh however much its inputs had moved,
# and a 25h-old one was rebuilt even when nothing had. The build now renders, compares
# against what is on disk, and writes only on a real difference.

def test_rebuild_with_unchanged_inputs_does_not_rewrite(ai_root):
    _seed_progress(ai_root)
    path = ai_root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"

    first = run_engine("briefing", "build", "kai-cto")
    assert first.returncode == 0, f"stderr: {first.stderr[:400]}"
    assert "wrote=" in first.stdout
    mtime_before = path.stat().st_mtime_ns

    second = run_engine("briefing", "build", "kai-cto")
    assert second.returncode == 0, f"stderr: {second.stderr[:400]}"
    assert "unchanged=" in second.stdout
    assert path.stat().st_mtime_ns == mtime_before, "briefing was rewritten with no input change"
    assert not list(path.parent.glob(".briefing-tmp-*")), "no-write path left a tmp file behind"


def test_timestamp_drift_alone_is_not_a_change(ai_root):
    """generated_at is stamped into every render, so it must be excluded from the
    comparison — otherwise every build looks like a change and the fix is a no-op."""
    _seed_progress(ai_root)
    path = ai_root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"

    run_engine("briefing", "build", "kai-cto")
    mtime_before = path.stat().st_mtime_ns

    time.sleep(1.1)  # guarantee a different generated_at value

    again = run_engine("briefing", "build", "kai-cto")
    assert "unchanged=" in again.stdout
    assert path.stat().st_mtime_ns == mtime_before, "a new timestamp alone triggered a rewrite"


def test_rebuild_after_input_change_rewrites(ai_root):
    _seed_progress(ai_root)
    path = ai_root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"

    run_engine("briefing", "build", "kai-cto")
    before = path.read_text(encoding="utf-8")

    (ai_root / "progress-summary.md").write_text(
        "# Progress Summary\n\n**Phase**: P2 | **v2.0 SHIPPED** Jul 27\n", encoding="utf-8"
    )

    after_run = run_engine("briefing", "build", "kai-cto")
    assert after_run.returncode == 0, f"stderr: {after_run.stderr[:400]}"
    assert "wrote=" in after_run.stdout
    assert path.read_text(encoding="utf-8") != before, "input changed but briefing did not"


def test_unreadable_existing_briefing_is_rewritten_not_raised(ai_root):
    """The old unconditional-overwrite code never read the existing briefing, so a
    corrupt file quietly repaired itself on the next write. Build-and-compare added
    a read for the comparison — an unreadable file must still self-heal, not raise
    (which would wedge every future session start at exit 1)."""
    _seed_progress(ai_root)
    path = ai_root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")

    r = run_engine("briefing", "build", "kai-cto")
    assert r.returncode == 0, f"stderr: {r.stderr[:400]}"
    assert "wrote=" in r.stdout
    assert path.read_text(encoding="utf-8").startswith("<!-- AUTO-GENERATED")


# ---------------------------------------------------------------------------
# Cases 4–8 — successful build for kai-cto
# ---------------------------------------------------------------------------

@pytest.fixture
def kai_cto_built(ai_root):
    """Run `engine briefing build kai-cto` once; return (result, briefing_path)."""
    _seed_progress(ai_root)
    r = run_engine("briefing", "build", "kai-cto")
    briefing_path = ai_root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"
    return r, briefing_path


# Case 4: exits 0 and writes briefing file
def test_build_kai_cto_exit0(kai_cto_built):
    r, path = kai_cto_built
    assert r.returncode == 0, f"stderr: {r.stderr[:400]}"
    assert path.is_file()


# Case 5: briefing contains expected H2 section headers
def test_briefing_section_headers(kai_cto_built):
    _, path = kai_cto_built
    content = path.read_text()
    for header in (
        "## Who I am",
        "## Project state",
        "## My open queue",
        "## Last sessions",
        "## Mentions",
    ):
        assert header in content, f"missing header: {header!r}"


# Case 6: stdout emits [briefing-build] step and wrote lines
def test_stdout_step_lines(kai_cto_built):
    r, _ = kai_cto_built
    assert "[briefing-build] step=who-i-am" in r.stdout
    assert "[briefing-build] step=render" in r.stdout
    assert "[briefing-build] wrote=" in r.stdout


# Case 7: wrote= line contains advisor filename
def test_wrote_contains_filename(kai_cto_built):
    r, _ = kai_cto_built
    assert "kai-cto.md" in r.stdout


# Case 8: build does NOT commit (git HEAD unchanged)
def test_no_commit(ai_root):
    _seed_progress(ai_root)
    subprocess.run(["git", "init", "-q"], cwd=str(ai_root), check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=str(ai_root), check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=str(ai_root), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(ai_root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(ai_root), check=True)
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(ai_root),
        capture_output=True, text=True, check=True,
    ).stdout.strip()

    run_engine("briefing", "build", "kai-cto")

    head_after = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(ai_root),
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert head_before == head_after


# ---------------------------------------------------------------------------
# Case 9 — AC6: file decision triggers briefing regen (mtime advances)
# ---------------------------------------------------------------------------

def test_file_decision_triggers_regen(ai_root, tmp_path):
    _seed_progress(ai_root)

    # Seed initial briefing (mtime baseline).
    briefing_path = ai_root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"
    briefing_path.write_text("# kai-cto briefing\n\n(initial)\n")
    before_mtime = briefing_path.stat().st_mtime

    # Ensure at least 1-second mtime granularity.
    time.sleep(1)

    body = tmp_path / "body.md"
    body.write_text("Move to base network for lower fees.\n")

    # engine file decision calls regen_advisor in-process (briefing.main).
    r = run_engine(
        "file", "decision",
        "--slug", "move-to-base",
        "--by", "kai-cto",
        "--date", "2026-05-21",
        "--body-file", str(body),
    )
    assert r.returncode == 0, f"file decision failed: {r.stderr[:400]}"

    dec_path = (
        ai_root / "agent-memory" / "advisors" / "decisions"
        / "2026-05-21-kai-cto-move-to-base.md"
    )
    assert dec_path.is_file(), "decision file was not created"

    after_mtime = briefing_path.stat().st_mtime
    assert after_mtime > before_mtime, (
        "briefing mtime did not advance after file decision — regen did not run"
    )


# ---------------------------------------------------------------------------
# Case 10 — regen.py importable: --from-commit with empty stdin exits 0
# ---------------------------------------------------------------------------

def test_regen_module_importable():
    """Smoke: briefing.regen --from-commit with empty stdin exits 0 (no paths touched)."""
    scripts_dir = Path(__file__).resolve().parents[2]  # engine/scripts
    r = subprocess.run(
        [sys.executable, "-m", "briefing.regen", "--from-commit"],
        input="",
        capture_output=True,
        text=True,
        cwd=str(scripts_dir),
    )
    assert r.returncode == 0, f"stderr: {r.stderr}"


# ---------------------------------------------------------------------------
# team-digest smoke tests (adapter for briefing team_digest.py)
# ---------------------------------------------------------------------------

def test_team_digest_no_args(ai_root):
    """engine briefing team-digest (no args) → exit 0, _team.md exists, AUTO-GENERATED header."""
    r = run_engine("briefing", "team-digest")
    assert r.returncode == 0, f"stderr: {r.stderr[:400]}"
    team_md = ai_root / "agent-memory" / "advisors" / "briefings" / "_team.md"
    assert team_md.is_file(), "_team.md was not created"
    content = team_md.read_text()
    assert "AUTO-GENERATED" in content


def test_team_digest_single_advisor(ai_root):
    """engine briefing team-digest kai-cto → exit 0 (single-advisor path)."""
    r = run_engine("briefing", "team-digest", "kai-cto")
    assert r.returncode == 0, f"stderr: {r.stderr[:400]}"


def test_team_digest_unknown_advisor_exit1(ai_root):
    """engine briefing team-digest totally-unknown → exit 1, 'unknown advisor' in stderr."""
    r = run_engine("briefing", "team-digest", "totally-unknown")
    assert r.returncode == 1
    assert "unknown advisor" in r.stderr

"""tests/cmd/test_session_close.py — integration tests for `engine session close`
and `engine session emission-gate`.

Ports:
  - 10 cases from engine/scripts/tests/close-session.bats
  - 2 cases from engine/scripts/tests/team-done-emission-gate.bats

STALE-BATS TRAP #1: bats seeds decisions as {date}-{slug}.md (no advisor token).
  close-session.sh (and close_session()) checks {date}-{advisor}-{slug}.md.
  Tests here seed the CORRECT advisor-tokened name.

STALE-BATS TRAP #2: bats asserts handoff at {date}-{slug}.md (no from-token).
  file_handoff() writes {date}-{from}-{slug}.md. Tests assert the correct name.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from enginelib.frontmatter import fm_get
from enginelib.paths import decisions_dir, handoffs_dir, mentions_dir, sessions_dir
from tests.cmd.helpers import run_engine

_DATE = "2026-04-22"
_ADVISOR = "nexus-ceo"


def _write_body(tmp_path: Path, text: str = "Outcome body.\n") -> Path:
    body = tmp_path / "session-body.md"
    body.write_text(text)
    return body


def _run_close(body: Path, **kwargs) -> subprocess.CompletedProcess:
    """Call `engine session close` with default advisor/slug/date plus any extra kwargs."""
    args = [
        "session", "close",
        "--advisor", _ADVISOR,
        "--slug", "vid-review",
        "--date", _DATE,
        "--body-file", str(body),
    ]
    for k, v in kwargs.items():
        args += [f"--{k.replace('_', '-')}", str(v)]
    return run_engine(*args)


# 1. Creates sessions/{date}-{advisor}-{slug}.md, exit 0
def test_creates_session_file(seed_advisors, tmp_path):
    seed_advisors(_ADVISOR, "spark-cmo")
    body = _write_body(tmp_path)
    r = _run_close(body)
    assert r.returncode == 0, r.stderr
    assert (sessions_dir() / f"{_DATE}-{_ADVISOR}-vid-review.md").is_file()


# 2. Frontmatter captures advisor/date/slug
def test_frontmatter_advisor_date_slug(seed_advisors, tmp_path):
    seed_advisors(_ADVISOR, "spark-cmo")
    body = _write_body(tmp_path)
    r = _run_close(body)
    assert r.returncode == 0, r.stderr
    f = sessions_dir() / f"{_DATE}-{_ADVISOR}-vid-review.md"
    assert fm_get(f, "advisor") == _ADVISOR
    assert fm_get(f, "date") == _DATE
    assert fm_get(f, "slug") == "vid-review"


# 3. --decisions populates frontmatter
# STALE-BATS TRAP #1: seed at {date}-{advisor}-{slug}.md (NOT {date}-{slug}.md)
def test_decisions_populate_frontmatter(seed_advisors, tmp_path):
    seed_advisors(_ADVISOR, "spark-cmo")
    body = _write_body(tmp_path)
    # Seed with advisor token (correct — STALE-BATS TRAP #1)
    for slug in ("move-to-base", "pause-ads"):
        df = decisions_dir() / f"{_DATE}-{_ADVISOR}-{slug}.md"
        df.parent.mkdir(parents=True, exist_ok=True)
        df.write_text(f"---\nslug: {slug}\ndate: {_DATE}\nstatus: active\n---\n\nBody.\n")
    r = _run_close(body, decisions="move-to-base,pause-ads")
    assert r.returncode == 0, r.stderr
    f = sessions_dir() / f"{_DATE}-{_ADVISOR}-vid-review.md"
    val = fm_get(f, "decisions") or ""
    assert "move-to-base" in val
    assert "pause-ads" in val


# 4. --issues-touched populates frontmatter
def test_issues_touched_populate_frontmatter(seed_advisors, tmp_path):
    seed_advisors(_ADVISOR, "spark-cmo")
    body = _write_body(tmp_path)
    r = _run_close(body, issues_touched="AI#58,AI#61")
    assert r.returncode == 0, r.stderr
    f = sessions_dir() / f"{_DATE}-{_ADVISOR}-vid-review.md"
    val = fm_get(f, "issues") or ""
    assert "AI#58" in val
    assert "AI#61" in val


# 5. --resolves-mentions moves mention open→archive; captured in session frontmatter
def test_resolves_mentions(seed_advisors, tmp_path):
    seed_advisors(_ADVISOR, "spark-cmo")
    # Create an open mention via the engine CLI
    mb = tmp_path / "mention-body.md"
    mb.write_text("deck review\n")
    r_create = run_engine(
        "mention", "create",
        "--from", "spark-cmo",
        "--to", _ADVISOR,
        "--body-file", str(mb),
        "--now", "2026-04-22T16:30:00-03:00",
    )
    assert r_create.returncode == 0, r_create.stderr
    mid = r_create.stdout.strip()
    assert mid, "mention create should print the mention id to stdout"

    # Sanity: open file exists
    assert (mentions_dir() / _ADVISOR / "open" / f"{mid}.md").is_file()

    body = _write_body(tmp_path)
    r = _run_close(body, resolves_mentions=mid)
    assert r.returncode == 0, r.stderr

    # Mention moved open → archive
    assert not (mentions_dir() / _ADVISOR / "open" / f"{mid}.md").exists()
    assert (mentions_dir() / _ADVISOR / "archive" / f"{mid}.md").is_file()

    # Session frontmatter captures resolved mention id
    f = sessions_dir() / f"{_DATE}-{_ADVISOR}-vid-review.md"
    assert mid in (fm_get(f, "mentions_resolved") or "")


# 6. --handoff-file files a handoff; session frontmatter records bare handoff slug
# STALE-BATS TRAP #2: bats asserts {date}-{slug}.md; file_handoff writes {date}-{from}-{slug}.md
def test_handoff_file_creates_handoff(seed_advisors, tmp_path):
    seed_advisors(_ADVISOR, "spark-cmo")
    hb = tmp_path / "handoff-body.md"
    hb.write_text("Handoff body text.\n")
    body = _write_body(tmp_path)
    r = _run_close(
        body,
        handoff_file=str(hb),
        handoff_to="spark-cmo",
        handoff_title="Pick up next week",
        handoff_slug="pick-up-next-week",
        handoff_priority="p2",
    )
    assert r.returncode == 0, r.stderr
    # STALE-BATS TRAP #2: correct filename includes from-token
    assert (handoffs_dir() / f"{_DATE}-{_ADVISOR}-pick-up-next-week.md").is_file()
    # Session frontmatter records bare slug (not filename)
    f = sessions_dir() / f"{_DATE}-{_ADVISOR}-vid-review.md"
    assert fm_get(f, "handoff") == "pick-up-next-week"


# 7. Unknown decision slug → exit != 0, "ghost-slug" or "not found" in stderr
def test_unknown_decision_errors(seed_advisors, tmp_path):
    seed_advisors(_ADVISOR, "spark-cmo")
    body = _write_body(tmp_path)
    r = _run_close(body, decisions="ghost-slug")
    assert r.returncode != 0
    assert "ghost-slug" in r.stderr or "not found" in r.stderr


# 8. Idempotent: run twice → exactly one session file
def test_idempotent(seed_advisors, tmp_path):
    seed_advisors(_ADVISOR, "spark-cmo")
    body = _write_body(tmp_path)
    _run_close(body)
    _run_close(body)
    count = len(list(sessions_dir().glob("*.md")))
    assert count == 1


# 9. Does NOT commit: session file written but git shows it as untracked (not committed)
def test_does_not_commit(seed_advisors, tmp_path):
    seed_advisors(_ADVISOR, "spark-cmo")
    ai = Path(os.environ["CONCLAVE_AI_ROOT"])
    # Establish a clean git baseline
    subprocess.run(["git", "init", "-q"], cwd=ai, check=True)
    subprocess.run(["git", "add", "-A"], cwd=ai, check=True)
    subprocess.run(
        ["git", "-c", "user.email=test@test.com", "-c", "user.name=Test",
         "commit", "-q", "-m", "init"],
        cwd=ai, check=True,
    )
    body = _write_body(tmp_path)
    r = _run_close(body)
    assert r.returncode == 0, r.stderr
    # Session file should appear as untracked — close_session never commits
    result = subprocess.run(
        ["git", "status", "--short"], cwd=ai, capture_output=True, text=True, check=True,
    )
    assert len(result.stdout.strip()) > 0, "expected untracked session file; git shows clean"


# 10. Required args enforced: missing slug/date/body-file → exit != 0, "required" in stderr
def test_required_args_enforced(seed_advisors, tmp_path):
    seed_advisors(_ADVISOR, "spark-cmo")
    r = run_engine("session", "close", "--advisor", "kai-cto")
    assert r.returncode != 0
    assert "required" in r.stderr


# --- Emission gate tests (ported from team-done-emission-gate.bats) ---

# 11. Gate BLOCKS when no emission file exists
def test_emission_gate_blocks_when_no_emission(tmp_path):
    bare_root = tmp_path / "ai"
    (bare_root / "ops" / "feedback").mkdir(parents=True)
    env = {
        "CONCLAVE_AI_ROOT": str(bare_root),
        "ADVISOR_NAME": "atlas",
        "SESSION_ID": "test-session-001",
        "TODAY": "2026-05-25",
    }
    r = run_engine("session", "emission-gate", env=env)
    assert r.returncode != 0
    combined = r.stdout + r.stderr
    assert "Missing or draft" in combined or "conclave:feedback" in combined


# 12. Gate PASSES when emission file exists with _draft: false
def test_emission_gate_passes_when_emission_present(tmp_path):
    bare_root = tmp_path / "ai"
    emission_dir = bare_root / "ops" / "feedback" / "2026-05-25"
    emission_dir.mkdir(parents=True)
    (emission_dir / "atlas-test-session-001.md").write_text(
        "---\n_draft: false\nsummary: test\n---\n"
    )
    env = {
        "CONCLAVE_AI_ROOT": str(bare_root),
        "ADVISOR_NAME": "atlas",
        "SESSION_ID": "test-session-001",
        "TODAY": "2026-05-25",
    }
    r = run_engine("session", "emission-gate", env=env)
    assert r.returncode == 0, r.stderr

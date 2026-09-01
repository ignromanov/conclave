"""tests/cmd/test_lifecycle_runlog_summary.py — integration tests for `engine lifecycle runlog-summary`.

Hermetic: bare tmp_path (NOT ai_root). Uses CONCLAVE_AI_ROOT env seam.
Port of engine/scripts/tests/lifecycle/runlog-summary.bats (5 cases).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from tests.cmd.helpers import run_engine


def _today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _log_file(tmp: Path) -> Path:
    return tmp / "agent-memory" / "run-log" / f"{_today()}.jsonl"


def _row(log: Path, script: str, exit_code: int, advisor: str) -> None:
    """Append one JSONL row to the run-log."""
    log.parent.mkdir(parents=True, exist_ok=True)
    today = _today()
    entry = {
        "ts": f"{today}T00:00:00Z",
        "script": script,
        "args_hash": "x",
        "exit_code": exit_code,
        "duration_ms": 10,
        "advisor": advisor,
    }
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def _env(tmp: Path) -> dict:
    return {"CONCLAVE_AI_ROOT": str(tmp)}


# ---------------------------------------------------------------------------
# 1. Missing log → zero-state, green.
# ---------------------------------------------------------------------------
def test_missing_log_yields_green_zero_state(tmp_path):
    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 0
    assert "🟢" in r.stdout
    assert "0 errors" in r.stdout


# ---------------------------------------------------------------------------
# 2. All exit 0 → green, 0 errors.
# ---------------------------------------------------------------------------
def test_all_exit_0_yields_green_0_errors(tmp_path):
    log = _log_file(tmp_path)
    _row(log, "mention.sh", 0, "kai-cto")
    _row(log, "file-decision.sh", 0, "kai-cto")

    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 0
    assert "🟢" in r.stdout
    assert "2 scripts" in r.stdout
    assert "0 errors" in r.stdout


# ---------------------------------------------------------------------------
# 3. exit 2 (refresh) is not an error — F1 regression guard.
# ---------------------------------------------------------------------------
def test_exit_2_refresh_is_not_an_error(tmp_path):
    log = _log_file(tmp_path)
    _row(log, "gh-fetch.sh", 2, "kai-cto")
    _row(log, "git-fetch.sh", 2, "kai-cto")

    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 0
    assert "🟢" in r.stdout
    assert "0 errors" in r.stdout


# ---------------------------------------------------------------------------
# 4. exit 1 counts; co-located exit 2 stays excluded.
# ---------------------------------------------------------------------------
def test_exit_1_counts_exit_2_alongside_does_not(tmp_path):
    log = _log_file(tmp_path)
    _row(log, "gh-fetch.sh", 2, "kai-cto")
    _row(log, "mention.sh", 1, "kai-cto")

    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 0
    assert "🟡" in r.stdout
    assert "1 errors" in r.stdout


# ---------------------------------------------------------------------------
# 5. P0 script exit 2 does NOT trip red.
# ---------------------------------------------------------------------------
def test_p0_script_exit_2_does_not_trip_red(tmp_path):
    log = _log_file(tmp_path)
    _row(log, "engine briefing briefing-build", 2, "kai-cto")

    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 0
    assert "🟢" in r.stdout
    assert "0 errors" in r.stdout


# ---------------------------------------------------------------------------
# 6. P0 script exit 1 DOES trip red (regression guard for _P0_RE match).
# ---------------------------------------------------------------------------
def test_p0_script_exit_1_trips_red(tmp_path):
    log = _log_file(tmp_path)
    _row(log, "engine file file-decision", 1, "kai-cto")

    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 0
    assert "🔴" in r.stdout
    assert "1 errors" in r.stdout


# ---------------------------------------------------------------------------
# 7. Non-P0 engine command exit 1 yields yellow, NOT red.
# ---------------------------------------------------------------------------
def test_non_p0_engine_command_exit_1_yields_yellow_not_red(tmp_path):
    log = _log_file(tmp_path)
    _row(log, "engine memory memory-index", 1, "kai-cto")

    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 0
    assert "🟡" in r.stdout
    assert "🔴" not in r.stdout
    assert "1 errors" in r.stdout


# ---------------------------------------------------------------------------
# 8. A failure row names WHICH script failed and with what exit code (GH#186).
#
# The Infra row is the operator's only view of a lifecycle failure: the adapter
# exits 0 by design (it succeeded at reporting), so severity alone left them with
# "something went wrong" and nothing to act on. commands/done.md has promised
# `{first_failing_script} exit={code}` since the row was specified.
# ---------------------------------------------------------------------------
def test_failure_row_names_the_first_failing_script_and_its_exit_code(tmp_path):
    log = _log_file(tmp_path)
    _row(log, "engine lifecycle gh-fetch", 2, "kai-cto")       # refresh — a success
    _row(log, "engine memory memory-index", 1, "kai-cto")      # the FIRST real failure
    _row(log, "engine mention mention-create", 3, "kai-cto")   # a later one

    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 0
    assert "engine memory memory-index exit=1" in r.stdout
    # exit 2 is a success (ADR-0003): naming it would send the operator after a healthy script.
    assert "gh-fetch" not in r.stdout


def test_failure_row_of_a_p0_script_names_it_too(tmp_path):
    log = _log_file(tmp_path)
    _row(log, "engine file file-decision", 1, "kai-cto")

    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert "🔴" in r.stdout
    assert "engine file file-decision exit=1" in r.stdout


def test_clean_row_names_no_script(tmp_path):
    """Nothing failed, so there is no name to give — the row must not invent one."""
    log = _log_file(tmp_path)
    _row(log, "engine lifecycle gh-fetch", 0, "kai-cto")
    _row(log, "engine lifecycle git-fetch", 2, "kai-cto")

    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert "🟢" in r.stdout
    assert "exit=" not in r.stdout


def test_another_advisors_failure_is_not_reported_as_mine(tmp_path):
    """`mine` filters by advisor; the named script must come from the same filtered set."""
    log = _log_file(tmp_path)
    _row(log, "engine memory memory-index", 1, "someone-else")
    _row(log, "engine lifecycle gh-fetch", 0, "kai-cto")

    r = run_engine("lifecycle", "runlog-summary", "--advisor", "kai-cto", env=_env(tmp_path))
    assert "🟢" in r.stdout
    assert "memory-index" not in r.stdout

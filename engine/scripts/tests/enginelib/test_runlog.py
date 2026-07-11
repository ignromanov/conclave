"""test_runlog.py — port of tests/lib/run-log.bats (4 cases)."""
import datetime
import json
import shutil
import threading
from pathlib import Path

from enginelib import runlog


def _today() -> str:
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")


def _log_file(tmp_path: Path) -> Path:
    return tmp_path / "agent-memory" / "run-log" / f"{_today()}.jsonl"


def _is_valid_json(line: str) -> bool:
    try:
        json.loads(line)
        return True
    except json.JSONDecodeError:
        return False


# ---------------------------------------------------------------------------
# 1. Single append: produces daily JSONL file with exactly one valid JSON row
# ---------------------------------------------------------------------------

def test_run_log_append_single_row(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))

    runlog.run_log_append("my-script", "abc123", 0, 42, "kai-cto")

    log_file = _log_file(tmp_path)
    assert log_file.is_file()

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    row = json.loads(lines[0])
    assert isinstance(row, dict)


# ---------------------------------------------------------------------------
# 2. Concurrent appends: 10 parallel calls produce 10 intact rows (no corruption)
# ---------------------------------------------------------------------------

def test_run_log_append_concurrent(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))

    threads = [
        threading.Thread(
            target=runlog.run_log_append,
            args=(f"script-{i}", f"hash{i}", 0, i * 10, "kai-cto"),
        )
        for i in range(1, 11)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    log_file = _log_file(tmp_path)
    assert log_file.is_file()

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 10

    bad = [line for line in lines if not _is_valid_json(line)]
    assert bad == []


# ---------------------------------------------------------------------------
# 3. Key set is exact: sorted keys == [advisor, args_hash, duration_ms,
#    exit_code, script, ts] — no extras, no missing
# ---------------------------------------------------------------------------

def test_run_log_append_key_set(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))

    runlog.run_log_append("check-keys", "deadbeef", 0, 99, "nexus-ceo")

    log_file = _log_file(tmp_path)
    first_line = log_file.read_text(encoding="utf-8").splitlines()[0]
    row = json.loads(first_line)

    assert sorted(row.keys()) == ["advisor", "args_hash", "duration_ms", "exit_code", "script", "ts"]


# ---------------------------------------------------------------------------
# 4. Auto-creates daily file + parent directory from scratch
# ---------------------------------------------------------------------------

def test_run_log_append_auto_creates_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))

    log_dir = tmp_path / "agent-memory" / "run-log"
    if log_dir.exists():
        shutil.rmtree(log_dir)

    runlog.run_log_append("autocreate-test", "000", 1, 7, "quorum")

    log_file = _log_file(tmp_path)
    assert log_dir.is_dir()
    assert log_file.is_file()

    lines = log_file.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


# ---------------------------------------------------------------------------
# 5. CONCLAVE_RUN_LOG_DIR override wins over CONCLAVE_AI_ROOT — lets the test
#    harness contain run-log writes to tmp instead of the real repo (#53).
# ---------------------------------------------------------------------------

def test_run_log_dir_honors_env_override(tmp_path, monkeypatch):
    from enginelib.paths import run_log_dir

    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path / "aidata"))
    monkeypatch.setenv("CONCLAVE_RUN_LOG_DIR", str(tmp_path / "override"))
    assert run_log_dir() == tmp_path / "override"


def test_run_log_write_contained_by_override(tmp_path, monkeypatch):
    # A write with the override set must land in the override dir and NOT under
    # the CONCLAVE_AI_ROOT tree — proves test writes never reach production.
    ai_root = tmp_path / "aidata"
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(ai_root))
    monkeypatch.setenv("CONCLAVE_RUN_LOG_DIR", str(tmp_path / "override"))

    runlog.run_log_append("contained", "h", 0, 1, "shared")

    assert (tmp_path / "override" / f"{_today()}.jsonl").is_file()
    assert not (ai_root / "agent-memory" / "run-log").exists()

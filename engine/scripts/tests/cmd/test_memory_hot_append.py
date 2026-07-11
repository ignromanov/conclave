"""tests/cmd/test_memory_hot_append.py — integration tests for `engine memory hot-append`.

Ports all 7 cases from engine/scripts/tests/hot-md-append.bats.

Uses bare tmp_path as CONCLAVE_AI_ROOT (no advisors needed).
hot = tmp_path/"agent-memory"/"hot.md"  (≡ hot_md_path() under that env).

Per-test LOCK_DIR = tmp_path/"locks" keeps the lock hermetic under pytest-xdist.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from tests.cmd.helpers import run_engine

# helpers.py → tests/cmd/ → tests/ → scripts/
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]


def _env(tmp_path: Path) -> dict:
    return {
        "CONCLAVE_AI_ROOT": str(tmp_path),
        "LOCK_DIR": str(tmp_path / "locks"),
    }


def _hot(tmp_path: Path) -> Path:
    return tmp_path / "agent-memory" / "hot.md"


def _init(tmp_path: Path) -> None:
    run_engine("memory", "hot-init", env=_env(tmp_path))


# 1. Appends to specified section, exit 0, line present in hot.md
def test_appends_to_section(tmp_path):
    _init(tmp_path)
    env = _env(tmp_path)
    r = run_engine(
        "memory", "hot-append",
        "--section", "now",
        "--advisor", "kai",
        "--line", "spec 070 implementation kicked off",
        env=env,
    )
    assert r.returncode == 0, r.stderr
    assert "spec 070 implementation kicked off" in _hot(tmp_path).read_text()


# 2. Rejects invalid section → non-zero exit
def test_rejects_invalid_section(tmp_path):
    _init(tmp_path)
    r = run_engine(
        "memory", "hot-append",
        "--section", "invalid",
        "--advisor", "kai",
        "--line", "test",
        env=_env(tmp_path),
    )
    assert r.returncode != 0


# 3. Updates Last updated timestamp with advisor name
def test_updates_last_updated(tmp_path):
    _init(tmp_path)
    r = run_engine(
        "memory", "hot-append",
        "--section", "now",
        "--advisor", "kai-cto",
        "--line", "test entry",
        env=_env(tmp_path),
    )
    assert r.returncode == 0, r.stderr
    content = _hot(tmp_path).read_text()
    assert re.search(
        r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}.* by kai-cto$",
        content,
        re.MULTILINE,
    ), f"Last updated line not found in:\n{content}"


# 4. Triggers compaction when size > 500 words
def test_compaction_when_size_exceeds_cap(tmp_path):
    _init(tmp_path)
    env = _env(tmp_path)
    for i in range(1, 81):
        r = run_engine(
            "memory", "hot-append",
            "--section", "recent-decisions",
            "--advisor", "kai",
            "--line", f"filler entry {i} with enough words to bloat the file consistently and reliably",
            env=env,
        )
        assert r.returncode == 0, f"append {i} failed: {r.stderr}"
    word_count = len(_hot(tmp_path).read_text().split())
    assert word_count <= 500, f"word count {word_count} exceeds 500"


# 5. Concurrent writes — all 5 land (lock guarantees no dropped writes)
def test_concurrent_writes(tmp_path):
    _init(tmp_path)
    full_env = {**os.environ, **_env(tmp_path)}
    procs = []
    for i in range(1, 6):
        p = subprocess.Popen(
            [
                sys.executable, "-m", "engine",
                "memory", "hot-append",
                "--section", "now",
                "--advisor", "kai",
                "--line", f"concurrent {i}",
            ],
            cwd=str(_SCRIPTS_DIR),
            env=full_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        procs.append(p)
    for p in procs:
        p.wait()
    content = _hot(tmp_path).read_text()
    for i in range(1, 6):
        assert f"concurrent {i}" in content, f"missing write: concurrent {i}\n{content}"


# 6. Section header missing → non-zero exit (no corrupted write)
def test_section_header_missing(tmp_path):
    _init(tmp_path)
    hot = _hot(tmp_path)
    # Remove the ## Watch header line
    lines = [ln for ln in hot.read_text().splitlines() if ln != "## Watch"]
    hot.write_text("\n".join(lines) + "\n")
    r = run_engine(
        "memory", "hot-append",
        "--section", "watch",
        "--advisor", "kai",
        "--line", "something",
        env=_env(tmp_path),
    )
    assert r.returncode != 0


# 7. Special shell characters stored verbatim
def test_special_shell_chars_verbatim(tmp_path):
    _init(tmp_path)
    special = 'value with "quotes" `backticks` and $VARIABLE'
    r = run_engine(
        "memory", "hot-append",
        "--section", "now",
        "--advisor", "kai",
        "--line", special,
        env=_env(tmp_path),
    )
    assert r.returncode == 0, r.stderr
    assert special in _hot(tmp_path).read_text()

"""tests/cmd/test_memory_hot_init.py — integration tests for `engine memory hot-init`.

Ports all 5 cases from engine/scripts/tests/hot-md-init.bats.

Uses bare tmp_path as CONCLAVE_AI_ROOT (no advisors needed).
hot = tmp_path/"agent-memory"/"hot.md"  (≡ hot_md_path() under that env).
"""
from __future__ import annotations

import os

from tests.cmd.helpers import run_engine


# 1. Creates hot.md with required sections, exit 0
def test_creates_hot_md_with_required_sections(tmp_path):
    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
    r = run_engine("memory", "hot-init", env=env)
    assert r.returncode == 0, r.stderr
    hot = tmp_path / "agent-memory" / "hot.md"
    assert hot.is_file()
    lines = hot.read_text().splitlines()
    assert any(ln.startswith("## Now") for ln in lines)
    assert any(ln.startswith("## Open threads") for ln in lines)
    assert any(ln.startswith("## Recent decisions") for ln in lines)
    assert any(ln.startswith("## Watch") for ln in lines)
    assert any(ln.startswith("## Last updated") for ln in lines)


# 2. Idempotent: second run without --force preserves canary
def test_idempotent_does_not_clobber(tmp_path):
    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
    hot = tmp_path / "agent-memory" / "hot.md"
    run_engine("memory", "hot-init", env=env)
    with hot.open("a") as f:
        f.write("__TEST_CANARY_42__\n")
    r = run_engine("memory", "hot-init", env=env)
    assert r.returncode == 0, r.stderr
    assert "__TEST_CANARY_42__" in hot.read_text()


# 3. --force overwrites existing; canary gone
def test_force_overwrites_existing(tmp_path):
    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
    hot = tmp_path / "agent-memory" / "hot.md"
    run_engine("memory", "hot-init", env=env)
    with hot.open("a") as f:
        f.write("__TEST_CANARY_42__\n")
    r = run_engine("memory", "hot-init", "--force", env=env)
    assert r.returncode == 0, r.stderr
    assert "__TEST_CANARY_42__" not in hot.read_text()


# 4. No --force on existing → exit 0, content byte-identical
def test_no_force_on_existing_byte_identical(tmp_path):
    env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
    hot = tmp_path / "agent-memory" / "hot.md"
    run_engine("memory", "hot-init", env=env)
    before = hot.read_bytes()
    r = run_engine("memory", "hot-init", env=env)
    assert r.returncode == 0, r.stderr
    assert hot.read_bytes() == before


# 5. Unwritable parent dir → non-zero exit
def test_unwritable_dir_nonzero_exit(tmp_path):
    locked_dir = tmp_path / "agent-memory"
    locked_dir.mkdir(parents=True)
    os.chmod(locked_dir, 0o500)
    try:
        env = {"CONCLAVE_AI_ROOT": str(tmp_path)}
        r = run_engine("memory", "hot-init", env=env)
        assert r.returncode != 0
    finally:
        os.chmod(locked_dir, 0o700)

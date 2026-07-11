"""tests/cmd/test_register_executor.py — integration tests for `engine register executor`.

Ports the 10 register-executor.bats cases. Uses the conftest ai_root fixture
so executor-agent.md / color-palette.md are present and
plugin_agents_dir()/repo_root() resolve into the fixture tree.

#68 create-path reconcile: the scaffolder emits an `agents/exec-<name>-<role>.md`
agent-def (the form the live roster actually uses), NOT a `skills/exec.<name>-<role>/`
skill-dir. Memory lives at `agent-memory/executors/<name>-<role>/` (bare `<name>-<role>`,
no `exec.` prefix — the parent dir already says "executors"). See test_executor_defs.py
for the naming-standard the hand-authored defs share.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from tests.cmd.helpers import run_engine


def _agents_dir() -> Path:
    """Plugin-shipped agent-def dir = engine_root().parent/agents (mirrors paths.plugin_agents_dir)."""
    return Path(os.environ["CONCLAVE_ENGINE_ROOT"]).parent / "agents"


# ---------------------------------------------------------------------------
# 1. Missing --chosen-name → exit ≠ 0, "chosen-name" in stderr
# ---------------------------------------------------------------------------
def test_missing_chosen_name(ai_root):
    r = run_engine("register", "executor", "--role", "dev", "--emoji", "🦊", "--color", "teal")
    assert r.returncode != 0
    assert "chosen-name" in r.stderr


# ---------------------------------------------------------------------------
# 2. Emoji collision (reserved 🔷) → exit ≠ 0, "collision" or "reserved"
# ---------------------------------------------------------------------------
def test_emoji_collision_reserved(ai_root):
    r = run_engine(
        "register", "executor",
        "--chosen-name", "atlas", "--role", "dev", "--emoji", "🔷", "--color", "teal",
    )
    assert r.returncode != 0
    assert "collision" in r.stderr or "reserved" in r.stderr


# ---------------------------------------------------------------------------
# 3. Invalid role (banana) → exit ≠ 0, "role" in stderr
# ---------------------------------------------------------------------------
def test_invalid_role(ai_root):
    r = run_engine(
        "register", "executor",
        "--chosen-name", "atlas", "--role", "banana", "--emoji", "🦊", "--color", "teal",
    )
    assert r.returncode != 0
    assert "role" in r.stderr


# ---------------------------------------------------------------------------
# 4. Happy path → exit 0; agents/exec-atlas-dev.md agent-def + MEMORY.md exist;
#    NO skill-dir, inline voice (no separate personality.md reference)
# ---------------------------------------------------------------------------
def test_happy_path(ai_root):
    engine_root = Path(os.environ["CONCLAVE_ENGINE_ROOT"])
    r = run_engine(
        "register", "executor",
        "--chosen-name", "atlas", "--role", "dev",
        "--emoji", "🦊", "--color", "teal", "--wraps", "team-implementer",
    )
    assert r.returncode == 0
    agent_def = _agents_dir() / "exec-atlas-dev.md"
    assert agent_def.exists(), "create-path must emit agents/exec-<name>-<role>.md"
    assert (ai_root / "agent-memory" / "executors" / "atlas-dev" / "MEMORY.md").exists()
    # dead skill-dir form must NOT be produced
    assert not (engine_root / "skills" / "exec.atlas-dev").exists()
    # inline voice — no separate personality.md, no dotted memory slug
    body = agent_def.read_text()
    assert "personality.md" not in body
    assert "exec.atlas-dev" not in body


# ---------------------------------------------------------------------------
# 5. Idempotent — run twice; exit 0; exactly ONE exec-atlas-dev.md agent-def
# ---------------------------------------------------------------------------
def test_idempotent(ai_root):
    run_engine(
        "register", "executor",
        "--chosen-name", "atlas", "--role", "dev",
        "--emoji", "🦊", "--color", "teal", "--wraps", "team-implementer",
    )
    r = run_engine(
        "register", "executor",
        "--chosen-name", "atlas", "--role", "dev",
        "--emoji", "🦊", "--color", "teal", "--wraps", "team-implementer",
    )
    assert r.returncode == 0
    hits = list(_agents_dir().glob("exec-atlas-dev.md"))
    assert len(hits) == 1


# ---------------------------------------------------------------------------
# 6. --dry-run → exit 0; no agent-def created
# ---------------------------------------------------------------------------
def test_dry_run(ai_root):
    r = run_engine(
        "register", "executor",
        "--chosen-name", "atlas", "--role", "dev",
        "--emoji", "🦊", "--color", "teal", "--wraps", "team-implementer",
        "--dry-run",
    )
    assert r.returncode == 0
    assert not (_agents_dir() / "exec-atlas-dev.md").exists()


# ---------------------------------------------------------------------------
# 7. --wraps default dev → exec-scout-dev.md agent-def contains "team-implementer"
# ---------------------------------------------------------------------------
def test_wraps_default_dev(ai_root):
    r = run_engine(
        "register", "executor",
        "--chosen-name", "scout", "--role", "dev", "--emoji", "🦁", "--color", "amber",
    )
    assert r.returncode == 0
    body = (_agents_dir() / "exec-scout-dev.md").read_text()
    assert "team-implementer" in body


# ---------------------------------------------------------------------------
# 8. --wraps default test → exec-argus-test.md agent-def contains "team-reviewer"
# ---------------------------------------------------------------------------
def test_wraps_default_test(ai_root):
    r = run_engine(
        "register", "executor",
        "--chosen-name", "argus", "--role", "test", "--emoji", "🔬", "--color", "blue",
    )
    assert r.returncode == 0
    body = (_agents_dir() / "exec-argus-test.md").read_text()
    assert "team-reviewer" in body


# ---------------------------------------------------------------------------
# 11. #68/#61 — create-path output satisfies the executor naming standard,
#     guarding hire-time drift (not just hand-authored defs)
# ---------------------------------------------------------------------------
def test_create_path_emits_naming_standard(ai_root):
    r = run_engine(
        "register", "executor",
        "--chosen-name", "atlas", "--role", "dev",
        "--emoji", "🦊", "--color", "teal", "--wraps", "team-implementer",
    )
    assert r.returncode == 0
    agent_def = _agents_dir() / "exec-atlas-dev.md"
    body = agent_def.read_text()
    # filename stem == exec-<name>-<role> (3 hyphen segments)
    assert agent_def.stem == "exec-atlas-dev"
    # frontmatter coherence: name == stem, chosen-name == <name> segment
    assert re.search(r"^name:\s*exec-atlas-dev\s*$", body, re.M), "frontmatter name: must equal stem"
    assert re.search(r"^chosen-name:\s*atlas\s*$", body, re.M), "chosen-name: must equal <name> segment"
    # name-keyed sentinel the naming guard asserts
    assert "<!-- exec:atlas v1 -->" in body
    # canonical memory path: hyphen slug under executors/, no dotted exec. form
    assert "executors/atlas-dev/" in body


# ---------------------------------------------------------------------------
# 9. chosen-name with spaces → exit ≠ 0
# ---------------------------------------------------------------------------
def test_chosen_name_with_spaces(ai_root):
    r = run_engine(
        "register", "executor",
        "--chosen-name", "has spaces", "--role", "dev", "--emoji", "🦊", "--color", "teal",
    )
    assert r.returncode != 0


# ---------------------------------------------------------------------------
# 10. chosen-name with slash → exit ≠ 0
# ---------------------------------------------------------------------------
def test_chosen_name_with_slash(ai_root):
    r = run_engine(
        "register", "executor",
        "--chosen-name", "has/slash", "--role", "dev", "--emoji", "🦊", "--color", "teal",
    )
    assert r.returncode != 0

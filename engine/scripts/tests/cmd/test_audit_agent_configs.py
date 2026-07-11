"""tests/cmd/test_audit_agent_configs.py — integration tests for `engine audit agent-configs`.

No bash test to port — all cases are new. Uses bare tmp_path (NOT ai_root fixture).
Seam: env={"CONCLAVE_AI_ROOT": str(tmp_path)} → scan_dir = tmp_path/.claude.
"""
from tests.cmd.helpers import run_engine


def _claude_dir(tmp_path):
    d = tmp_path / ".claude"
    d.mkdir()
    return d


# ──────────────────────────────────────────────────────────────────────────────
# Case 1: clean repo
# ──────────────────────────────────────────────────────────────────────────────

def test_clean_exit0(tmp_path):
    """Benign content → 0 CRIT, 0 WARN, exit 0, no [CRIT]/[WARN] blocks."""
    claude = _claude_dir(tmp_path)
    (claude / "x.md").write_text("# harmless\nSome benign content here.\n")

    r = run_engine("audit", "agent-configs", env={"CONCLAVE_AI_ROOT": str(tmp_path)})

    assert r.returncode == 0
    assert "=== Summary: 0 CRIT, 0 WARN ===" in r.stdout
    assert "[CRIT]" not in r.stdout
    assert "[WARN]" not in r.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Case 2: Anthropic-style key leak → CRIT, exit 2
# ──────────────────────────────────────────────────────────────────────────────

def test_secret_crit_exit2(tmp_path):
    """sk- + 32 alnum chars triggers CRIT and exit 2."""
    claude = _claude_dir(tmp_path)
    secret = "sk-" + "a" * 32
    (claude / "leak.md").write_text(f"API_KEY={secret}\n")

    r = run_engine("audit", "agent-configs", env={"CONCLAVE_AI_ROOT": str(tmp_path)})

    assert r.returncode == 2
    assert "[CRIT] Anthropic-style API key leak" in r.stdout
    assert "1 CRIT" in r.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Case 3: settings.local.json excluded (SECRET_EXCLUDES)
# ──────────────────────────────────────────────────────────────────────────────

def test_settings_local_excluded(tmp_path):
    """Secret in settings.local.json is excluded by SECRET_EXCLUDES — not flagged."""
    claude = _claude_dir(tmp_path)
    secret = "sk-" + "b" * 32
    (claude / "settings.local.json").write_text(f"ALLOW_KEY={secret}\n")

    r = run_engine("audit", "agent-configs", env={"CONCLAVE_AI_ROOT": str(tmp_path)})

    assert r.returncode == 0
    assert "=== Summary: 0 CRIT, 0 WARN ===" in r.stdout
    assert "[CRIT]" not in r.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Case 4: WARN flag, exit 0; references/ dir excluded (DANGER_EXCLUDES)
# ──────────────────────────────────────────────────────────────────────────────

def test_warn_flag_exit0_and_references_excluded(tmp_path):
    """--no-verify in hook.sh → WARN, exit 0. Same string in references/ → excluded."""
    claude = _claude_dir(tmp_path)
    (claude / "hook.sh").write_text("git commit --no-verify -m 'msg'\n")

    refs = claude / "references"
    refs.mkdir()
    (refs / "foo.md").write_text("Do NOT use --no-verify in production.\n")

    r = run_engine("audit", "agent-configs", env={"CONCLAVE_AI_ROOT": str(tmp_path)})

    assert r.returncode == 0
    assert "[WARN] --no-verify flag" in r.stdout
    # Only hook.sh should appear, not references/foo.md
    assert "hook.sh" in r.stdout
    assert "foo.md" not in r.stdout
    assert "0 CRIT" in r.stdout
    # WARN present but summary shows warn count
    assert "=== Summary: 0 CRIT, 1 WARN ===" in r.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Case 5: unquoted shell var in hook command → CRIT, exit 2
# ──────────────────────────────────────────────────────────────────────────────

def test_hook_injection_crit_exit2(tmp_path):
    """Hook command with unquoted $VAR triggers CRIT and exit 2.

    Pattern: "command":[^"]*\\$[A-Z_]+[^"]*"
    Matches when there is no opening JSON string quote between "command": and the $VAR.
    Example: {"command": exec $INPUT_FILE "run"} — the value is unquoted JSON.
    """
    claude = _claude_dir(tmp_path)
    # The value after "command": must not begin with " for the pattern to match.
    # This represents an injection: the hook value is unquoted, exposing shell expansion.
    (claude / "settings.json").write_text(
        '{"hooks": [{"matcher": "Bash", "command": exec $INPUT_FILE "run"}]}\n'
    )

    r = run_engine("audit", "agent-configs", env={"CONCLAVE_AI_ROOT": str(tmp_path)})

    assert r.returncode == 2
    assert "[CRIT] Unquoted shell var in hook command" in r.stdout
    assert "1 CRIT" in r.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Case 6a: exclude-dir .venv — secret inside .venv is not found
# ──────────────────────────────────────────────────────────────────────────────

def test_exclude_dir_venv(tmp_path):
    """Secret inside .claude/.venv/ is skipped (--exclude-dir=.venv equivalent)."""
    claude = _claude_dir(tmp_path)
    venv = claude / ".venv" / "lib"
    venv.mkdir(parents=True)
    secret = "sk-" + "c" * 32
    (venv / "x.py").write_text(f"KEY = '{secret}'\n")

    r = run_engine("audit", "agent-configs", env={"CONCLAVE_AI_ROOT": str(tmp_path)})

    assert r.returncode == 0
    assert "=== Summary: 0 CRIT, 0 WARN ===" in r.stdout
    assert "[CRIT]" not in r.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Case 6b: MCP wildcard scope → INFO block, but 0 CRIT/0 WARN, exit 0
# ──────────────────────────────────────────────────────────────────────────────

def test_mcp_info_exit0(tmp_path):
    """MCP server with wildcard scope → INFO block present, summary 0 CRIT 0 WARN, exit 0."""
    claude = _claude_dir(tmp_path)
    (claude / "settings.json").write_text(
        '{"mcpServers": {"myserver": "*"}}\n'
    )

    r = run_engine("audit", "agent-configs", env={"CONCLAVE_AI_ROOT": str(tmp_path)})

    assert r.returncode == 0
    assert "[INFO] MCP server with wildcard scope" in r.stdout
    assert "=== Summary: 0 CRIT, 0 WARN ===" in r.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Case 7: secret behind a DIRECTORY symlink → still CRIT, exit 2 (#81)
# ──────────────────────────────────────────────────────────────────────────────

def test_secret_behind_dir_symlink_crit_exit2(tmp_path):
    """Under spec 103 the DATA repo owns the skills; `.claude/skills/<name>` is a dir symlink.

    pathlib's rglob() lists a symlinked directory but never descends into it, so a secret one
    level below the link was invisible to the scanner while it still exited 0. That is the whole
    scan surface of the post-split layout going dark, not an edge case.
    """
    claude = _claude_dir(tmp_path)
    skills = claude / "skills"          # real dir, per spec 103 §3.2
    skills.mkdir()

    data_skill = tmp_path / "data" / ".claude" / "skills" / "myskill"
    data_skill.mkdir(parents=True)
    secret = "ghp_" + "d" * 36
    (data_skill / "SKILL.md").write_text(f"token: {secret}\n")

    (skills / "myskill").symlink_to(data_skill, target_is_directory=True)

    r = run_engine("audit", "agent-configs", env={"CONCLAVE_AI_ROOT": str(tmp_path)})

    assert r.returncode == 2
    assert "[CRIT] GitHub personal access token leak" in r.stdout
    assert "1 CRIT" in r.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Case 8: file symlink stays visible (no regression) (#81)
# ──────────────────────────────────────────────────────────────────────────────

def test_secret_behind_file_symlink_crit_exit2(tmp_path):
    """`.claude/agents/<id>.md` is a per-FILE symlink; rglob already lists those. Lock it in."""
    claude = _claude_dir(tmp_path)
    agents = claude / "agents"
    agents.mkdir()

    target = tmp_path / "data" / "kai.md"
    target.parent.mkdir(parents=True)
    secret = "sk-" + "e" * 32
    target.write_text(f"key: {secret}\n")

    (agents / "kai.md").symlink_to(target)

    r = run_engine("audit", "agent-configs", env={"CONCLAVE_AI_ROOT": str(tmp_path)})

    assert r.returncode == 2
    assert "[CRIT] Anthropic-style API key leak" in r.stdout


# ──────────────────────────────────────────────────────────────────────────────
# Case 9: symlink cycle must not multiply a finding (#81)
# ──────────────────────────────────────────────────────────────────────────────

def test_symlink_cycle_does_not_multiply_findings(tmp_path):
    """`.claude/loop -> .claude`: one real leak must be reported once, not once per cycle level.

    A cycle does not hang the walker — the kernel raises ELOOP roughly 32 levels down and the
    descent stops on its own. What it does without a visited set is re-yield every file below the
    link once per level (measured: 16 yields of a single file), inflating the CRIT count and the
    match list. The dedup is what makes the count trustworthy.
    """
    claude = _claude_dir(tmp_path)
    secret = "sk-" + "f" * 32
    (claude / "leak.md").write_text(f"key: {secret}\n")
    (claude / "loop").symlink_to(claude, target_is_directory=True)

    r = run_engine("audit", "agent-configs", env={"CONCLAVE_AI_ROOT": str(tmp_path)})

    assert r.returncode == 2
    assert "1 CRIT" in r.stdout

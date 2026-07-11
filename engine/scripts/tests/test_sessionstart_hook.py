import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
HOOK = ROOT / "hooks/sessionstart-conclave.py"


def _run(project_dir):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir), "CONCLAVE_ENGINE_ROOT": str(ROOT / "engine")}
    r = subprocess.run(["python3", str(HOOK)], env=env, capture_output=True, text=True)
    return r.stdout


def test_uninitialized_emits_nudge_no_scaffold(tmp_path):
    out = _run(tmp_path)
    assert "conclave:init" in out.lower()
    assert not (tmp_path / ".conclave").exists()   # never scaffolds by magic


def test_initialized_injects_dashboard(tmp_path):
    (tmp_path / ".conclave/agent-memory/advisors/briefings").mkdir(parents=True)
    (tmp_path / ".conclave/roster.yaml").write_text("name: demo\n")
    # hire one discoverable advisor so render_dashboard emits real content
    # (_known_advisors globs ${CLAUDE_PROJECT_DIR}/.claude/agents/*.md — D-5b)
    (tmp_path / ".claude/agents").mkdir(parents=True)
    (tmp_path / ".claude/agents/demo-advisor.md").write_text("---\nname: demo-advisor\n---\n")
    out = _run(tmp_path)
    # dashboard markers (briefing/resume/cadence/roster) — at least one present
    assert any(k in out.lower() for k in ["briefing", "roster", "resume", "cadence"])


def test_hook_resolves_engine_via_env_no_plugin_root_literal():
    # F-001: the plugin-root interpolation var is empty at SessionStart (CC #27145/#39550);
    # the shipped script must resolve its engine root from CONCLAVE_ENGINE_ROOT.
    src = HOOK.read_text()
    assert "${CLAUDE_PLUGIN_ROOT}" not in src
    assert "CONCLAVE_ENGINE_ROOT" in src

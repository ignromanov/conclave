"""test_start_self_heal.py — SessionStart hook self-heal on /conclave:start (099 followups B1).

On a marketplace/git install the plugin lives in a content-hash cache dir that
`/plugin update` wipes; conclave_init.register_hook() baked that dir's absolute path into
the consumer's .claude/settings.json (SessionStart command + CONCLAVE_ENGINE_ROOT), so an
update silently kills the hook. `/conclave:start` runs with ${CLAUDE_PLUGIN_ROOT} populated
(unlike the hook itself — CC #27145/#39550) and is the repair window.

Two layers:
  - unit: enginelib.init.reconcile_hook, pure (no I/O).
  - integration: the standalone runner engine/scripts/init/reconcile_hook.py, via subprocess
    (mirrors test_conclave_init.py / test_sessionstart_hook.py's subprocess pattern).
"""
import json
import os
import pathlib
import subprocess

from enginelib.init import desired_hook, reconcile_hook

ROOT = pathlib.Path(__file__).resolve().parents[3]
RUNNER = ROOT / "engine" / "scripts" / "init" / "reconcile_hook.py"


def _settings_with_hook(plugin_root: pathlib.Path, ai_root: str = "/consumer/.conclave") -> dict:
    """Build a settings dict as register_hook() would, registered for `plugin_root`."""
    command, engine_root = desired_hook(plugin_root)
    return {
        "hooks": {
            "SessionStart": [
                {"matcher": "*", "hooks": [{"type": "command", "command": command}]}
            ]
        },
        "env": {"CONCLAVE_ENGINE_ROOT": engine_root, "CONCLAVE_AI_ROOT": ai_root},
    }


# ---------------------------------------------------------------------------
# Unit — enginelib.init.reconcile_hook (pure)
# ---------------------------------------------------------------------------


def test_stale_hook_repaired_to_new_root(tmp_path):
    old_root = tmp_path / "old-plugin-hash"
    new_root = tmp_path / "new-plugin-hash"
    settings = _settings_with_hook(old_root)

    updated, changed = reconcile_hook(new_root, settings)

    assert changed is True
    desired_command, desired_engine_root = desired_hook(new_root)
    assert updated["env"]["CONCLAVE_ENGINE_ROOT"] == desired_engine_root
    commands = [
        h["command"] for entry in updated["hooks"]["SessionStart"] for h in entry["hooks"]
    ]
    assert desired_command in commands
    assert str(old_root) not in json.dumps(updated)
    # original untouched (pure — operates on a copy)
    old_command, old_engine_root = desired_hook(old_root)
    assert settings["env"]["CONCLAVE_ENGINE_ROOT"] == old_engine_root
    assert settings["hooks"]["SessionStart"][0]["hooks"][0]["command"] == old_command


def test_reconcile_is_idempotent(tmp_path):
    new_root = tmp_path / "new-plugin-hash"
    settings = _settings_with_hook(new_root)

    first, changed_first = reconcile_hook(new_root, settings)
    second, changed_second = reconcile_hook(new_root, first)

    assert changed_first is False
    assert changed_second is False
    assert second == first


def test_ai_root_untouched(tmp_path):
    old_root = tmp_path / "old-plugin-hash"
    new_root = tmp_path / "new-plugin-hash"
    settings = _settings_with_hook(old_root, ai_root="/consumer/.conclave")

    updated, _ = reconcile_hook(new_root, settings)

    assert updated["env"]["CONCLAVE_AI_ROOT"] == "/consumer/.conclave"


def test_no_hook_present_appends_fresh_entry(tmp_path):
    new_root = tmp_path / "new-plugin-hash"

    updated, changed = reconcile_hook(new_root, {})

    assert changed is True
    desired_command, desired_engine_root = desired_hook(new_root)
    commands = [
        h["command"] for entry in updated["hooks"]["SessionStart"] for h in entry["hooks"]
    ]
    assert commands == [desired_command]
    assert updated["env"]["CONCLAVE_ENGINE_ROOT"] == desired_engine_root


def test_correctly_current_is_not_rewritten(tmp_path):
    new_root = tmp_path / "new-plugin-hash"
    settings = _settings_with_hook(new_root)

    updated, changed = reconcile_hook(new_root, settings)

    assert changed is False
    assert updated == settings


def test_unrelated_session_start_hooks_preserved(tmp_path):
    old_root = tmp_path / "old-plugin-hash"
    new_root = tmp_path / "new-plugin-hash"
    settings = _settings_with_hook(old_root)
    settings["hooks"]["SessionStart"].append(
        {"matcher": "*", "hooks": [{"type": "command", "command": "python3 other-tool.py"}]}
    )

    updated, changed = reconcile_hook(new_root, settings)

    assert changed is True
    commands = [
        h["command"] for entry in updated["hooks"]["SessionStart"] for h in entry["hooks"]
    ]
    assert "python3 other-tool.py" in commands


# ---------------------------------------------------------------------------
# Integration — the standalone runner (subprocess, plain python3, no uv)
# ---------------------------------------------------------------------------


def _run_runner(project_dir, plugin_root=None):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project_dir)}
    if plugin_root is not None:
        env["CLAUDE_PLUGIN_ROOT"] = str(plugin_root)
    else:
        env.pop("CLAUDE_PLUGIN_ROOT", None)
    return subprocess.run(
        ["python3", str(RUNNER)], env=env, cwd=str(project_dir), capture_output=True, text=True
    )


def test_runner_repairs_stale_settings_end_to_end(tmp_path):
    old_plugin = tmp_path / "old-plugin-hash"
    new_plugin = tmp_path / "new-plugin-hash"
    project = tmp_path / "consumer"
    (project / ".claude").mkdir(parents=True)
    ai_root = str(project / ".conclave")
    settings = _settings_with_hook(old_plugin, ai_root=ai_root)
    settings_path = project / ".claude" / "settings.json"
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")

    result = _run_runner(project, plugin_root=new_plugin)

    assert result.returncode == 0, result.stderr
    after = json.loads(settings_path.read_text())
    desired_command, desired_engine_root = desired_hook(new_plugin)
    commands = [h["command"] for entry in after["hooks"]["SessionStart"] for h in entry["hooks"]]
    assert desired_command in commands
    assert after["env"]["CONCLAVE_ENGINE_ROOT"] == desired_engine_root
    assert after["env"]["CONCLAVE_AI_ROOT"] == ai_root
    assert str(old_plugin) not in json.dumps(after)


def test_runner_second_run_is_noop(tmp_path):
    new_plugin = tmp_path / "new-plugin-hash"
    project = tmp_path / "consumer"
    (project / ".claude").mkdir(parents=True)
    settings = _settings_with_hook(new_plugin, ai_root=str(project / ".conclave"))
    settings_path = project / ".claude" / "settings.json"
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    before = settings_path.read_text()

    result = _run_runner(project, plugin_root=new_plugin)

    assert result.returncode == 0, result.stderr
    assert settings_path.read_text() == before


def test_runner_missing_plugin_root_exits_zero_no_crash(tmp_path):
    project = tmp_path / "consumer"
    (project / ".claude").mkdir(parents=True)
    settings_path = project / ".claude" / "settings.json"
    settings_path.write_text('{"hooks": {}}\n')

    result = _run_runner(project, plugin_root=None)

    assert result.returncode == 0, result.stderr
    # never touched — can't repair without knowing the current root
    assert settings_path.read_text() == '{"hooks": {}}\n'


def test_runner_missing_settings_file_exits_zero(tmp_path):
    new_plugin = tmp_path / "new-plugin-hash"
    project = tmp_path / "consumer"
    project.mkdir(parents=True)

    result = _run_runner(project, plugin_root=new_plugin)

    assert result.returncode == 0, result.stderr
    assert not (project / ".claude" / "settings.json").exists()


def test_runner_unreadable_settings_json_exits_zero(tmp_path):
    new_plugin = tmp_path / "new-plugin-hash"
    project = tmp_path / "consumer"
    (project / ".claude").mkdir(parents=True)
    settings_path = project / ".claude" / "settings.json"
    settings_path.write_text("{not valid json")

    result = _run_runner(project, plugin_root=new_plugin)

    assert result.returncode == 0, result.stderr
    assert settings_path.read_text() == "{not valid json"

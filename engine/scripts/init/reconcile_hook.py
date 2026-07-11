#!/usr/bin/env python3
"""reconcile_hook.py — self-heal the SessionStart hook registration (099 followups B1).

Standalone, stdlib-only — mirrors init/conclave_init.py and hooks/sessionstart-conclave.py:
runs on system python3, no uv, no `python -m engine`. Deliberate: the repair must not
depend on the plugin venv/deps, which live under the same content-hash cache dir that
`/plugin update` wipes.

Invoked from /conclave:start, which (unlike the SessionStart hook itself) runs with
${CLAUDE_PLUGIN_ROOT} populated — this is the window where the consumer's
`.claude/settings.json` (SessionStart command + CONCLAVE_ENGINE_ROOT, both baked in as
resolved absolute paths by conclave_init.register_hook) can be repaired after the old
plugin cache dir has been removed.

Best-effort: always exits 0 so a missing/unreadable settings file, or a missing
CLAUDE_PLUGIN_ROOT, never blocks a session start.
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # engine/scripts
from enginelib.init import reconcile_hook  # noqa: E402
from enginelib.snapshot import snapshot_write  # noqa: E402


def main() -> int:
    plugin_root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root_env:
        print("[reconcile-hook] CLAUDE_PLUGIN_ROOT unset — skipping (nothing to repair against)")
        return 0

    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    settings_path = Path(project_dir) / ".claude" / "settings.json"
    if not settings_path.exists():
        print(f"[reconcile-hook] no settings file at {settings_path} — nothing to repair")
        return 0

    try:
        settings = json.loads(settings_path.read_text())
    except json.JSONDecodeError as e:
        print(f"[reconcile-hook] {settings_path} unreadable ({e}) — skipping best-effort")
        return 0

    plugin_root = Path(plugin_root_env)
    updated, changed = reconcile_hook(plugin_root, settings)
    if not changed:
        print(f"[reconcile-hook] {settings_path} already current")
        return 0

    snapshot_write(settings_path, json.dumps(updated, indent=2) + "\n")
    print(f"[reconcile-hook] repaired: {settings_path} -> {plugin_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

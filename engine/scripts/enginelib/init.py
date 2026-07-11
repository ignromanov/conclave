"""init.py — pure reconciliation of the SessionStart hook registration (099 followups B1).

No filesystem reads/writes, no environment access, no stdout, no CLI parsing, no process
exit — this module only computes the desired hook shape for a given plugin root and
reconciles it against an in-memory settings dict. The standalone runner that actually
reads/writes the consumer's `.claude/settings.json` and reports its outcome lives at
`engine/scripts/init/reconcile_hook.py` (stdlib-only, runs on system python3 so the repair
does not depend on the plugin venv/deps, which may live in the same wiped cache dir).

Mirrors `init/conclave_init.py::register_hook`'s exact command-string format so a
correctly-registered hook is recognized as already-current rather than rewritten needlessly.
"""
import copy
from pathlib import Path
from typing import Any

_HOOK_MARKER = "sessionstart-conclave.py"


def desired_hook(plugin_root: Path) -> tuple[str, str]:
    """Return (command, engine_root) the settings SHOULD have for this plugin_root.

    Mirrors conclave_init exactly:
    command = f'python3 "{plugin_root}/hooks/sessionstart-conclave.py"';
    engine_root = str(plugin_root / "engine").
    """
    hook_script = plugin_root / "hooks" / "sessionstart-conclave.py"
    command = f'python3 "{hook_script}"'
    engine_root = str(plugin_root / "engine")
    return command, engine_root


def reconcile_hook(plugin_root: Path, settings: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Reconcile the SessionStart hook command + CONCLAVE_ENGINE_ROOT against plugin_root.

    Given the on-disk settings dict and the CURRENT plugin_root, return
    (updated_settings, changed):
      - command: every SessionStart hook whose command references
        sessionstart-conclave.py is rewritten to the desired command if different. If none
        exists, a fresh entry {"matcher": "*", "hooks": [{"type": "command", "command": ...}]}
        is appended.
      - env: settings['env']['CONCLAVE_ENGINE_ROOT'] is set to the desired engine_root if
        different. env['CONCLAVE_AI_ROOT'] is never touched — it points at the consumer's
        DATA dir and does not rot.
      - changed is True iff anything actually differed. Idempotent: a second call with the
        same plugin_root returns changed=False.

    Operates on a deep copy of `settings`; the caller's dict is never mutated.
    """
    updated = copy.deepcopy(settings)
    desired_command, desired_engine_root = desired_hook(plugin_root)
    changed = False

    hooks = updated.setdefault("hooks", {})
    session_start = hooks.setdefault("SessionStart", [])
    found = False
    for entry in session_start:
        for h in entry.get("hooks", []):
            command = h.get("command", "")
            if _HOOK_MARKER in command:
                found = True
                if command != desired_command:
                    h["command"] = desired_command
                    changed = True
    if not found:
        session_start.append(
            {"matcher": "*", "hooks": [{"type": "command", "command": desired_command}]}
        )
        changed = True

    env = updated.setdefault("env", {})
    if env.get("CONCLAVE_ENGINE_ROOT") != desired_engine_root:
        env["CONCLAVE_ENGINE_ROOT"] = desired_engine_root
        changed = True

    return updated, changed

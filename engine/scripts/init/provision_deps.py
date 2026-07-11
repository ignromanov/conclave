#!/usr/bin/env python3
"""provision_deps.py — self-heal engine deps into ${CLAUDE_PLUGIN_DATA}/venv (099 followups B4).

Standalone, stdlib-only — mirrors init/reconcile_hook.py: runs on system python3, no uv
required to *invoke* it, no `python -m engine`. Deliberate: the provisioning step must not
itself depend on the plugin venv/deps it's trying to provision.

Invoked from /conclave:start, immediately after the B1 reconcile step, where
${CLAUDE_PLUGIN_ROOT} is populated (unlike the raw SessionStart hook — CC #27145/#39550).

Best-effort: always exits 0. Missing CLAUDE_PLUGIN_ROOT/CLAUDE_PLUGIN_DATA, a missing `uv`,
or a failed `uv sync` never block a session start.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # engine/scripts
from enginelib.provision import ensure_deps  # noqa: E402


def main() -> int:
    plugin_root_env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if not plugin_root_env:
        print("[provision-deps] CLAUDE_PLUGIN_ROOT unset — skipping")
        return 0

    data_env = os.environ.get("CLAUDE_PLUGIN_DATA")
    if not data_env:
        print("[provision-deps] CLAUDE_PLUGIN_DATA unset — skipping (dev/dogfood run)")
        return 0

    result = ensure_deps(Path(plugin_root_env), Path(data_env))
    if result.action == "failed":
        print(f"[provision-deps] uv sync failed: {result.reason}")
    elif result.action == "skipped":
        print(f"[provision-deps] skipped: {result.reason}")
    else:
        print(f"[provision-deps] {result.action} ({result.venv_python})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

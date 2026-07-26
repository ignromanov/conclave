#!/usr/bin/env python3
"""provision_deps.py — self-heal engine deps into ${CLAUDE_PLUGIN_DATA}/venv (099 followups B4).

Standalone, stdlib-only — mirrors init/reconcile_hook.py: runs on system python3, no uv
required to *invoke* it, no `python -m engine`. Deliberate: the provisioning step must not
itself depend on the plugin venv/deps it's trying to provision.

Invoked from /conclave:start, immediately after the B1 reconcile step, where
${CLAUDE_PLUGIN_ROOT} is populated (unlike the raw SessionStart hook — CC #27145/#39550).

Best-effort: always exits 0. Missing CLAUDE_PLUGIN_ROOT/CLAUDE_PLUGIN_DATA, a missing `uv`,
or a failed `uv sync` never block a session start. The interpreter-floor guard below is the
one exception — no `uv sync` can provision the interpreter this script is already running on.
"""
import os
import sys
from pathlib import Path

# Interpreter floor, enforced before the first thing that can fail below it — here,
# `enginelib.provision`, whose `venv_python: Path | None` field annotation is evaluated on
# import. /conclave:start Step 0b launches this file directly, before the guarded
# session_init.py at Step 1. Measured, not declared; see engine/__main__.py for the full note.
if sys.version_info < (3, 11):  # noqa: UP036 — see engine/__main__.py
    sys.stderr.write(
        f"Conclave requires Python 3.11 or newer.\n"
        f"This is Python {sys.version.split()[0]} at {sys.executable}.\n"
        f"Install a newer interpreter (e.g. `uv python install 3.13`) and re-run.\n"
    )
    sys.exit(1)

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

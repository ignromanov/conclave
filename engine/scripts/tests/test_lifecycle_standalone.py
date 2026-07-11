"""test_lifecycle_standalone.py — lifecycle scripts must self-bootstrap enginelib.

RED (session_init.py): fails before the sys.path shim is added
  (ModuleNotFoundError: No module named 'enginelib') — GH#1 it-8.
GREEN: passes once the shim is inserted, matching study_phase.py / gh_board_query.py
  which already carry it.

Each module is imported in a subprocess run with `-S` — which skips site.py, so the
venv's editable-install `.pth` that normally puts scripts/ on sys.path is NOT processed
and `enginelib` is therefore NOT auto-discovered. The venv's site-packages dir is added
back manually (via `sys.path.insert`, which does not trigger `.pth` processing) so genuine
third-party deps (ruamel/pydantic) that the enginelib chain needs stay importable. Under
this setup, `import enginelib` resolves ONLY if the module itself inserts scripts/ onto
sys.path at load time — the exact robustness a bare `python3` invocation needs (GH#1 it-8).
"""
from __future__ import annotations

import os
import subprocess
import sys
import sysconfig
from pathlib import Path

import pytest

LIFECYCLE_DIR = Path(__file__).resolve().parent.parent / "lifecycle"

# venv site-packages — carries third-party deps (ruamel, pydantic) but NOT the
# editable enginelib path (that comes from a .pth, which -S skips).
_SITE_PACKAGES = sysconfig.get_paths()["purelib"]

# Env with the import-path knobs scrubbed — the script must bootstrap on its own.
_CLEAN_ENV: dict[str, str] = {
    k: v for k, v in os.environ.items()
    if k not in ("PYTHONPATH", "PYTHONSTARTUP", "PYTHONHOME")
}


def _probe(module: str) -> subprocess.CompletedProcess[str]:
    """Import the module (runs its load-time shim), then import enginelib."""
    code = (
        f"import sys; sys.path.append({_SITE_PACKAGES!r}); "
        f"import {module}; import enginelib"
    )
    return subprocess.run(
        [sys.executable, "-S", "-c", code],
        capture_output=True,
        text=True,
        cwd=str(LIFECYCLE_DIR),
        env=_CLEAN_ENV,
    )


@pytest.mark.parametrize("module", ["session_init", "study_phase", "gh_board_query"])
def test_lifecycle_script_self_bootstraps_enginelib(module: str) -> None:
    result = _probe(module)
    assert "ModuleNotFoundError" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr

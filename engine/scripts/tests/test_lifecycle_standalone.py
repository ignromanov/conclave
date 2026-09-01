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
import shutil
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


# ---------------------------------------------------------------------------
# GH#187 — a lifecycle script must dispatch its sibling helpers from its OWN copy.
#
# `_engine_root()` honoured an ambient CONCLAVE_ENGINE_ROOT ahead of `__file__`, and that
# variable is baked into `.claude/settings.json` by the initialiser, so every process on the
# machine inherits it. A worktree's `session_init.py` therefore ran `python -m engine ...`
# with `cwd=<main checkout>/engine/scripts` — measured, not inferred, before the fix.
#
# That is the mechanism behind #171: a pre-spec-099 plugin cache answered a real 65-item
# triage with older semantics and produced a diverged index. A copy that errors costs a turn;
# a copy that silently answers costs a wrong conclusion.
# ---------------------------------------------------------------------------

SCRIPTS_DIR = LIFECYCLE_DIR.parent
OWN_ENGINE_ROOT = SCRIPTS_DIR.parent


def _second_copy(tmp_path: Path, module: str) -> Path:
    """A real second checkout of one lifecycle script, at <tmp>/engine/scripts/lifecycle/.

    Only `lifecycle/<module>.py` is copied; every other top-level entry of `scripts/` is
    symlinked, so the module still imports `enginelib` while the file under test genuinely
    lives in a different engine root. A stub tree would only prove the stub's layout.
    """
    scripts = tmp_path / "engine" / "scripts"
    (scripts / "lifecycle").mkdir(parents=True)
    shutil.copy2(LIFECYCLE_DIR / f"{module}.py", scripts / "lifecycle" / f"{module}.py")
    for entry in SCRIPTS_DIR.iterdir():
        if entry.name not in ("lifecycle", "__pycache__"):
            (scripts / entry.name).symlink_to(entry)
    return tmp_path / "engine"


@pytest.mark.parametrize("module", ["session_init", "study_phase"])
def test_engine_root_prefers_own_copy(module: str, tmp_path: Path) -> None:
    """CONCLAVE_ENGINE_ROOT points at another checkout; the script must ignore it."""
    copy_root = _second_copy(tmp_path, module)

    env = {
        **_CLEAN_ENV,
        # The ambient value the SessionStart hook exports — a DIFFERENT engine root.
        "CONCLAVE_ENGINE_ROOT": str(OWN_ENGINE_ROOT),
    }
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}; print({module}._engine_root())"],
        capture_output=True,
        text=True,
        cwd=str(copy_root / "scripts" / "lifecycle"),
        env=env,
    )
    assert result.returncode == 0, result.stderr
    answered = Path(result.stdout.strip())
    assert answered == copy_root.resolve(), (
        f"{module} dispatches helpers from {answered}, not from its own copy at "
        f"{copy_root} — a script in one checkout is running another checkout's code."
    )


def test_a_divergent_ambient_engine_root_is_announced(tmp_path: Path) -> None:
    """Ignoring the variable silently would swap one invisible answer for another: the
    operator set it deliberately and is entitled to know it was overruled."""
    copy_root = _second_copy(tmp_path, "session_init")

    env = {**_CLEAN_ENV, "CONCLAVE_ENGINE_ROOT": str(OWN_ENGINE_ROOT)}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import session_init; print('\\n'.join(session_init._pin_engine_root_to_own_copy()))",
        ],
        capture_output=True,
        text=True,
        cwd=str(copy_root / "scripts" / "lifecycle"),
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert str(OWN_ENGINE_ROOT) in result.stdout
    assert str(copy_root.resolve()) in result.stdout


def test_an_agreeing_ambient_engine_root_is_silent(tmp_path: Path) -> None:
    """No divergence, no warning — a notice that fires on the healthy path gets tuned out."""
    copy_root = _second_copy(tmp_path, "session_init")

    env = {**_CLEAN_ENV, "CONCLAVE_ENGINE_ROOT": str(copy_root)}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import session_init; print(len(session_init._pin_engine_root_to_own_copy()))",
        ],
        capture_output=True,
        text=True,
        cwd=str(copy_root / "scripts" / "lifecycle"),
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0"

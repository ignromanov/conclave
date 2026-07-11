"""tests/test_provision.py — provision engine deps into ${CLAUDE_PLUGIN_DATA} (099 followups B4).

Two layers:
  - unit: enginelib.provision.ensure_deps (via the injected `uv_sync` seam — no real uv/network)
    and enginelib.provision.plan_reexec (pure, no fs/subprocess).
  - integration: the re-exec path end-to-end via subprocess, using the CONCLAVE_ENGINE_FORCE_REEXEC
    seam (forces deps_present=False deterministically) plus a stub `venv/bin/python` that proves
    it was actually exec'd into (writes a marker, then hands off to the real interpreter) — a
    plain symlink can't distinguish "re-exec happened" from "bootstrap no-op'd" here, since --help
    is dep-free and succeeds either way.
"""
import os
import subprocess
import sys
from pathlib import Path

from enginelib.provision import Reexec, ensure_deps, plan_reexec
from tests.cmd.helpers import run_engine


def _write_manifest(
    scripts_dir: Path, lock: bytes = b"lock-v1", pyproject: bytes = b"pyproject-v1"
) -> None:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "uv.lock").write_bytes(lock)
    (scripts_dir / "pyproject.toml").write_bytes(pyproject)


def _setup(tmp_path: Path) -> tuple[Path, Path, Path]:
    plugin_root = tmp_path / "plugin"
    scripts_dir = plugin_root / "engine" / "scripts"
    _write_manifest(scripts_dir)
    data_dir = tmp_path / "data"
    return plugin_root, scripts_dir, data_dir


def _fake_uv_sync(calls: list) -> object:
    def _sync(scripts_dir: Path, venv_dir: Path) -> None:
        calls.append((scripts_dir, venv_dir))
        bin_dir = venv_dir / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        python = bin_dir / "python"
        if not python.exists():
            python.symlink_to(sys.executable)

    return _sync


def _raising_uv_sync(exc: Exception) -> object:
    def _sync(scripts_dir: Path, venv_dir: Path) -> None:
        raise exc

    return _sync


# ---------------------------------------------------------------------------
# ensure_deps — via the injected uv_sync seam (no real uv/network)
# ---------------------------------------------------------------------------


def test_ensure_deps_fresh_installs(tmp_path):
    plugin_root, scripts_dir, data_dir = _setup(tmp_path)
    calls: list = []

    result = ensure_deps(plugin_root, data_dir, uv_sync=_fake_uv_sync(calls))

    assert result.action == "installed"
    assert result.reinstalled is True
    assert result.venv_python == data_dir / "venv" / "bin" / "python"
    assert result.venv_python.exists()
    assert (data_dir / ".deps-hash").exists()
    assert len(calls) == 1


def test_ensure_deps_idempotent_no_uv_call(tmp_path):
    plugin_root, scripts_dir, data_dir = _setup(tmp_path)
    calls: list = []
    ensure_deps(plugin_root, data_dir, uv_sync=_fake_uv_sync(calls))
    assert len(calls) == 1

    result = ensure_deps(plugin_root, data_dir, uv_sync=_fake_uv_sync(calls))

    assert result.action == "current"
    assert result.reinstalled is False
    assert len(calls) == 1  # not called again


def test_ensure_deps_reinstalls_on_manifest_diff(tmp_path):
    plugin_root, scripts_dir, data_dir = _setup(tmp_path)
    calls: list = []
    ensure_deps(plugin_root, data_dir, uv_sync=_fake_uv_sync(calls))
    old_hash = (data_dir / ".deps-hash").read_text()

    (scripts_dir / "uv.lock").write_bytes(b"lock-v2")

    result = ensure_deps(plugin_root, data_dir, uv_sync=_fake_uv_sync(calls))

    assert result.reinstalled is True
    assert result.action == "updated"
    assert len(calls) == 2
    new_hash = (data_dir / ".deps-hash").read_text()
    assert new_hash != old_hash


def test_ensure_deps_missing_venv_reinstalls(tmp_path):
    plugin_root, scripts_dir, data_dir = _setup(tmp_path)
    calls: list = []
    ensure_deps(plugin_root, data_dir, uv_sync=_fake_uv_sync(calls))
    venv_python = data_dir / "venv" / "bin" / "python"
    venv_python.unlink()

    result = ensure_deps(plugin_root, data_dir, uv_sync=_fake_uv_sync(calls))

    assert result.reinstalled is True
    assert venv_python.exists()
    assert len(calls) == 2


def test_ensure_deps_uv_missing(tmp_path):
    plugin_root, scripts_dir, data_dir = _setup(tmp_path)

    result = ensure_deps(plugin_root, data_dir, uv_sync=_raising_uv_sync(FileNotFoundError()))

    assert result.action == "skipped"
    assert result.venv_python is None
    assert result.reason
    assert not (data_dir / ".deps-hash").exists()


def test_ensure_deps_uv_sync_fails(tmp_path):
    plugin_root, scripts_dir, data_dir = _setup(tmp_path)
    exc = subprocess.CalledProcessError(
        1, ["uv", "sync"], output="", stderr="boom: dependency conflict"
    )

    result = ensure_deps(plugin_root, data_dir, uv_sync=_raising_uv_sync(exc))

    assert result.action == "failed"
    assert result.venv_python is None
    assert "boom" in result.reason
    assert not (data_dir / ".deps-hash").exists()


def test_ensure_deps_manifest_not_found_skips(tmp_path):
    plugin_root = tmp_path / "plugin"  # no engine/scripts/{uv.lock,pyproject.toml} written
    data_dir = tmp_path / "data"

    result = ensure_deps(
        plugin_root, data_dir, uv_sync=_raising_uv_sync(AssertionError("must not be called"))
    )

    assert result.action == "skipped"
    assert result.venv_python is None


# ---------------------------------------------------------------------------
# plan_reexec — pure (no fs/subprocess access)
# ---------------------------------------------------------------------------

_VENV_PYTHON = Path("/data/venv/bin/python")
_SCRIPTS_DIR = Path("/plugin/engine/scripts")


def test_plan_reexec_deps_present_returns_none():
    result = plan_reexec(
        venv_python=_VENV_PYTHON,
        scripts_dir=_SCRIPTS_DIR,
        current_executable="/usr/bin/python3",
        args=["--help"],
        deps_present=True,
        bootstrapped=False,
    )

    assert result is None


def test_plan_reexec_bootstrapped_returns_none():
    result = plan_reexec(
        venv_python=_VENV_PYTHON,
        scripts_dir=_SCRIPTS_DIR,
        current_executable="/usr/bin/python3",
        args=["--help"],
        deps_present=False,
        bootstrapped=True,
    )

    assert result is None


def test_plan_reexec_no_venv_returns_none():
    result = plan_reexec(
        venv_python=None,
        scripts_dir=_SCRIPTS_DIR,
        current_executable="/usr/bin/python3",
        args=["--help"],
        deps_present=False,
        bootstrapped=False,
    )

    assert result is None


def test_plan_reexec_already_venv_interpreter_returns_none():
    result = plan_reexec(
        venv_python=_VENV_PYTHON,
        scripts_dir=_SCRIPTS_DIR,
        current_executable=str(_VENV_PYTHON),
        args=["--help"],
        deps_present=False,
        bootstrapped=False,
    )

    assert result is None


def test_plan_reexec_deps_absent_returns_reexec_plan():
    result = plan_reexec(
        venv_python=_VENV_PYTHON,
        scripts_dir=_SCRIPTS_DIR,
        current_executable="/usr/bin/python3",
        args=["advisor", "create"],
        deps_present=False,
        bootstrapped=False,
    )

    assert isinstance(result, Reexec)
    assert result.python == str(_VENV_PYTHON)
    assert result.argv == ["-m", "engine", "advisor", "create"]
    assert result.env["PYTHONPATH"] == str(_SCRIPTS_DIR)
    assert result.env["CONCLAVE_ENGINE_BOOTSTRAPPED"] == "1"


def test_plan_reexec_preserves_existing_pythonpath():
    result = plan_reexec(
        venv_python=_VENV_PYTHON,
        scripts_dir=_SCRIPTS_DIR,
        current_executable="/usr/bin/python3",
        args=["--help"],
        deps_present=False,
        bootstrapped=False,
        existing_pythonpath="/some/other/path",
    )

    assert result is not None
    assert result.env["PYTHONPATH"] == f"{_SCRIPTS_DIR}{os.pathsep}/some/other/path"


# ---------------------------------------------------------------------------
# Integration — re-exec end-to-end via subprocess (proves the fresh-consumer AC without uv)
# ---------------------------------------------------------------------------


def test_reexec_runs_command_end_to_end(tmp_path):
    data_dir = tmp_path / "data"
    venv_bin = data_dir / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    marker = tmp_path / "reexec-marker"
    venv_python = venv_bin / "python"
    # A stub interpreter that proves it was actually exec'd into (marker file) before handing
    # off to the real interpreter — a bare symlink to sys.executable can't be distinguished from
    # "bootstrap no-op'd" here, since --help is dep-free and this process already has real deps.
    venv_python.write_text(
        "#!/bin/sh\n"
        f'echo reexec > "{marker}"\n'
        f'exec "{sys.executable}" "$@"\n'
    )
    venv_python.chmod(0o755)

    result = run_engine(
        "--help",
        env={"CLAUDE_PLUGIN_DATA": str(data_dir), "CONCLAVE_ENGINE_FORCE_REEXEC": "1"},
    )

    assert result.returncode == 0, result.stderr
    assert marker.exists(), "expected the parent process to re-exec into venv_python"
    assert "usage" in result.stdout.lower()


def test_no_reexec_when_data_dir_unset(tmp_path):
    """Dev/dogfood no-op: CLAUDE_PLUGIN_DATA unset → no re-exec, --help still works."""
    result = run_engine("--help", env={"CLAUDE_PLUGIN_DATA": ""})

    assert result.returncode == 0, result.stderr
    assert "usage" in result.stdout.lower()

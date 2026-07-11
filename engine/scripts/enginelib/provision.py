"""provision.py — install engine third-party deps into ${CLAUDE_PLUGIN_DATA}/venv.

099 followups B4. A fresh consumer install and every `/plugin update` never carry a populated
`engine/scripts/.venv` (that directory lives inside the plugin tree and gets wiped on update).
`ensure_deps` provisions a persistent, content-hashed venv under the DATA dir instead, using
`uv sync --no-install-project` so only third-party deps land there; the engine/enginelib CODE
keeps being supplied via PYTHONPATH from the currently-running plugin source at re-exec time
(see `plan_reexec`) rather than from a copy that could rot.

Idempotent: a manifest-hash file gates reinstalls, and the target venv interpreter's presence
is checked too, so a manually-deleted venv self-heals on the next call.

Non-goal: Windows. Only the posix `venv/bin/python` layout is supported.
"""
import hashlib
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from enginelib.snapshot import snapshot_write

_STDERR_TAIL_CHARS = 500


@dataclass
class ProvisionResult:
    action: str  # "current" | "installed" | "updated" | "skipped" | "failed"
    venv_python: Path | None
    reason: str = ""
    reinstalled: bool = False  # True iff uv_sync was actually invoked


def _default_uv_sync(scripts_dir: Path, venv_dir: Path) -> None:
    subprocess.run(
        ["uv", "sync", "--frozen", "--no-install-project", "--project", str(scripts_dir)],
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(venv_dir)},
        check=True,
        capture_output=True,
        text=True,
    )


def ensure_deps(
    plugin_root: Path,
    data_dir: Path,
    *,
    uv_sync: Callable[[Path, Path], None] = _default_uv_sync,
) -> ProvisionResult:
    """Install/refresh the deps-only venv at `data_dir/venv`. Best-effort, never raises.

    1. Locate `uv.lock` + `pyproject.toml` under `plugin_root/engine/scripts`; missing either
       → "skipped" (nothing to provision from).
    2. Hash both manifests together; compare against the stored hash + the venv interpreter's
       presence — reinstall iff either is missing/stale (self-heals a manually-deleted venv).
    3. Not needed → "current", idempotent, no `uv` call.
    4. Needed → invoke `uv_sync`; on success write the new hash atomically and report
       "installed" (first time) or "updated" (refresh); on `uv` missing → "skipped"; on sync
       failure → "failed" with the hash left untouched so the next call retries.
    """
    scripts_dir = Path(plugin_root) / "engine" / "scripts"
    lock = scripts_dir / "uv.lock"
    pyproject = scripts_dir / "pyproject.toml"
    if not lock.exists() or not pyproject.exists():
        return ProvisionResult("skipped", None, "manifest not found")

    current = hashlib.sha256(lock.read_bytes() + b"\0" + pyproject.read_bytes()).hexdigest()

    data_dir = Path(data_dir)
    venv_dir = data_dir / "venv"
    venv_python = venv_dir / "bin" / "python"
    hash_file = data_dir / ".deps-hash"

    stored_hash = hash_file.read_text(encoding="utf-8").strip() if hash_file.exists() else None
    if venv_python.exists() and stored_hash == current:
        return ProvisionResult("current", venv_python)

    action = "installed" if stored_hash is None else "updated"
    try:
        uv_sync(scripts_dir, venv_dir)
    except FileNotFoundError:
        return ProvisionResult("skipped", None, "uv not found")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr if isinstance(exc.stderr, str) else str(exc.stderr or "")
        return ProvisionResult("failed", None, stderr[-_STDERR_TAIL_CHARS:])

    snapshot_write(hash_file, current)
    return ProvisionResult(action, venv_python, reinstalled=True)


@dataclass
class Reexec:
    python: str
    argv: list[str]  # ["-m", "engine", *args]
    env: dict[str, str]  # PYTHONPATH + sentinel overlay


def plan_reexec(
    *,
    venv_python: Path | None,
    scripts_dir: Path,
    current_executable: str,
    args: list[str],
    deps_present: bool,
    bootstrapped: bool,
    existing_pythonpath: str = "",
) -> Reexec | None:
    """Pure decision: should the current process re-exec into the provisioned venv?

    No filesystem/subprocess access — safe to unit-test exhaustively. Re-exec (not sys.path
    injection) so compiled-extension deps (e.g. pydantic) load from an ABI-matched interpreter.
    """
    if bootstrapped:
        return None  # loop guard (sentinel)
    if deps_present:
        return None  # dev/dogfood/in-venv → no re-exec
    if venv_python is None:
        return None  # not provisioned / no data dir
    if current_executable == str(venv_python):
        return None  # already the venv interpreter but deps missing → broken venv, don't loop
    pp = (
        f"{scripts_dir}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(scripts_dir)
    )
    return Reexec(
        str(venv_python),
        ["-m", "engine", *args],
        {"PYTHONPATH": pp, "CONCLAVE_ENGINE_BOOTSTRAPPED": "1"},
    )

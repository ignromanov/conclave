"""test_python_floor.py — the interpreter floor is declared once and enforced at every entrypoint.

Why this file exists: on an interpreter below the floor the engine used to die with a raw
`TypeError: unsupported operand type(s) for |` from PEP 604 annotations, naming neither Python
nor a version. Worse, the three entrypoints failed in three different ways — `python -m engine`
tripped on its own signature, `session_init.py` on an `enginelib` import, and `conclave_init.py`
not at all until after the user had answered the whole interactive interview.

The floor is measured, not declared: an import sweep of all 125 runtime modules is clean on 3.11
and 3.13 and fails on 3.10 solely on `from datetime import UTC` (added in 3.11).

Two layers of assertion:
  * structural — the guard exists, and sits before anything that can fail below the floor. Runs
    everywhere, needs no old interpreter.
  * behavioural — an actual sub-floor interpreter gets the friendly message and no traceback.
    Skipped when the machine has no such interpreter (a Linux CI box usually does not).
"""

from __future__ import annotations

import ast
import pathlib
import re
import subprocess
import sys

import pytest

SCRIPTS_ROOT = pathlib.Path(__file__).resolve().parents[1]

# The single source of truth for the floor, asserted against pyproject and the guards below.
FLOOR = (3, 11)

ENTRYPOINTS = (
    "engine/__main__.py",
    "lifecycle/session_init.py",
    "init/conclave_init.py",
)


def _module(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _is_stdlib(name: str) -> bool:
    return name.split(".")[0] in sys.stdlib_module_names


def _guard_line(tree: ast.Module) -> int | None:
    """Line of the module-level `if sys.version_info < (...)` guard, if present."""
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        if any(
            isinstance(sub, ast.Attribute) and sub.attr == "version_info"
            for sub in ast.walk(node.test)
        ):
            return node.lineno
    return None


def _guard_floor(tree: ast.Module) -> tuple[int, ...] | None:
    """The version tuple the guard compares against."""
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        for sub in ast.walk(node.test):
            if isinstance(sub, ast.Tuple) and all(
                isinstance(e, ast.Constant) and isinstance(e.value, int) for e in sub.elts
            ):
                return tuple(e.value for e in sub.elts)  # type: ignore[attr-defined]
    return None


@pytest.mark.parametrize("rel", ENTRYPOINTS)
def test_entrypoint_has_version_guard(rel: str) -> None:
    """Every entrypoint refuses a sub-floor interpreter itself — no reliance on the caller."""
    tree = _module(SCRIPTS_ROOT / rel)
    assert _guard_line(tree) is not None, (
        f"{rel} has no module-level `sys.version_info` guard; a sub-floor interpreter will "
        f"reach PEP 604 annotations or an interactive prompt before failing"
    )


@pytest.mark.parametrize("rel", ENTRYPOINTS)
def test_guard_floor_matches_declared_floor(rel: str) -> None:
    assert _guard_floor(_module(SCRIPTS_ROOT / rel)) == FLOOR


@pytest.mark.parametrize("rel", ENTRYPOINTS)
def test_guard_precedes_anything_that_can_fail(rel: str) -> None:
    """The guard must run before the first first-party import and before the first def/class.

    Those are the two things measured to break below the floor: `enginelib` imports carry PEP 604
    at module level, and a `def` whose signature is evaluated at definition time does too.
    """
    tree = _module(SCRIPTS_ROOT / rel)
    guard = _guard_line(tree)
    assert guard is not None, f"{rel}: no guard (see test_entrypoint_has_version_guard)"

    risky: list[tuple[int, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            risky += [(node.lineno, a.name) for a in node.names if not _is_stdlib(a.name)]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if node.level == 0 and mod != "__future__" and not _is_stdlib(mod):
                risky.append((node.lineno, mod))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            risky.append((node.lineno, f"def {node.name}"))

    if not risky:
        return
    first_line, first_what = min(risky)
    assert guard < first_line, (
        f"{rel}: guard at line {guard} runs after {first_what!r} at line {first_line}"
    )


def test_pyproject_floor_matches_guards() -> None:
    """A declared floor nobody enforces is a claim, not a constraint — keep the two in step."""
    text = (SCRIPTS_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^requires-python\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml declares no requires-python"
    assert match.group(1) == ">=" + ".".join(str(p) for p in FLOOR)


def _sub_floor_interpreter() -> str | None:
    """An interpreter below FLOOR, if this machine has one."""
    for candidate in ("/usr/bin/python3", "python3.9", "python3.10"):
        try:
            out = subprocess.run(
                [candidate, "-c", "import sys; print('%d.%d' % sys.version_info[:2])"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if out.returncode != 0:
            continue
        try:
            found = tuple(int(p) for p in out.stdout.strip().split("."))
        except ValueError:
            continue
        if found < FLOOR:
            return candidate
    return None


@pytest.mark.parametrize("rel", ENTRYPOINTS)
def test_sub_floor_interpreter_gets_a_readable_refusal(rel: str) -> None:
    """The observable contract: a version sentence and an exit, not a traceback."""
    interpreter = _sub_floor_interpreter()
    if interpreter is None:
        pytest.skip("no sub-floor interpreter on this machine")

    proc = subprocess.run(
        [interpreter, str(SCRIPTS_ROOT / rel), "--help"],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PYTHONPATH": str(SCRIPTS_ROOT), "PATH": "/usr/bin:/bin"},
        cwd=str(SCRIPTS_ROOT),
    )
    combined = proc.stdout + proc.stderr
    assert "Traceback" not in combined, f"{rel} still crashes below the floor:\n{combined}"
    assert re.search(r"3\.11", combined), f"{rel} refusal names no version:\n{combined}"
    assert proc.returncode != 0, f"{rel} exited 0 on a sub-floor interpreter"

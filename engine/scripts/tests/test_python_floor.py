"""test_python_floor.py — the interpreter floor is declared once and enforced at every entrypoint.

Why this file exists: on an interpreter below the floor the engine used to die with a raw
`TypeError: unsupported operand type(s) for |` from PEP 604 annotations, naming neither Python
nor a version. Worse, the entrypoints failed in several different ways — `python -m engine`
tripped on its own signature, `session_init.py` on an `enginelib` import, the `feedback/*`
scripts on `from datetime import UTC`, `lib/roster.py` on a `ModuleNotFoundError: ruamel` that
mentions neither Python nor a version, and `conclave_init.py` not at all until after the user
had answered the whole interactive interview.

The floor is measured, not declared: an import sweep of all 125 runtime modules is clean on 3.11
and 3.13 and fails on 3.10 solely on `from datetime import UTC` (added in 3.11).

**The entrypoint set is derived, not listed.** A hand-written tuple of three was what let five
prose-launched scripts ship unguarded: the enumeration and the shipped prose drifted apart with
nothing comparing them. So `_prose_entrypoints()` scans the prose that actually launches the
engine (`commands/*.md`, `skills/advisor-contracts/references/*.md`) for `python …/<script>.py`
invocations and resolves each to a file. Three assertions stop a broken scan passing vacuously:
the derived set must be non-empty, must contain the entrypoints known to be prose-launched, and
every matched path must resolve to a real file.

Two layers of assertion per entrypoint:
  * structural — the guard exists, and sits before anything that can fail below the floor. Runs
    everywhere, needs no old interpreter.
  * behavioural — an actual sub-floor interpreter gets the friendly message and no traceback.
    Skipped when the machine has no such interpreter (a Linux CI box usually does not).
"""

from __future__ import annotations

import ast
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

SCRIPTS_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_ROOT.parents[1]  # engine/scripts -> engine -> repo root

# The single source of truth for the floor, asserted against pyproject and the guards below.
FLOOR = (3, 11)

# The shipped prose that launches the engine on a consumer machine.
PROSE_GLOBS = ("commands/*.md", "skills/advisor-contracts/references/*.md")

# `python3 <path>.py` / `python <path>.py`, optional flags and quoting between the two. Matches
# the `uv run --project … python …/x.py` form as well: uv only enforces `requires-python` when the
# project it is pointed at declares one, so that form is not a substitute for an in-file guard.
_INVOCATION = re.compile(r"""\bpython3?\b\s+(?:-\S+\s+)*["']?([^\s"'|;&()]+\.py)""")

# Every engine script lives under this prefix, whatever precedes it in the prose
# (`engine/scripts/…`, `${CLAUDE_PLUGIN_ROOT}/engine/scripts/…`, an absolute path).
_SCRIPTS_MARKER = "engine/scripts/"

# Launched as a module (`python -m engine`), so no file-path invocation appears in the prose and
# the scan cannot find it. Declared here — with the same guard requirement as the derived set.
MODULE_ENTRYPOINTS = ("engine/__main__.py",)

# Known to be prose-launched by file path. The scan must find at least these, or `_INVOCATION`
# has regressed and the derived set is quietly shrinking again.
_EXPECTED_IN_PROSE = ("init/conclave_init.py", "lifecycle/session_init.py")


def _prose_entrypoints() -> tuple[dict[str, set[str]], list[str], int]:
    """Scripts the shipped prose launches by file path.

    Returns `(rel -> {docs that launch it}, unresolvable raw paths, docs scanned)`. The last two
    are what the anti-vacuity assertions read: a scan that resolves nothing, or silently drops a
    match it could not resolve, is the failure this derivation exists to prevent.
    """
    found: dict[str, set[str]] = {}
    unresolved: list[str] = []
    scanned = 0
    for glob in PROSE_GLOBS:
        for doc in sorted(REPO_ROOT.glob(glob)):
            scanned += 1
            # Fold shell line-continuations so a wrapped `uv run … \\\n  python …/x.py` matches.
            text = re.sub(r"\\\s*\n\s*", " ", doc.read_text(encoding="utf-8"))
            for match in _INVOCATION.finditer(text):
                raw = match.group(1)
                where = str(doc.relative_to(REPO_ROOT))
                if _SCRIPTS_MARKER not in raw:
                    unresolved.append(f"{where}: {raw}")
                    continue
                rel = raw.split(_SCRIPTS_MARKER)[-1]
                if not (SCRIPTS_ROOT / rel).is_file():
                    unresolved.append(f"{where}: {raw}")
                    continue
                found.setdefault(rel, set()).add(where)
    return found, unresolved, scanned


PROSE_ENTRYPOINTS, _UNRESOLVED, _DOCS_SCANNED = _prose_entrypoints()

# What every guard assertion below is parametrized over.
ENTRYPOINTS = tuple(sorted(set(PROSE_ENTRYPOINTS) | set(MODULE_ENTRYPOINTS)))


def test_prose_scan_is_not_vacuous() -> None:
    """A scan that finds nothing would make every guard assertion below pass by not running."""
    assert _DOCS_SCANNED > 0, f"no prose matched {PROSE_GLOBS} under {REPO_ROOT}"
    assert PROSE_ENTRYPOINTS, (
        f"scanned {_DOCS_SCANNED} prose files and found no `python …/<script>.py` invocation; "
        f"`_INVOCATION` no longer matches the shipped form"
    )


def test_prose_scan_finds_the_known_file_path_entrypoints() -> None:
    """A regex regression that halves the derived set must fail here, not ship silently."""
    missing = [rel for rel in _EXPECTED_IN_PROSE if rel not in PROSE_ENTRYPOINTS]
    assert not missing, (
        f"the prose scan missed known prose-launched entrypoints {missing}; found "
        f"{sorted(PROSE_ENTRYPOINTS)}"
    )


def test_every_prose_invocation_resolves_to_a_file() -> None:
    """An unresolvable match is a hole in the derivation, so it fails loudly rather than drops.

    Either the prose names a path that does not exist (a broken instruction on a consumer
    machine), or it launches a script outside `engine/scripts/` that this scan cannot check.
    Both need a human; neither may be silently skipped.
    """
    assert not _UNRESOLVED, (
        "prose launches `.py` paths this scan could not resolve to a file under "
        f"{SCRIPTS_ROOT}:\n  " + "\n  ".join(_UNRESOLVED)
    )


def _module(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _is_stdlib(name: str) -> bool:
    return name.split(".")[0] in sys.stdlib_module_names


def _int_tuple(node: ast.expr) -> tuple[int, ...] | None:
    if not isinstance(node, ast.Tuple):
        return None
    if not all(isinstance(e, ast.Constant) and isinstance(e.value, int) for e in node.elts):
        return None
    return tuple(e.value for e in node.elts)  # type: ignore[attr-defined]


def _body_refuses(node: ast.If) -> bool:
    """The body exits the process. A version test that falls through refuses nothing."""
    return any(
        isinstance(sub, ast.Raise)
        or (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "exit")
        for stmt in node.body
        for sub in ast.walk(stmt)
    )


def _guard_node(tree: ast.Module) -> ast.If | None:
    """The module-level version guard, selected **once** for every assertion below.

    Line number and floor must come from the same node, or a weakened guard can hide behind an
    unrelated version test: two helpers walking `tree.body` independently will happily bind to
    two different `if` statements. Matching on `version_info` alone is not enough either — an
    earlier feature-detect or `== (3, 11)` compatibility branch would shadow the real guard and
    the floor would be read off it. So the criterion is the whole refusal shape:
    `sys.version_info < <int tuple>` over a body that exits.
    """
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test = node.test
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            continue
        if not isinstance(test.ops[0], ast.Lt):
            continue
        if not (isinstance(test.left, ast.Attribute) and test.left.attr == "version_info"):
            continue
        if _int_tuple(test.comparators[0]) is None or not _body_refuses(node):
            continue
        return node
    return None


def _guard_floor(node: ast.If) -> tuple[int, ...] | None:
    """The version tuple the selected guard compares against."""
    test = node.test
    assert isinstance(test, ast.Compare)  # guaranteed by _guard_node
    return _int_tuple(test.comparators[0])


@pytest.mark.parametrize("rel", ENTRYPOINTS)
def test_entrypoint_has_version_guard(rel: str) -> None:
    """Every entrypoint refuses a sub-floor interpreter itself — no reliance on the caller."""
    tree = _module(SCRIPTS_ROOT / rel)
    assert _guard_node(tree) is not None, (
        f"{rel} has no module-level `sys.version_info` guard; a sub-floor interpreter will "
        f"reach PEP 604 annotations or an interactive prompt before failing"
    )


@pytest.mark.parametrize("rel", ENTRYPOINTS)
def test_guard_floor_matches_declared_floor(rel: str) -> None:
    node = _guard_node(_module(SCRIPTS_ROOT / rel))
    assert node is not None, f"{rel}: no guard (see test_entrypoint_has_version_guard)"
    assert _guard_floor(node) == FLOOR


@pytest.mark.parametrize("rel", ENTRYPOINTS)
def test_guard_precedes_anything_that_can_fail(rel: str) -> None:
    """The guard must run before the first first-party import and before the first def/class.

    Those are the two things measured to break below the floor: `enginelib` imports carry PEP 604
    at module level, and a `def` whose signature is evaluated at definition time does too.
    """
    tree = _module(SCRIPTS_ROOT / rel)
    guard_node = _guard_node(tree)
    assert guard_node is not None, f"{rel}: no guard (see test_entrypoint_has_version_guard)"
    guard = guard_node.lineno

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


# Mutation M11's shape: the real guard weakened to 3.8, with an earlier version test that reads
# like the floor but refuses nothing. Under the old two-independent-walks helpers the assertions
# bound to the decoy and the suite stayed green while the engine accepted Python 3.8.
_DECOYED_ENTRYPOINT = """\
import sys

if sys.version_info[:2] == (3, 11):
    pass

if sys.version_info < (3, 8):
    sys.stderr.write("too old\\n")
    sys.exit(1)
"""


def test_decoy_version_test_cannot_shadow_the_guard() -> None:
    """Both readings must come off the refusing guard, never off an earlier version test."""
    node = _guard_node(ast.parse(_DECOYED_ENTRYPOINT))
    assert node is not None
    assert _guard_floor(node) == (3, 8), "floor was read off the decoy, not the real guard"
    assert node.lineno == 6, "line was read off the decoy (line 3), not the real guard (line 6)"


def test_pyproject_floor_matches_guards() -> None:
    """A declared floor nobody enforces is a claim, not a constraint — keep the two in step."""
    text = (SCRIPTS_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^requires-python\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match, "pyproject.toml declares no requires-python"
    assert match.group(1) == ">=" + ".".join(str(p) for p in FLOOR)


def _sub_floor_interpreter() -> str | None:
    """An interpreter below FLOOR, if this machine has one.

    Resolved to an absolute path: candidates are found on the parent's PATH, but the behavioural
    test below runs them under a minimal `PATH=/usr/bin:/bin`. A bare `python3.10` from Homebrew
    would pass the probe here and then fail `execvpe` there, erroring instead of skipping.
    """
    for name in ("/usr/bin/python3", "python3.9", "python3.10"):
        candidate = shutil.which(name)
        if candidate is None:
            continue
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

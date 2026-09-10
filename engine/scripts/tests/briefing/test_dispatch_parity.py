"""The two copies of the briefing's section dispatch must not drift apart.

`scans/__init__.py` holds no registry — it is a docstring and `ScanCtx` (42 lines, no
`SECTIONS`, no `register()`, no `__all__`). Dispatch therefore exists as a hardcoded
dict literal in two places:

  * `briefing/render.py:build()`   — untimed, and reached only from tests
  * `briefing/__main__.py:main()`  — timed per step, and the one production ships

Adding a section means editing both, in lockstep, by hand. Nothing checks that today,
and the failure is silent in the direction that matters: a section wired only into
`render.py` passes every test that goes through `render.build`, and never appears in a
real briefing. This file is the lockstep check, written statically — it reads the two
literals rather than executing them, so it needs no instance, no fixture, and no clock.

Plan 057 T5b replaces both literals with one registry. Until then, this is the gate;
after it, this file should fail to find the literals and be deleted with the refactor.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SCANS_DIR = Path(__file__).resolve().parents[2] / "briefing" / "scans"
_RENDER_PY = _SCANS_DIR.parent / "render.py"
_MAIN_PY = _SCANS_DIR.parent / "__main__.py"


def _values_dict_keys(path: Path) -> list[str]:
    """The string keys of the `values: dict[str, str] = {...}` literal in *path*."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.AnnAssign):
            continue
        target = node.target
        if not (isinstance(target, ast.Name) and target.id == "values"):
            continue
        if not isinstance(node.value, ast.Dict):
            continue
        return [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    pytest.fail(f"no `values: dict[...] = {{...}}` literal found in {path.name}")


def _scan_modules_called(path: Path) -> set[str]:
    """Module names `m` for which *path* contains a call `m.build(...)`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    called: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "build"
            and isinstance(node.func.value, ast.Name)
        ):
            called.add(node.func.value.id)
    return called


def _public_scan_modules() -> set[str]:
    """Every `scans/*.py` exposing a public `build`. Privates (`_gh_cache`, `_specfm`)
    have no `build` and are excluded by that, not by their leading underscore."""
    modules: set[str] = set()
    for py in _SCANS_DIR.glob("*.py"):
        if py.name == "__init__.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        if any(
            isinstance(n, ast.FunctionDef) and n.name == "build"
            for n in tree.body
        ):
            modules.add(py.stem)
    return modules


def test_both_dispatches_carry_the_same_keys_in_the_same_order():
    """Order is asserted, not just membership.

    The template does not care about order, so an order difference is harmless
    output-wise — which is exactly why it is worth catching: it is evidence the two
    literals were edited independently, and the next edit is the one that diverges
    in substance.
    """
    render_keys = _values_dict_keys(_RENDER_PY)
    main_keys = _values_dict_keys(_MAIN_PY)
    assert render_keys == main_keys, (
        "the two dispatch literals disagree\n"
        f"  only in render.py:   {sorted(set(render_keys) - set(main_keys))}\n"
        f"  only in __main__.py: {sorted(set(main_keys) - set(render_keys))}"
    )


def test_every_public_scan_is_wired_into_the_production_path():
    """A scan reachable only from `render.build` never reaches a real briefing.

    `render.build` has no production caller — production is
    `briefing/__main__.py:main` -> `render.render_content`. A section wired into the
    former alone is a consumer without a producer, which this instance has shipped
    three times (2026-09-01).
    """
    missing = _public_scan_modules() - _scan_modules_called(_MAIN_PY)
    assert not missing, f"scan modules never called on the production path: {sorted(missing)}"


def test_every_public_scan_is_wired_into_the_render_path():
    missing = _public_scan_modules() - _scan_modules_called(_RENDER_PY)
    assert not missing, f"scan modules missing from render.build: {sorted(missing)}"


def test_the_dispatch_covers_every_scan_and_nothing_it_invents():
    """The key count is pinned to the module count so a stray key is visible.

    Two keys are not sections — `advisor` and `generated_at` are render metadata.
    Measured 2026-09-09: 15 public scans, 17 keys.
    """
    keys = set(_values_dict_keys(_MAIN_PY))
    non_section = {"advisor", "generated_at"}
    assert len(keys - non_section) == len(_public_scan_modules()), (
        f"{len(keys - non_section)} section keys against "
        f"{len(_public_scan_modules())} public scan modules"
    )

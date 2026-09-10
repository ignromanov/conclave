"""One list of sections, and the three ways it can still be wrong (plan 057 T5b).

This replaces `test_dispatch_parity.py`. That gate held two hardcoded dispatch literals
byte-equal by AST, because adding a section meant editing `render.py` and `__main__.py` in
lockstep and the failure was silent in the direction that matters: a section wired only into
`render.py` passed every test that went through `render.build` and never reached a briefing.

`briefing/sections.py` retires the lockstep problem by having one list. It does not retire
the drift — it moves it. A new `scans/*.py` with a public `build` that nobody registers is
invisible exactly as before, one level up. So this gate asserts what the registry cannot
enforce structurally:

  * every public scan is registered, and the registry invents none;
  * every key is a placeholder the template actually carries, in both directions;
  * neither consumer has quietly grown a second dispatch back.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from briefing.paths import templates_dir
from briefing.sections import META_KEYS, SECTIONS

_SCANS_DIR = Path(__file__).resolve().parents[2] / "briefing" / "scans"
_RENDER_PY = _SCANS_DIR.parent / "render.py"
_MAIN_PY = _SCANS_DIR.parent / "__main__.py"

# Digits included deliberately: `p0_blockers` is a key, and a `[a-zA-Z_]+` class silently
# reports the template as one placeholder short — an instrument manufacturing an absence.
_PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")


def _public_scan_modules() -> set[str]:
    """Every `scans/*.py` exposing a public `build`. Privates (`_gh_cache`, `_specfm`)
    have no `build` and are excluded by that, not by their leading underscore."""
    modules: set[str] = set()
    for py in _SCANS_DIR.glob("*.py"):
        if py.name == "__init__.py":
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        if any(isinstance(n, ast.FunctionDef) and n.name == "build" for n in tree.body):
            modules.add(py.stem)
    return modules


def _direct_build_calls(path: Path) -> set[str]:
    """Module names `m` for which *path* contains a literal call `m.build(...)`.

    A registry-driven consumer calls `section.scan.build(ctx)` — an attribute of an
    attribute — so any bare `queue.build(ctx)` here is a re-introduced dispatch.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.func.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "build"
        and isinstance(node.func.value, ast.Name)
    }


def test_every_public_scan_is_registered():
    """A scan file nobody registered renders nowhere, and nothing else says so."""
    registered = {s.scan.__name__.rsplit(".", 1)[-1] for s in SECTIONS}
    on_disk = _public_scan_modules()
    assert not on_disk - registered, (
        f"scans exist but are in no Section: {sorted(on_disk - registered)} — "
        "add them to briefing/sections.py:SECTIONS or they render nowhere"
    )
    assert not registered - on_disk, (
        f"SECTIONS names modules with no public build: {sorted(registered - on_disk)}"
    )


def test_keys_and_steps_are_unique():
    """Two sections sharing a key silently drop one; sharing a step misreports timing."""
    keys = [s.key for s in SECTIONS]
    steps = [s.step for s in SECTIONS]
    assert len(set(keys)) == len(keys), f"duplicate keys: {sorted(keys)}"
    assert len(set(steps)) == len(steps), f"duplicate steps: {sorted(steps)}"
    assert not set(keys) & set(META_KEYS), "a section key collides with a meta key"


def test_every_key_is_a_placeholder_the_template_carries():
    """Both directions. A key with no placeholder is computed and discarded; a
    placeholder with no key renders as the literal `{{name}}` to the reader, because
    `_substitute` falls back to the match rather than raising."""
    template = (templates_dir() / "briefing.md").read_text(encoding="utf-8")
    placeholders = set(_PLACEHOLDER_RE.findall(template))
    supplied = {s.key for s in SECTIONS} | set(META_KEYS)

    assert not supplied - placeholders, (
        f"keys the template never uses (computed and thrown away): "
        f"{sorted(supplied - placeholders)}"
    )
    assert not placeholders - supplied, (
        f"placeholders nothing supplies (render as literal braces): "
        f"{sorted(placeholders - supplied)}"
    )


def test_neither_consumer_has_grown_a_second_dispatch():
    """The reason the old gate existed. It is cheaper to keep asserting than to rediscover."""
    for path in (_RENDER_PY, _MAIN_PY):
        direct = _direct_build_calls(path)
        assert not direct, (
            f"{path.name} calls {sorted(direct)}.build() directly — the point of "
            "briefing/sections.py is that this list exists once"
        )

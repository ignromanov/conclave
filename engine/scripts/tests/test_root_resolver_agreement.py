"""test_root_resolver_agreement.py — the two DATA-root resolvers must answer alike.

The engine carries two `repo_root()` implementations: `enginelib.paths` (29 non-test
importers, all of engine/cmd and lifecycle) and `briefing.paths` (12, all of briefing/
and feedback/). They were ported from the same bash function and then drifted apart on
five separate axes — the env names honoured, whether the result is `.resolve()`d, what
the walk starts from, whether a symlinked `.claude` is accepted, and a module-level
cache in one of them. `feedback_verify.py` imports `repo_root` from one and
`project_root` from the other, so a single call site can straddle the disagreement.

Nothing in the suite compared them, because `conftest.ai_root` pinned BOTH env vars to
the same tree: under that fixture every resolver agrees by construction, and the
divergence is unreachable. These tests deliberately do not use that fixture.

Each case runs in a subprocess with every root-steering variable scrubbed, because the
divergence lives in exactly the code paths that read the ambient environment and the
importing module's own location — neither is controllable in-process, and a
monkeypatched approximation would be testing the approximation.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]

# Runs inside the subprocess: call both resolvers, report answer-or-exception for each.
_PROBE = r"""
import json, sys
out = {}
for name, mod, fn in (
    ("enginelib", "enginelib.paths", "repo_root"),
    ("briefing", "briefing.paths", "repo_root"),
):
    try:
        m = __import__(mod, fromlist=["x"])
        out[name] = {"ok": True, "value": str(getattr(m, fn)())}
    except Exception as exc:
        out[name] = {"ok": False, "value": type(exc).__name__}
print(json.dumps(out))
"""

_SCRUB = ("CONCLAVE_AI_ROOT", "VOIDPAY_AI_ROOT", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")


def _both_resolvers(env_overrides: dict[str, str], cwd: Path) -> dict[str, dict]:
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
    env["PYTHONPATH"] = str(_SCRIPTS)
    env.update(env_overrides)
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"probe crashed: {proc.stderr}"
    return json.loads(proc.stdout)


def _make_data_tree(base: Path, name: str = ".conclave") -> Path:
    """Minimal DATA root: ops/ + .claude/ + the roster.yaml that says it is an instance."""
    root = base / name
    (root / "ops").mkdir(parents=True)
    (root / ".claude").mkdir(parents=True)
    (root / "roster.yaml").write_text("github: {}\n", encoding="utf-8")
    return root


def _assert_agree(result: dict[str, dict], what: str) -> None:
    a, b = result["enginelib"], result["briefing"]
    assert a == b, (
        f"{what}: enginelib.paths.repo_root() and briefing.paths.repo_root() disagree — "
        f"enginelib={a['value']!r} ({'ok' if a['ok'] else 'raised'}), "
        f"briefing={b['value']!r} ({'ok' if b['ok'] else 'raised'})"
    )


def test_explicit_data_root_agrees(tmp_path):
    """CONCLAVE_AI_ROOT set: the plain case both resolvers claim to honour."""
    root = _make_data_tree(tmp_path)
    _assert_agree(
        _both_resolvers({"CONCLAVE_AI_ROOT": str(root)}, cwd=tmp_path),
        "explicit CONCLAVE_AI_ROOT",
    )


def test_data_root_reached_through_a_symlink_agrees(tmp_path):
    """A symlinked path to the same tree. One resolver `.resolve()`s, the other does not,
    so downstream string comparisons of the same directory can come out unequal."""
    _make_data_tree(tmp_path / "real")
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "real")
    _assert_agree(
        _both_resolvers({"CONCLAVE_AI_ROOT": str(link / ".conclave")}, cwd=tmp_path),
        "CONCLAVE_AI_ROOT via symlink",
    )


def test_plugin_mode_agrees(tmp_path):
    """Plugin mode: CLAUDE_PROJECT_DIR only. Both are meant to derive `$CPD/.conclave`."""
    _make_data_tree(tmp_path)
    _assert_agree(
        _both_resolvers({"CLAUDE_PROJECT_DIR": str(tmp_path)}, cwd=tmp_path),
        "plugin mode (CLAUDE_PROJECT_DIR only)",
    )


def test_walk_from_inside_a_data_tree_agrees(tmp_path):
    """No env at all, process standing inside a DATA root. One resolver walks up from the
    cwd and finds it; the other walks up from its own __file__ and finds the engine
    checkout instead — a different tree entirely, and the CODE-side orphan at that."""
    root = _make_data_tree(tmp_path)
    _assert_agree(
        _both_resolvers({}, cwd=root),
        "walk from inside a DATA tree",
    )


def test_no_root_anywhere_agrees(tmp_path):
    """No env, cwd outside any DATA tree. Absence must be reported the same way by both —
    a resolver that answers here is answering about some other project's tree."""
    (tmp_path / "empty").mkdir()
    _assert_agree(
        _both_resolvers({}, cwd=tmp_path / "empty"),
        "no root anywhere",
    )


def test_legacy_alias_alone_is_not_silently_honoured(tmp_path):
    """VOIDPAY_AI_ROOT set without CONCLAVE_AI_ROOT: one resolver honours it, the other
    ignores it, so the same process reads two different trees. Whatever the engine
    decides the alias means, both resolvers must mean the same thing by it."""
    root = _make_data_tree(tmp_path)
    _assert_agree(
        _both_resolvers({"VOIDPAY_AI_ROOT": str(root)}, cwd=tmp_path),
        "legacy alias alone",
    )


def test_a_code_shaped_tree_is_not_taken_for_a_data_root(tmp_path):
    """ops/ + .claude/ without a roster.yaml is the CODE checkout's shape, not an
    instance's. The engine repo carries both (ops/ holds ops/SCHEMA.md), so the old
    marker matched the tree the resolver was reading itself from and DATA was written
    into CODE whenever the environment was empty (GH#29). Both resolvers must refuse."""
    code_like = tmp_path / "checkout"
    (code_like / "ops").mkdir(parents=True)
    (code_like / ".claude").mkdir(parents=True)
    result = _both_resolvers({}, cwd=code_like)
    _assert_agree(result, "CODE-shaped tree")
    assert result["enginelib"]["ok"] is False, (
        "a tree with no roster.yaml was accepted as a DATA root: "
        f"{result['enginelib']['value']!r}"
    )

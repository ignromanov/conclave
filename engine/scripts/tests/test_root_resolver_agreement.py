"""test_root_resolver_agreement.py — the DATA-root resolver must answer a written spec.

The engine used to carry two `repo_root()` implementations — `enginelib.paths` and
`briefing.paths` — ported from the same bash function and then drifted on five axes: the
env names honoured, whether the result is `.resolve()`d, what the walk starts from,
whether a symlinked `.claude` is accepted, and a module-level cache in one of them. This
file was written to compare them, and every case asserted `enginelib == briefing`.

The two were then unified: `briefing.paths` now re-exports `enginelib.paths.repo_root`,
so `enginelib.paths.repo_root is briefing.paths.repo_root` is True. The comparison did
not become wrong — it became UNABLE TO BE WRONG. `f() == f()` inside one subprocess holds
whatever `f` does, so six of the seven cases here passed with a resolver replaced by
`return Path("/tmp/MUTANT-NOT-A-ROOT")`; only the one case carrying an absolute assertion
reddened. A guard that survives its own subject is indistinguishable from a working one
by colour alone, which is the shape of GH#132 and GH#215.

So the cases below assert the RESOLVED VALUE, not agreement, and the seven behaviours
they pin — measured against the implementation, then written down here — are the spec
this resolver did not previously have anywhere:

  1. `CONCLAVE_AI_ROOT` is honoured verbatim, resolved.
  2. A symlinked path resolves THROUGH to the real directory. Load-bearing: on macOS the
     unresolved and resolved forms of one directory differ by the `/private` prefix
     alone, so a comparison between a briefing-derived path and an enginelib-derived one
     was false for the same tree.
  3. Plugin mode derives `$CLAUDE_PROJECT_DIR/.conclave`.
  4. With no env at all the walk starts from the cwd and finds the enclosing DATA root.
  5. Outside any DATA tree the resolver RAISES. Answering here means answering about some
     other project's tree.
  6. `VOIDPAY_AI_ROOT` alone stops the process with a message naming the alias; set
     beside `CONCLAVE_AI_ROOT` it is inert and the current name wins.
  7. `ops/` + `.claude/` without a `roster.yaml` is the CODE checkout's shape, not an
     instance's, and is refused (GH#29). The engine repo carries both, so the old marker
     matched the tree the resolver was reading itself from, and DATA was written into
     CODE whenever the environment was empty.

Agreement is still enforced, but by identity (`is`) rather than by equality: that
assertion fails the moment a second implementation reappears, which equality could not.

Each case runs in a subprocess with every root-steering variable scrubbed, because the
behaviour lives in exactly the code paths that read the ambient environment and the
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

# Runs inside the subprocess: resolve, report answer-or-exception.
_PROBE = r"""
import json
import enginelib.paths as m
try:
    out = {"ok": True, "value": str(m.repo_root()), "msg": ""}
except Exception as exc:
    out = {"ok": False, "value": type(exc).__name__, "msg": str(exc)}
print(json.dumps(out))
"""

# Runs inside the subprocess: report whether the two modules expose one function object.
_IDENTITY_PROBE = r"""
import json
import enginelib.paths as e
import briefing.paths as b
print(json.dumps({"same": e.repo_root is b.repo_root}))
"""

_SCRUB = ("CONCLAVE_AI_ROOT", "VOIDPAY_AI_ROOT", "CLAUDE_PROJECT_DIR", "CLAUDE_PLUGIN_ROOT")


def _run_probe(probe: str, env_overrides: dict[str, str], cwd: Path) -> dict:
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
    env["PYTHONPATH"] = str(_SCRIPTS)
    env.update(env_overrides)
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(cwd), env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"probe crashed: {proc.stderr}"
    return json.loads(proc.stdout)


def _resolve(env_overrides: dict[str, str], cwd: Path) -> dict:
    return _run_probe(_PROBE, env_overrides, cwd)


def _assert_resolves_to(result: dict, expected: Path, what: str) -> None:
    assert result["ok"], (
        f"{what}: expected {str(expected)!r}, but repo_root() raised "
        f"{result['value']}"
    )
    assert result["value"] == str(expected), (
        f"{what}: repo_root() returned {result['value']!r}, expected {str(expected)!r}"
    )


def _assert_refuses(result: dict, what: str, because: str | None = None) -> None:
    assert not result["ok"], (
        f"{what}: repo_root() must refuse to answer, but returned {result['value']!r}"
    )
    assert result["value"] == "RuntimeError", (
        f"{what}: expected RuntimeError, got {result['value']}"
    )
    # A bare `RuntimeError` is satisfied by any refusal, including one raised for an
    # unrelated reason. Where a case exists to pin a SPECIFIC refusal, pin its wording.
    if because is not None:
        assert because in result["msg"], (
            f"{what}: refused, but not for the expected reason — the message should "
            f"mention {because!r}, got {result['msg']!r}"
        )


def _make_data_tree(base: Path, name: str = ".conclave") -> Path:
    """Minimal DATA root: ops/ + .claude/ + the roster.yaml that says it is an instance."""
    root = base / name
    (root / "ops").mkdir(parents=True)
    (root / ".claude").mkdir(parents=True)
    (root / "roster.yaml").write_text("github: {}\n", encoding="utf-8")
    return root


def test_briefing_reexports_the_single_implementation():
    """One implementation, re-exported — not two that happen to agree.

    This is the assertion the old `enginelib == briefing` comparison was reaching for and
    could not make: equality holds when both sides are the same object AND when both are
    separately broken in the same way, so it could not detect a re-fork. Identity can.
    """
    result = _run_probe(_IDENTITY_PROBE, {}, _SCRIPTS)
    assert result["same"], (
        "briefing.paths.repo_root is no longer enginelib.paths.repo_root — a second "
        "DATA-root implementation has reappeared. Two ports of this function drifted on "
        "five axes once already (GH#107); re-export it rather than re-implementing it."
    )


def test_explicit_data_root_is_honoured_verbatim(tmp_path):
    """CONCLAVE_AI_ROOT names the DATA root outright; the resolver returns exactly it."""
    root = _make_data_tree(tmp_path)
    _assert_resolves_to(
        _resolve({"CONCLAVE_AI_ROOT": str(root)}, cwd=tmp_path),
        root.resolve(),
        "explicit CONCLAVE_AI_ROOT",
    )


def test_data_root_reached_through_a_symlink_resolves_to_the_real_path(tmp_path):
    """A symlinked path must resolve THROUGH to the real directory, not be echoed back.

    Callers compare these paths as strings. When one producer resolved and another did
    not, the two spellings of one directory compared unequal and callers had begun
    sprinkling `.resolve()` at the comparison sites instead of at the source.
    """
    real = _make_data_tree(tmp_path / "real")
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "real")
    _assert_resolves_to(
        _resolve({"CONCLAVE_AI_ROOT": str(link / ".conclave")}, cwd=tmp_path),
        real.resolve(),
        "CONCLAVE_AI_ROOT via symlink",
    )


def test_plugin_mode_derives_the_data_root_under_the_project_dir(tmp_path):
    """Plugin mode: CLAUDE_PROJECT_DIR only, and the DATA root is `$CPD/.conclave`."""
    root = _make_data_tree(tmp_path)
    _assert_resolves_to(
        _resolve({"CLAUDE_PROJECT_DIR": str(tmp_path)}, cwd=tmp_path),
        root.resolve(),
        "plugin mode (CLAUDE_PROJECT_DIR only)",
    )


def test_walk_from_inside_a_data_tree_finds_the_enclosing_root(tmp_path):
    """No env at all: the walk starts from the cwd, not from the module's own location.

    A resolver walking up from its own `__file__` finds the engine checkout instead — a
    different tree entirely, and the CODE-side orphan at that (GH#87).
    """
    root = _make_data_tree(tmp_path)
    _assert_resolves_to(
        _resolve({}, cwd=root),
        root.resolve(),
        "walk from inside a DATA tree",
    )


def test_no_root_anywhere_is_refused(tmp_path):
    """Outside any DATA tree the resolver raises rather than guessing."""
    empty = tmp_path / "empty"
    empty.mkdir()
    _assert_refuses(_resolve({}, cwd=empty), "no root anywhere")


def test_legacy_alias_alone_is_refused_by_name(tmp_path):
    """VOIDPAY_AI_ROOT without CONCLAVE_AI_ROOT stops the process, naming the alias.

    Six call sites honoured the alias and the seventh — the resolver the other six were
    meant to defer to — ignored it, so one process could write feedback into one tree
    while reading advisors from another, with no error anywhere because every individual
    call succeeded. The answer was a loud refusal rather than a silent precedence rule.

    The refusal's WORDING is asserted, not merely its type. `RuntimeError` alone is also
    what an unrelated failure raises here: a mutation that adds the alias back into the
    env chain leaves this case green, because the guard above it raises first and the
    mutated branch is unreachable. That mutant is equivalent, but the assertion that
    survived it was weaker than its name promised.
    """
    root = _make_data_tree(tmp_path)
    _assert_refuses(
        _resolve({"VOIDPAY_AI_ROOT": str(root)}, cwd=tmp_path),
        "legacy alias alone",
        because="VOIDPAY_AI_ROOT is set but CONCLAVE_AI_ROOT is not",
    )


def test_legacy_alias_is_inert_beside_the_current_one(tmp_path):
    """Both set: CONCLAVE_AI_ROOT wins and the alias is ignored, not merged or preferred.

    `check_legacy_data_root_env` documents the alias as "inert and ignored" when set
    alongside the current name — the arrangement the test fixtures carried for years —
    but nothing asserted it, so the precedence between two trees named at once rested on
    a docstring. Two DIFFERENT trees are used here deliberately: with one tree the
    assertion would hold whichever variable won.
    """
    current = _make_data_tree(tmp_path / "current")
    legacy = _make_data_tree(tmp_path / "legacy")
    _assert_resolves_to(
        _resolve(
            {"CONCLAVE_AI_ROOT": str(current), "VOIDPAY_AI_ROOT": str(legacy)},
            cwd=tmp_path,
        ),
        current.resolve(),
        "both roots set",
    )


def test_a_code_shaped_tree_is_not_taken_for_a_data_root(tmp_path):
    """ops/ + .claude/ without a roster.yaml is the CODE checkout's shape (GH#29)."""
    code_like = tmp_path / "checkout"
    (code_like / "ops").mkdir(parents=True)
    (code_like / ".claude").mkdir(parents=True)
    _assert_refuses(_resolve({}, cwd=code_like), "CODE-shaped tree")


def test_engine_root_falls_back_to_its_own_location_when_the_env_is_absent(tmp_path):
    """The CODE-root fallback must be reachable — a branch that never runs is not a branch.

    `engine_root()` reads CONCLAVE_ENGINE_ROOT and only otherwise derives the path from
    `__file__`. That variable is exported by the SessionStart hook and baked into
    `.claude/settings.json`, so in every ordinary run — and in this suite, which
    deliberately does not scrub it — the fallback is dead code. pytest carried the same
    shape for years in its filesystem-root guard (pytest-dev/pytest#10506): the guard
    compared against `"/"` where the platform produced `"\\"`, never fired, and nothing
    failed to reveal it. This test is the only place the fallback executes.
    """
    probe = (
        "import json, enginelib.paths as m; "
        "print(json.dumps({'value': str(m.engine_root())}))"
    )
    env = {k: v for k, v in os.environ.items() if k not in _SCRUB}
    env.pop("CONCLAVE_ENGINE_ROOT", None)
    env["PYTHONPATH"] = str(_SCRIPTS)
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=str(tmp_path), env=env, capture_output=True, text=True, timeout=60,
    )
    assert proc.returncode == 0, f"probe crashed: {proc.stderr}"
    assert json.loads(proc.stdout)["value"] == str(_SCRIPTS.parent), (
        "engine_root() with CONCLAVE_ENGINE_ROOT unset must derive the engine/ dir from "
        "its own file location"
    )


def test_pytest_is_rooted_in_the_tree_this_file_lives_in(pytestconfig):
    """rootdir must be this checkout's root, and the config must be its own pytest.ini.

    `get_dirs_from_args()` silently drops path arguments that do not exist and
    `locate_config()` takes the first config found walking up from each surviving one, so
    an invocation can be rooted somewhere other than intended with no diagnostic — the
    shape that once left `feedback/tests` uncollected while the run reported success
    (GH#99). pytest prints rootdir in every run's header for exactly this reason; an
    assertion is the same disclosure in a form that fails.

    This pins only the half pytest controls. The other half — CONCLAVE_ENGINE_ROOT
    naming a DIFFERENT checkout, so shipped-asset tests read a neighbouring branch — is
    GH#103, and it wants a collection-time gate that names both roots and both exposure
    paths, not an assertion in one test file.
    """
    assert pytestconfig.rootpath == _SCRIPTS.parents[1], (
        f"pytest rootdir is {pytestconfig.rootpath}, but this file lives under "
        f"{_SCRIPTS.parents[1]} — the suite is rooted in a different checkout"
    )
    assert pytestconfig.inipath == _SCRIPTS.parents[1] / "pytest.ini", (
        f"pytest read its config from {pytestconfig.inipath}, not this checkout's "
        f"pytest.ini — testpaths, pythonpath and addopts are all coming from elsewhere"
    )

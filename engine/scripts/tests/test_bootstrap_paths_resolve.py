"""test_bootstrap_paths_resolve.py — shipped bash snippets must name paths that exist.

The class this closes (#137, and the bootstrap half of #61): a shipped surface prescribes a
command, the command builds a path out of shell variables, and nothing ever evaluates it. The
`${CLAUDE_PLUGIN_ROOT:-.}` bootstrap was re-reported eleven times across two triage windows
because it fails only in the deployment nobody runs the suite in — an installed instance, where
CLAUDE_PLUGIN_ROOT is unset and cwd is the consumer checkout, which has no engine/ in it.

The gate evaluates the assignments in each fence with real bash, under exactly that condition,
and asserts every engine path the fence then names exists. Two token shapes are checked, because
between them they cover every way a fence reaches the engine and nothing else:

  * PYTHONPATH="<token>"   — the import root
  * "<token>.py"           — a script the fence executes

`-R "$OWNER/$(...)"` and other var-rooted strings that are not filesystem paths are therefore
out of scope by construction, rather than by an exclusion list that would rot.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
ENGINE_ROOT = pathlib.Path(__file__).resolve().parents[2]

_FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_PYTHONPATH = re.compile(r'PYTHONPATH="([^"]+)"')
_SCRIPT = re.compile(r'"([^"]*\.py)"')


def _surfaces() -> list[pathlib.Path]:
    """Every shipped markdown surface that prescribes a command."""
    out: list[pathlib.Path] = []
    for sub in ("commands", "skills"):
        base = REPO_ROOT / sub
        if base.is_dir():
            out.extend(sorted(base.rglob("*.md")))
    return out


def _engine_tokens(fence: str) -> list[str]:
    """The tokens in one fence that are meant to resolve to a path inside the engine."""
    return _PYTHONPATH.findall(fence) + _SCRIPT.findall(fence)


def _cases() -> list[tuple[str, str, str]]:
    """(surface, assignment prelude, token) for every engine path a shipped fence names."""
    cases: list[tuple[str, str, str]] = []
    for path in _surfaces():
        for fence in _FENCE.findall(path.read_text(encoding="utf-8")):
            tokens = _engine_tokens(fence)
            if not tokens:
                continue
            prelude = "\n".join(
                line for line in fence.splitlines() if _ASSIGNMENT.match(line.strip())
            )
            rel = str(path.relative_to(REPO_ROOT))
            for token in tokens:
                cases.append((rel, prelude, token))
    return cases


CASES = _cases()


def test_the_gate_has_subjects():
    """A gate that silently matches nothing is the defect it is meant to catch."""
    assert CASES, "no shipped bash fence names an engine path — the extractor is broken"


@pytest.mark.parametrize(
    ("surface", "prelude", "token"),
    CASES,
    ids=[f"{s}::{t}" for s, _, t in CASES],
)
def test_shipped_snippet_path_exists(surface, prelude, token, tmp_path):
    """Every engine path a shipped fence names resolves, in an installed instance.

    Installed instance = CLAUDE_PLUGIN_ROOT unset (Claude Code does not export it to the
    SessionStart hook, CC #27145/#39550), CONCLAVE_ENGINE_ROOT exported by the hook, and cwd
    the consumer checkout — which has no engine/ directory.
    """
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_PLUGIN_ROOT"}
    env["CONCLAVE_ENGINE_ROOT"] = str(ENGINE_ROOT)

    result = subprocess.run(
        ["bash", "-c", f'{prelude}\nprintf "%s" "{token}"'],
        capture_output=True,
        text=True,
        cwd=tmp_path,          # a consumer checkout: no engine/ here
        env=env,
        check=False,
    )
    assert result.returncode == 0, (
        f"{surface}: the fence's own assignments do not evaluate: {result.stderr.strip()}"
    )

    resolved = pathlib.Path(result.stdout)
    assert resolved.exists(), (
        f"{surface} prescribes {token!r}, which resolves to {result.stdout!r} — "
        f"a path that does not exist. In an installed instance CLAUDE_PLUGIN_ROOT is unset, "
        f"so a `${{CLAUDE_PLUGIN_ROOT:-.}}` fallback lands in the consumer checkout. "
        f"The engine root is CONCLAVE_ENGINE_ROOT (the engine/ dir itself — "
        f"docs/architecture/instance-contract.md §2, locked 1af117c)."
    )

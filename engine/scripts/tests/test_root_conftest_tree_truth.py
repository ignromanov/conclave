"""tests/test_root_conftest_tree_truth.py — the suite's assets come from its own tree (#103, #86).

`pytest.ini` pins the code under test to this checkout: `pythonpath` is rootdir-relative,
so a run inside a git worktree imports that worktree's `enginelib`. `CONCLAVE_ENGINE_ROOT`
is exported by the SessionStart hook and names the main checkout. Nothing reconciled them,
so a worktree run read its own code against another tree's shipped assets — a false red in
one direction, a false green in the other, decided by which branch an unrelated third
checkout happened to be sitting on.

**On what these tests can and cannot show.** The invariant test below passes in this
checkout whether or not the fix is present, because here the derived root and the ambient
root are the same directory — the dogfooding instance cannot exhibit its own topology
defect. It is kept because it is the statement of the contract and it *does* go red in a
worktree, which is where the defect lives. The tests that can fail here are the subprocess
ones: they build a synthetic tree, poison the environment against it, and run a real pytest
inside it, so the disagreement the main checkout cannot produce is manufactured on demand.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import enginelib

ENGINE_ROOT_VAR = "CONCLAVE_ENGINE_ROOT"

# repo root ← tests ← scripts ← engine ← <root>
_REPO_ROOT = Path(__file__).resolve().parents[3]
_ROOT_CONFTEST = _REPO_ROOT / "conftest.py"


def test_asset_root_is_the_tree_the_code_came_from():
    """The contract in one line: one run, one checkout.

    enginelib/__init__.py → enginelib → scripts → engine, so parents[2] is the engine
    root of whichever tree pytest actually imported. If the asset root names a different
    one, every `engine_root()`-derived resolver — templates_dir, forge_dir, skills_dir —
    reads a tree whose code is not running.
    """
    code_tree = Path(enginelib.__file__).resolve().parents[2]
    asset_tree = Path(os.environ[ENGINE_ROOT_VAR]).resolve()

    assert asset_tree == code_tree, (
        f"the suite is running {code_tree}'s code against {asset_tree}'s assets — "
        f"two checkouts in one run"
    )


def _synthetic_tree(tmp_path: Path) -> Path:
    """A minimal tree carrying the real root conftest, and nothing else it needs.

    The conftest is standalone by design (stdlib only, derives from its own __file__),
    so copying the single file reproduces the mechanism exactly rather than approximating
    it. Copied, not imported: the point is to run it as *some other tree's* root.
    """
    tree = tmp_path / "checkout"
    (tree / "engine").mkdir(parents=True)
    (tree / "conftest.py").write_text(_ROOT_CONFTEST.read_text(encoding="utf-8"), encoding="utf-8")
    # The real suite runs under `-q` (pytest.ini addopts). The header hook must survive
    # it, so the synthetic tree is given the same flag rather than a friendlier one.
    (tree / "pytest.ini").write_text(
        "[pytest]\naddopts = -q -p no:randomly\n", encoding="utf-8"
    )
    (tree / "test_probe.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "def test_probe():\n"
        f"    assert Path(os.environ[{ENGINE_ROOT_VAR!r}]).resolve() == "
        "Path(__file__).resolve().parent / 'engine'\n",
        encoding="utf-8",
    )
    return tree


def _run_pytest(tree: Path, ambient: str | None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != ENGINE_ROOT_VAR}
    if ambient is not None:
        env[ENGINE_ROOT_VAR] = ambient
    return subprocess.run(
        [sys.executable, "-m", "pytest", "test_probe.py", "-q"],
        cwd=str(tree), env=env, capture_output=True, text=True,
    )


def test_a_foreign_ambient_root_does_not_reach_the_tests(tmp_path):
    """The defect itself: another checkout's root exported into a run of this one."""
    tree = _synthetic_tree(tmp_path)
    foreign = tmp_path / "some-other-checkout" / "engine"
    foreign.mkdir(parents=True)

    r = _run_pytest(tree, ambient=str(foreign))

    assert r.returncode == 0, (
        f"the foreign root reached the tests:\n{r.stdout}\n{r.stderr}"
    )


def test_the_correction_is_announced_in_a_channel_q_does_not_hide(tmp_path):
    """A corrected run says so, or the correction is as invisible as the defect was.

    The synthetic tree runs under the same `-q` the real suite does, which is the whole
    point: a `print` at conftest import and a `pytest_report_header` both passed review
    and both failed this assertion, because `-q` hides one and capture swallows the
    other on a passing run.
    """
    tree = _synthetic_tree(tmp_path)
    foreign = tmp_path / "some-other-checkout" / "engine"
    foreign.mkdir(parents=True)

    r = _run_pytest(tree, ambient=str(foreign))
    shown = r.stdout + r.stderr

    assert str(foreign) in shown and str(tree / "engine") in shown, (
        f"the correction named neither root it compared:\n{shown}"
    )
    assert "SessionStart" in shown, (
        "the message must say where the variable comes from, or the next reader goes "
        f"looking in their shell profile:\n{shown}"
    )


def test_an_agreeing_root_is_not_announced(tmp_path):
    """Silence on the normal case. A line printed every run is a line nobody reads."""
    tree = _synthetic_tree(tmp_path)

    r = _run_pytest(tree, ambient=str(tree / "engine"))

    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "names another checkout" not in (r.stdout + r.stderr), (
        f"announced a correction it did not make:\n{r.stdout}{r.stderr}"
    )


def test_an_absent_ambient_root_is_still_pinned(tmp_path):
    """CI exports nothing, so the unset case is the one CI actually runs.

    Left unset the resolver falls through to its own `Path(__file__)` guess, which is a
    second answer to a question that must have one. The export happens either way.
    """
    tree = _synthetic_tree(tmp_path)

    r = _run_pytest(tree, ambient=None)

    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "names another checkout" not in (r.stdout + r.stderr)

"""test_project_unification.py — Wave 2 gate: single root uv project (spec 099 Task 2.1)."""
import subprocess
import sys
import tomllib
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent  # engine/scripts


def test_single_root_pyproject():
    assert (SCRIPTS / "pyproject.toml").is_file()
    assert not (SCRIPTS / "briefing" / "pyproject.toml").exists()
    assert not (SCRIPTS / "feedback" / "pyproject.toml").exists()
    assert not (SCRIPTS / "briefing" / "uv.lock").exists()
    assert not (SCRIPTS / "feedback" / "uv.lock").exists()


def test_root_deps_absorb_subprojects():
    data = tomllib.loads((SCRIPTS / "pyproject.toml").read_text())
    deps = " ".join(data["project"]["dependencies"])
    for pkg in ("python-frontmatter", "pydantic", "ruamel.yaml", "PyYAML"):
        assert pkg.lower() in deps.lower()
    # requires-python is asserted by tests/test_python_floor.py, which ties it to the guards that
    # actually enforce it. A second hardcoded literal here is how the floor drifted out of step
    # with the code in the first place — this test owns dependency absorption, not the floor.


def test_engine_module_runs():
    r = subprocess.run(
        [sys.executable, "-m", "engine", "--help"],
        cwd=SCRIPTS, capture_output=True, text=True,
    )
    assert r.returncode == 0
    assert "post-commit" in r.stdout

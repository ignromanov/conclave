"""The dispatcher says so when it is running a tree the caller is not standing in (GH#126).

These run a real subprocess with a real import path and a real cwd, because the defect is
made of exactly those two things. The mismatch is manufactured the way the `.pth` file makes
it in life: `PYTHONPATH` pins one checkout while the process stands in another.

Two properties matter as much as the warning itself:

* it goes to **stderr**, so it cannot corrupt the machine-readable stdout GH#108 is asking for;
* it does **not** change the exit code. Per the design's error-handling rule, a non-zero exit
  from a `!`-block aborts the whole command load — replacing a diagnosable warning with a
  missing command, which is a worse version of the silence being cured.
"""
from pathlib import Path

from tests.cmd.helpers import run_engine

# parents[0]=cmd  parents[1]=tests  parents[2]=scripts  parents[3]=engine  parents[4]=repo
_SCRIPTS = Path(__file__).resolve().parents[2]
_REPO = Path(__file__).resolve().parents[4]


def _elsewhere_checkout(tmp_path: Path) -> Path:
    """A second checkout, and a working directory *inside* it but below its root.

    Below the root on purpose: `python -m` puts cwd on `sys.path[0]`, and a cwd holding an
    `engine/` directory would let the import resolve there as a namespace package instead of
    through the pin — the test would then fail for a reason that has nothing to do with GH#126.
    """
    root = tmp_path / "other-checkout"
    (root / "engine" / "scripts" / "engine").mkdir(parents=True)
    (root / "engine" / "scripts" / "engine" / "__main__.py").write_text("")
    work = root / "work"
    work.mkdir()
    return work


def test_warns_on_stderr_when_the_running_tree_is_not_the_caller_s_tree(tmp_path):
    work = _elsewhere_checkout(tmp_path)

    r = run_engine(
        "--help",
        cwd=str(work),
        env={
            "PYTHONPATH": str(_SCRIPTS),
            "CONCLAVE_RUN_LOG_DIR": str(tmp_path / "run-log"),
        },
    )

    assert str(_REPO) in r.stderr, f"the running tree is not named:\n{r.stderr}"
    assert str(work.parent) in r.stderr, f"the caller's tree is not named:\n{r.stderr}"
    assert "PYTHONPATH" in r.stderr
    assert "WARNING" not in r.stdout, "the warning must not pollute machine-readable stdout"


def test_the_warning_does_not_change_the_exit_code(tmp_path):
    work = _elsewhere_checkout(tmp_path)

    r = run_engine(
        "--help",
        cwd=str(work),
        env={
            "PYTHONPATH": str(_SCRIPTS),
            "CONCLAVE_RUN_LOG_DIR": str(tmp_path / "run-log"),
        },
    )

    # Both halves, or this passes vacuously: with no warning emitted at all the exit code is
    # trivially unchanged, and the test could never fail for the reason it is named after.
    assert "not the tree you are standing in" in r.stderr, r.stderr
    assert r.returncode == 0, f"exit {r.returncode}, stderr:\n{r.stderr}"


def test_silent_when_the_caller_stands_in_the_tree_being_run(tmp_path):
    """The negative control. Without it, a detector that warns unconditionally would pass
    every assertion above."""
    r = run_engine(
        "--help",
        cwd=str(_SCRIPTS),
        env={
            "PYTHONPATH": str(_SCRIPTS),
            "CONCLAVE_RUN_LOG_DIR": str(tmp_path / "run-log"),
        },
    )

    assert "not the tree you are standing in" not in r.stderr, r.stderr

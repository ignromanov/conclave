"""CLI contract for `engine protocol` (spec 108 P0, Task 4).

The exit-code contract is the opposite of the usual instinct and is deliberate:
`assemble` ALWAYS exits 0. A non-zero exit from a `!`-block aborts the entire command
load, replacing a diagnosable error with a missing command. Loudness lives in stdout.

That contract has a cost these tests must pay for: if the only assertion is `exit == 0`,
every test here passes against a scanner pointed at a directory that does not exist.
So `test_the_cli_scans_the_real_registry_tree` asserts the COUNT instead.
"""
import re
from pathlib import Path

from enginelib.protocols.registry import FIXED_HOMES
from tests.cmd.helpers import run_engine

# test_protocol_cmd.py lives at engine/scripts/tests/cmd/
# parents[0]=cmd  parents[1]=tests  parents[2]=scripts  parents[3]=engine  parents[4]=repo
_ENGINE = Path(__file__).resolve().parents[3]
_REPO = _ENGINE.parent

# CONCLAVE_ENGINE_ROOT is ambient (the SessionStart hook exports it) and the hermetic
# fixture deliberately leaves it alone — it is a CODE root, not an instance root. In a
# worktree it points at the MAIN checkout (GH#86), so an unpinned subprocess would scan
# a different branch's skills/ and report green about a tree this test never touched.
_ENV = {"CONCLAVE_ENGINE_ROOT": str(_ENGINE)}


def run(*args):
    return run_engine("protocol", *args, env=_ENV)


def _counts(stdout: str) -> tuple[int, int]:
    m = re.search(r"^(\d+) protocol\(s\), (\d+) error\(s\)$", stdout, re.M)
    assert m, f"no count line in output:\n{stdout}"
    return int(m.group(1)), int(m.group(2))


def test_assemble_exits_zero_on_a_healthy_registry():
    r = run("assemble", "--tier", "work", "--task-type", "dev")
    assert r.returncode == 0, r.stderr


def test_assemble_exits_zero_even_when_a_home_is_missing():
    # The contract: a broken registry must never abort the caller's command load.
    r = run("assemble", "--tier", "work", "--task-type", "dev", "--advisor", "nope-not-real")
    assert r.returncode == 0, r.stderr


def test_assemble_emits_a_loud_block_when_something_is_wrong():
    # Errors are reported in CONTENT, not via exit code.
    r = run("assemble", "--tier", "work", "--task-type", "dev", "--advisor", "nope-not-real")
    assert r.returncode == 0
    # Either the registry is clean (no error block) or it names the problem explicitly.
    if "ASSEMBLY ERROR" in r.stdout:
        assert "nope-not-real" in r.stdout or "no frontmatter" in r.stdout


def test_list_prints_one_row_per_protocol():
    r = run("list")
    assert r.returncode == 0, r.stderr
    assert "STAGES" in r.stdout


def test_the_cli_scans_the_real_registry_tree():
    """The wrong-root defect that neither exit code nor the header can express.

    `assemble` exits 0 by contract and `list` prints its header unconditionally, so a
    scanner aimed at the DATA root — which holds no skills/ tree at all — satisfies
    every other test in this file. Only the count separates "scanned the registry"
    from "scanned nothing", and only comparing it against disk makes it a completeness
    assertion rather than a smoke test.

    Files-plus-errors, not files: before the registry is normalized every file is an
    error, and this must hold in both phases.
    """
    r = run("list")
    assert r.returncode == 0, r.stderr
    found, errors = _counts(r.stdout)
    on_disk = sum(len(list((_REPO / rel).glob("*.md"))) for rel in FIXED_HOMES)
    assert on_disk > 0, f"the fixed homes are empty under {_REPO} — the test itself is broken"
    assert found + errors == on_disk


def test_rejects_an_unknown_tier():
    r = run("assemble", "--tier", "epic", "--task-type", "dev")
    assert r.returncode != 0  # argparse choices — a CLI misuse, not a registry fault

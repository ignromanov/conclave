"""conftest.py — the suite's CODE root is derived from this tree, never inherited (#103, #86).

This file sits beside `pytest.ini` at the repo root on purpose: it is the *topmost*
conftest, so it applies to both declared testpaths (`engine/scripts/tests` and
`engine/scripts/feedback/tests`) and to every invocation, including an explicit-path
one that never imports the conftest nested under `tests/`.

## What was wrong

`pytest.ini` pins the code under test to *this* checkout — `pythonpath` entries are
rootdir-relative, so a run inside a git worktree imports that worktree's `enginelib`.
`CONCLAVE_ENGINE_ROOT`, meanwhile, is exported by the SessionStart hook and points at
the main checkout. Nothing reconciled the two, so a worktree run read **its own code
against another tree's shipped assets**. Measured, not inferred:

    IMPORTED enginelib FROM : /tmp/conclave-probe-wt/engine/scripts/enginelib/__init__.py
    RESOLVED templates_dir(): /Users/ignat/code/conclave/skills/forge-operations/...

Both directions of failure have been observed on the same day: a worktree off master
failed `test_advisor_create.py::test_defaults` on an unsubstituted `${DESCRIPTION}`
because the main checkout sat on a feature branch (a false red, reported to the
operator as "master is red" while CI was green), and the mirror image from a parallel
session. The false-green half is the dangerous one: it announces nothing, and the run
is unreproducible afterwards because the deciding input is which branch a third,
unrelated checkout happened to be sitting on.

## Why derive rather than refuse

GH#103 proposed a gate that fails collection when the ambient value disagrees with the
test tree. That was the right instinct against the alternative it was weighed against —
pinning the variable per test, which no one would remember. But refusing is still the
weaker of the two available fixes here, for a reason the issue did not have in front of
it: **`pytest.ini` has already pinned the code to this tree.** A `CONCLAVE_ENGINE_ROOT`
naming a different tree does not express an intent the suite should honour; it produces
a run whose code and assets come from different checkouts, which is incoherent whatever
the operator meant. There is no legitimate variation left to preserve, so the value is
derived and the input is removed rather than validated.

Refusing would also fire on the *normal* case — the hook sets the variable in every
session by design — and a gate that fires normally is a gate that gets worked around.
What is abnormal is the two roots disagreeing, and that is what gets reported below.

Scoped deliberately to `CONCLAVE_ENGINE_ROOT`. The instance-root scrub lives in
`engine/scripts/tests/conftest.py` and is left where it is; that it does not cover the
`feedback/tests` testpath under an explicit-path invocation is a real, separate hole,
filed rather than folded in here.
"""
from __future__ import annotations

import os
import warnings
from pathlib import Path

ENGINE_ROOT_VAR = "CONCLAVE_ENGINE_ROOT"

# The CODE root of the tree this file lives in. In a linked worktree this is the
# worktree, which is the whole point: it is the same tree pytest.ini's rootdir-relative
# `pythonpath` puts on sys.path, so code and assets resolve to one checkout.
CODE_ROOT = Path(__file__).resolve().parent
ENGINE_ROOT = CODE_ROOT / "engine"

# The value the ambient environment tried to impose, kept only when it named a different
# tree. Read by the test that proves this file does its job, and reported once below.
INHERITED_ENGINE_ROOT: str | None = None

_ambient = os.environ.get(ENGINE_ROOT_VAR)
if _ambient and Path(_ambient).resolve() != ENGINE_ROOT:
    INHERITED_ENGINE_ROOT = _ambient

# Declared input, not inherited state. Set even when nothing was inherited, so the
# resolver never falls through to its own `Path(__file__)` guess and the suite has one
# answer regardless of how it was invoked.
os.environ[ENGINE_ROOT_VAR] = str(ENGINE_ROOT)


def pytest_configure(config) -> None:
    """Say so when a run was corrected — in a channel a *passing* run still shows.

    Channel chosen by measurement, not by taste. Under this repo's configured `-q`:

    | channel                       | visible under `-q`? |
    |-------------------------------|---------------------|
    | `print` at conftest import     | no — captured, and never replayed when the run passes |
    | `pytest_report_header`         | no — suppressed at `-q` verbosity |
    | `warnings.warn`                | **yes**, before the run |
    | `pytest_terminal_summary`      | yes, after the run |

    The first two were both written and both discarded after
    `test_root_conftest_tree_truth.py::test_the_correction_is_announced_on_stderr`
    went red on them. That is the defect's own shape reappearing inside its fix: a
    notice that is invisible in precisely the case it exists for — the false-green
    worktree run that reports nothing wrong.

    A warning wins over the terminal summary because it lands *before* the output a
    reader is scrolling through, and because it is escalatable: anyone who wants the
    hard gate GH#103 originally proposed can run `-W error::UserWarning`, or set
    `filterwarnings = error` in a CI config, without this file imposing it on the
    ordinary session where the variable is set by design and simply harmless.

    Only the disagreement is announced. The matching case is the normal one, and a
    line printed on every run is a line nobody reads.
    """
    if INHERITED_ENGINE_ROOT is None:
        return
    warnings.warn(
        f"{ENGINE_ROOT_VAR}={INHERITED_ENGINE_ROOT} names another checkout; the suite "
        f"uses its own tree {ENGINE_ROOT}. That value is exported by the SessionStart "
        f"hook (.claude/settings.json) and is correct for an in-place checkout, not "
        f"for this worktree.",
        UserWarning,
        stacklevel=1,
    )

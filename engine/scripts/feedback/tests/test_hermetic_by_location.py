"""The feedback testpath is hermetic by its own conftest chain, not by import order (#239).

`engine/scripts/feedback/tests` is a declared testpath with **no conftest of its own**. The
instance-root scrub used to live in `engine/scripts/tests/conftest.py` and ran at module
import — a process-global `os.environ.pop`. Whether it protected this directory therefore
depended on whether a conftest in a *sibling* directory happened to be imported first, which
is decided by the invocation:

| invocation                                          | `CONCLAVE_AI_ROOT` seen here |
|-----------------------------------------------------|------------------------------|
| `pytest` (both testpaths, sibling conftest imported) | `None`                       |
| `pytest engine/scripts/feedback/tests/<file>`        | **the operator's live root** |

Same file, same tree, same environment. The narrower invocation is the one a person reaches
for when iterating on a single failing test, and it was the unprotected one.

The cost of this class of hole is on record rather than hypothetical: a non-hermetic run
against a live instance rewrote the frontmatter of 34 DATA files — 16 decisions and 18
sessions — inside a test that names itself a safety gate (GH#131, finding 4).

## Why two tests and not one

The first test states the property. On its own it is worth little: under the full-suite
invocation it passed *before* the fix, because the sibling conftest had already run. A gate
written only against the usual invocation would have certified the defect as absent.

The second test is therefore the real gate — it re-runs the first one in a child process by
explicit path, with both variables poisoned, which is the exact invocation that leaked.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# feedback/tests/<this file> → parents: [tests, feedback, scripts, engine, <checkout>]
_CHECKOUT = Path(__file__).resolve().parents[4]

INSTANCE_ROOT_VARS = ("CONCLAVE_AI_ROOT", "VOIDPAY_AI_ROOT", "CLAUDE_PROJECT_DIR")

_PROPERTY_TEST = "test_this_directory_sees_no_ambient_instance_root"


def test_this_directory_sees_no_ambient_instance_root():
    """No instance-root variable reaches a test in this directory.

    Read from `os.environ` rather than from a fixture, because the fixture is half of what
    is under test: the autouse `_hermetic_instance_env` was defined in the sibling conftest
    and so had that directory's scope, leaving this one with no per-test clear at all.
    """
    leaked = {var: os.environ[var] for var in INSTANCE_ROOT_VARS if var in os.environ}
    assert not leaked, (
        f"instance-root variables reached this test: {leaked}. Every DATA-root resolver "
        f"follows them, so this run reads and can write the operator's live instance."
    )


def test_the_property_holds_under_an_explicit_path_invocation():
    """Re-run the property in a child process, by explicit path, with the vars poisoned.

    This is the whole gate. `pytest` selects conftests by walking from rootdir down to each
    collected file, so an explicit path into this directory collects the repo-root conftest
    and nothing else — no sibling directory is visited, and no import of its conftest is
    triggered. If the scrub is anywhere below the root, this child sees the poison.

    The values are deliberately non-existent paths: were the child to act on them, it fails
    loudly rather than touching a real tree.
    """
    poison = {
        "CONCLAVE_AI_ROOT": "/nonexistent/leaked-ai-root",
        "CLAUDE_PROJECT_DIR": "/nonexistent/leaked-project-dir",
    }
    env = {**os.environ, **poison}
    # Not inherited from this process: the parent run may itself have been invoked in a way
    # that already cleared them, and a poison that is not set proves nothing.
    node = f"{Path(__file__).relative_to(_CHECKOUT)}::{_PROPERTY_TEST}"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", node, "-p", "no:cacheprovider"],
        cwd=str(_CHECKOUT), env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, (
        f"an explicit-path run of {node} leaked the ambient instance root.\n"
        f"Poison set: {poison}\n"
        f"--- child stdout ---\n{proc.stdout[-3000:]}\n"
        f"--- child stderr ---\n{proc.stderr[-2000:]}"
    )

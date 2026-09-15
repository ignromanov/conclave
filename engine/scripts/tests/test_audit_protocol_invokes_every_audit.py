"""The audit protocol must invoke every audit the CLI accepts (#302).

The set of audits lives in `_AUDITS`, a dict in the CLI adapter. Until this gate it
also lived a second time, as a shell literal in `protocols/audit.md` § Run, and only
the first copy was updated when an audit was added. Measured when this gate was
written: the CLI accepted 16, the loop named 8. The most recent addition, `records`,
had fallen outside the loop the day before — the leak is live, not historical.

An audit outside the loop is not merely undocumented. It is an audit nothing runs, so
it can sit green for months while the thing it guards rots — `a CLI no protocol
invokes is not a path`, the 093 finding, re-entered through a doc. Four of the eight
audits outside the loop were in fact reporting CRIT at the time this was written, and
no audit run had ever surfaced one of them.

The gate is written to measure, not to recognise a shape. A doc that derives its list
passes only if the derivation, EXECUTED, yields the full set: an `engine audit --list`
that printed nothing would otherwise read as "derived, therefore complete", which is
the vacuity this whole defect class is made of.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from engine.cmd.audit import _AUDITS

REPO = Path(__file__).resolve().parents[3]
AUDIT_MD = REPO / "skills" / "forge-operations" / "references" / "protocols" / "audit.md"
SCRIPTS = REPO / "engine" / "scripts"

#: The derivation the protocol is expected to prescribe. Spelled once, here, so the
#: doc and this gate cannot drift into naming two different commands.
DERIVATION = "engine audit --list"


def _run_block() -> str:
    """The fenced shell block under `## Run`, unwrapped of line continuations."""
    text = AUDIT_MD.read_text(encoding="utf-8")
    match = re.search(r"^## Run\s*\n+```[a-z]*\n(.*?)^```", text, re.S | re.M)
    assert match, f"{AUDIT_MD} has no fenced shell block under `## Run`"
    block = match.group(1).replace("\\\n", " ")
    assert block.strip(), "the `## Run` block is empty — it invokes nothing"
    return block


def _audit_list() -> set[str]:
    """`engine audit --list`, actually executed. The doc's own command, not a stand-in."""
    proc = subprocess.run(
        [sys.executable, "-m", "engine", "audit", "--list"],
        cwd=SCRIPTS, capture_output=True, text=True,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(SCRIPTS)},
    )
    assert proc.returncode == 0, f"`{DERIVATION}` failed rc={proc.returncode}: {proc.stderr}"
    return {ln.strip() for ln in proc.stdout.splitlines() if ln.strip()}


def _names_the_run_block_iterates() -> set[str]:
    """Every audit a reader following `## Run` would actually invoke.

    Two shapes are understood, and neither is privileged: a literal `for name in a b c`
    is read off the doc, and a `$(engine audit --list)` is resolved by running it. The
    caller's assertion is the same either way, which is the point — a derived list that
    is wrong fails exactly as loudly as a hand list that is stale.
    """
    block = _run_block()
    if DERIVATION in block:
        return _audit_list()
    match = re.search(r"for\s+\w+\s+in\s+(.*?);", block, re.S)
    assert match, f"`## Run` neither iterates a literal nor uses `{DERIVATION}`:\n{block}"
    return {w for w in match.group(1).split() if w and not w.startswith("$")}


def test_the_run_loop_covers_every_audit_the_cli_accepts():
    assert _AUDITS, "the CLI registry is empty — this gate would measure nothing"
    invoked = _names_the_run_block_iterates()
    assert invoked, "`## Run` resolves to no audit at all"
    missing = sorted(set(_AUDITS) - invoked)
    assert not missing, (
        f"{len(missing)} audit(s) the CLI accepts are invoked by nothing in "
        f"{AUDIT_MD.name}: {', '.join(missing)}"
    )


def test_the_run_loop_names_no_audit_the_cli_rejects():
    """The mirror direction. A stale name makes the whole loop abort at that
    iteration on argparse's `invalid choice`, taking the audits after it down too —
    so this is not merely a tidiness check."""
    invoked = _names_the_run_block_iterates()
    unknown = sorted(invoked - set(_AUDITS))
    assert not unknown, f"`## Run` names audits the CLI rejects: {', '.join(unknown)}"


def test_audit_list_prints_exactly_the_cli_registry():
    """Guards the derivation itself. Without this, `--list` could print a hand-kept
    literal of its own and the gate above would certify the second copy as the first."""
    assert _audit_list() == set(_AUDITS)

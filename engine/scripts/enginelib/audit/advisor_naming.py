"""enginelib/audit/advisor_naming.py — report advisor ids that predate the naming standard.

An advisor id is `<name>-<role>` with `<role>` from the closed vocabulary in
`enginelib.advisors.ADVISOR_ROLES`. `validate_advisor_id` enforces that at the two
doors an id can ENTER through — `advisor create` and `advisor rename --to`. Ids
already on disk were never asked, so nothing would ever surface them.

This REPORTS rather than refuses, deliberately. The fix for a live non-conforming
advisor is a migration that carries its memory across (`engine advisor rename`),
chosen by an operator who also has to pick the persona name. A gate that merely
rejected the id would break every instance holding one and offer no path out.

Executors are out of scope: `exec-<name>-<role>` has its own vocabulary and its
own gate (`tests/test_executor_defs.py::test_executor_naming_standard`). Auditing
them here would report every executor as a broken advisor.

I/O-free: no print/argparse/sys.exit. Returns Findings for the adapter to format.
"""
from __future__ import annotations

from pathlib import Path

from enginelib.advisors import ADVISOR_ROLES, is_valid_advisor_id
from enginelib.audit import Findings


def run(agents_dir: Path) -> Findings:
    """Report every non-conforming advisor id under *agents_dir*."""
    findings = Findings()
    if not agents_dir.is_dir():
        return findings

    # `is_file()` follows the link: the project's agents dir is a symlink layer
    # over the DATA tree, so retiring an advisor deletes the target and can leave
    # the link behind. A glob still sees it, and the audit told the operator to
    # migrate the memory of a file that does not exist.
    offenders = sorted(
        md.stem
        for md in agents_dir.glob("*.md")
        if md.is_file() and not md.stem.startswith("exec-") and not is_valid_advisor_id(md.stem)
    )
    if not offenders:
        return findings

    roles = ", ".join(sorted(ADVISOR_ROLES))
    for stem in offenders:
        findings.crit.append(
            f"{stem}: not <name>-<role>. Migrate with "
            f"`engine advisor rename --from {stem} --to <name>-<role>`."
        )
    findings.crit.append(f"allowed roles: {roles}")
    return findings

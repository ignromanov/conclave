"""enginelib/audit/frontmatter.py — report records that do not match their type's schema.

The reader half of spec 084 §4. `briefing/validate.py` holds the per-file predicate; this
walks the corpus and speaks `Findings`, so the check the spec specified is finally
reachable from a command instead of from tests alone.

Reachable is the whole point. Until now `validate_file`/`validate_tree` had ZERO
production callers — §A4 named three consumers (briefing-build, validator, backfill) and
none of them was ever built, so a validator with its own pydantic models and 24 tests ran
nowhere. It also could not have run: pointed at this instance it raised out of the first
unparseable record and examined nothing after it.

Reports rather than refuses, on the `records` and `feedback_owners` precedent. The repair
is a DATA migration plus a revision of §4 itself, and neither is a thing a gate can do:
measured 2026-09-15, of the 581 records in the locations the registry claims, ZERO conform
— and five of the ten declared locations do not exist at all, because §4 was written
before spec 086 re-homed feedback and spec 103 moved the trees. That is a contract to
re-author against the corpus that exists, and this audit is the instrument that says by
how much. A gate here would only add a red light nobody can turn off.

I/O-free apart from reading the files it is handed: no print/argparse/sys.exit.
"""
from __future__ import annotations

from pathlib import Path

from briefing.validate import Severity, validate_tree
from enginelib.audit import Findings


def run(root: Path) -> Findings:
    """Report every record under *root* that its own type's schema rejects.

    ERROR findings are CRIT and WARN findings are WARN, one for one: the severity split
    is spec 084 §3 A5's and is already decided per finding, so re-deciding it here would
    be a second opinion on a question the validator has answered.

    Paths are reported relative to *root* where possible. An absolute path here is a
    temp-dir path in a test or a record outside the tree; neither should be silently
    rendered as though it sat beside the others.
    """
    findings = Findings()
    for f in validate_tree(Path(root)):
        try:
            where = str(f.path.relative_to(root))
        except ValueError:
            where = str(f.path)
        line = f"{where} — {f.message}"
        if f.severity is Severity.ERROR:
            findings.crit.append(line)
        else:
            findings.warn.append(line)
    return findings

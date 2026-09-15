"""enginelib/audit/records.py — report records whose written value did not survive.

The layer above `enginelib.records`, which holds the predicate; this one walks a corpus
and speaks `Findings`. Same subject, two layers: the core primitive is what the WRITER
calls on itself before every write (`frontmatter.render_record`), and this is what a
reader calls over files nobody is writing — the hand-edit path, where no serializer stands.

That path is not hypothetical. `sessions/2026-09-14-sage-cto-117-mechanism-decided.md`
carries `issues: [#26]` and does not parse, written five days after `as_flow_list` fixed
the writer that produces that field (#261). Its same-day sibling from the same engine is
correct, so the engine did not regress — a hand reached in. Nothing noticed, because every
reader the engine points at a session record is line-based by design.

Reports rather than refuses, on the `feedback_owners` precedent: the repair is a DATA
migration the operator has to choose, and a gate that merely rejected would leave the
instance no path out of the records it already holds.

I/O-free apart from reading the files it is handed: no print/argparse/sys.exit.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from enginelib.audit import Findings
from enginelib.records import check_file


def run(dirs: Iterable[Path]) -> Findings:
    """Report every value lost in the markdown records under *dirs*.

    Everything found here is CRIT. There is no degraded-but-usable shade of this: the
    value is either readable by both halves of the engine or it is gone from one of them,
    and a record the YAML half cannot read is a record any future projection drops in
    silence while reporting a confident total.
    """
    findings = Findings()
    for d in dirs:
        d = Path(d)
        if not d.is_dir():
            continue
        for path in sorted(d.rglob("*.md")):
            for lost in check_file(path):
                findings.crit.append(f"{path.name} — {lost}")
    return findings

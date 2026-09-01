"""scans/plans.py — section: Plans (spec 116 P1, GH#183).

An inventory of the instance's planned work, with a state for each plan that is
DERIVED and never self-reported.

Why derived. The issue that commissioned this recorded four plan status headers read
by hand and two of them false: one said "No code written yet. Branch not cut yet"
while its components were in a merged commit, another said "Uncommitted, no PR" while
all four of its marker strings were on origin/main. A plan's prose about itself is not
an input to this scan — it is not read at all.

Why not branches. The issue proposed deriving from "branch exists? merged? residual
diff against origin/main?". That is the one signal that cannot work here: both recorded
falsifications came from marker strings found on origin/main AFTER a squash merge, which
destroys the branch and its lineage. `branch exists?` answers "no" identically for a plan
never started and a plan shipped and squashed — precisely the two states worth telling
apart. The operator's stated default is squash merge.

What is used instead: the plan's own closing condition, evaluated against the tree —
the same `verify:` predicate 093 already ships and already closes feedback items with.

    verify:
      kind: file-contains
      file: src/core/parsers/relationship-skew.ts
      pattern: clampDateRange

Two plan conventions are discovered, because two are measured and neither is engine
canon: `ops/specs/<NNN-slug>/plan*.md` in DATA (this project's CLAUDE.md mandates plans
live beside their spec) and `.claude/plans/` in the project checkout (the harness
convention, where the commissioning instance keeps 35 heterogeneous entries). A scan
hardcoding one renders 0 in the instance that filed the issue.

Empty-state: _(no plans found)_
"""
from __future__ import annotations

import re
from pathlib import Path

from briefing.scans import ScanCtx

_PLACEHOLDER = "_(no plans found)_"

# Rows shown before the list is truncated. The glance count is always exact; the rows
# are the deviation cluster only, because this section renders identically in every
# advisor's briefing and the body has a ~6000-token cap to share.
_MAX_ROWS = 5

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Ordered by what the reader must do about it. Uncertainty ranks ABOVE known-bad
# (Icinga's UNKNOWN-before-WARNING): "cannot tell" is more urgent than "not done yet".
# `landed` is a count and never a row — the inverted pyramid.
_BROKEN = "broken"
_OPEN = "open"
_UNVERIFIABLE = "unverifiable"
_LANDED = "landed"

_ROW_ORDER = (_BROKEN, _OPEN, _UNVERIFIABLE)

# The remedy travels with the state, in the same cell. A state that cannot be computed
# honestly is reported as absent WITH what unblocks it — never greyed out, never guessed.
_REMEDY = {
    _BROKEN: "verify: target is gone — repoint or drop it",
    _OPEN: "closing condition not met",
    _UNVERIFIABLE: "no verify: declared — add one to its frontmatter",
}


def build(ctx: ScanCtx) -> str:
    """Return the plans inventory: one glance line, then the deviation rows."""
    plans = _discover(ctx)
    if not plans:
        return _PLACEHOLDER

    states = {p: _derive_state(p, ctx.project_root) for p in plans}
    counts = {s: sum(1 for v in states.values() if v == s) for s in
              (_LANDED, _OPEN, _BROKEN, _UNVERIFIABLE)}

    # Zeros render. On an inventory surface an omitted row is not a green signal, and
    # "0 landed" is the finding on day one, not a blank to be tidied away.
    total = len(plans)
    noun = "plan" if total == 1 else "plans"
    summary = (
        f"{total} {noun} — {counts[_LANDED]} landed · {counts[_OPEN]} open · "
        f"{counts[_BROKEN]} broken · {counts[_UNVERIFIABLE]} unverifiable"
    )

    # Proof layer: the globs that regenerate the number, one hop away.
    sources = "`ops/specs/*/plan*.md` · `.claude/plans/`"

    groups = [
        (state, sorted(p for p, s in states.items() if s == state))
        for state in _ROW_ORDER
    ]
    groups = [(state, members) for state, members in groups if members]
    if not groups:
        return f"{summary}\n{sources}\n\nEvery plan's closing condition holds."

    lines = [summary, sources, ""]
    budget = _MAX_ROWS
    for state, members in groups:
        lines.append(f"- {state} ({len(members)}) — {_REMEDY[state]}")
        # A state covering the WHOLE corpus gets no member list: naming five arbitrary
        # plans adds nothing the count and the glob above do not already carry, and one
        # remedy repeated per row is exactly the data-ink waste this contract refuses.
        # Members are named only while the group is a minority, so the section shrinks
        # as the hygiene it measures improves.
        if len(members) == total or budget <= 0:
            continue
        shown = members[:budget]
        lines.extend(f"  › {_label(path, ctx)}" for path in shown)
        budget -= len(shown)
        if len(members) > len(shown):
            lines.append(f"  › … and {len(members) - len(shown)} more")
    return "\n".join(lines)


def _discover(ctx: ScanCtx) -> list[Path]:
    """Plans from both conventions, deduplicated and ordered."""
    found: set[Path] = set()

    specs_root = ctx.repo_root / "ops" / "specs"
    if specs_root.is_dir():
        found.update(p for p in specs_root.glob("*/plan*.md") if p.is_file())

    harness_root = ctx.plans_dir
    if harness_root.is_dir():
        for entry in harness_root.iterdir():
            # A plan is either a markdown file, or a directory holding one. Anything
            # else in this tree (.sql, .patch, scratch data) is not a plan and is not
            # counted -- an inflated denominator is its own kind of lie.
            if entry.is_file() and entry.suffix == ".md":
                found.add(entry)
            elif entry.is_dir():
                found.update(p for p in entry.glob("*.md") if p.is_file())

    return sorted(found)


def _derive_state(path: Path, project_root: Path) -> str:
    """One of landed / open / broken / unverifiable — never the plan's own claim."""
    pred = _declared_predicate(path)
    if pred is None:
        return _UNVERIFIABLE
    try:
        from enginelib.paths import engine_root
        from feedback.feedback_verify import classify_predicate
        from feedback.schema import Predicate
    except Exception:  # pragma: no cover - defensive; feedback pkg always ships
        return _UNVERIFIABLE
    try:
        # `pred` is untyped frontmatter; Predicate's own validator is the gate that
        # decides whether it is usable, so the cast is deliberate and the raise below
        # is the handled path, not an unexpected one.
        #
        # `code_root` is not optional in practice (#170/#197): a predicate declaring
        # `root: code` makes classify_predicate RAISE when it is missing, and the
        # `except` below would fold that raise into `broken` -- accusing a perfectly
        # valid predicate of pointing at a vanished file. A caller that cannot say
        # where the CODE tree is must not be the one rendering the verdict.
        verdict = classify_predicate(
            Predicate(**pred),  # type: ignore[arg-type]
            project_root,
            engine_root().parent,
        )
    except Exception:
        # A malformed predicate is declared-but-unusable: that is `broken`, not
        # `unverifiable`. The two are different facts and the remedy differs.
        return _BROKEN
    return {"pass": _LANDED, "fail": _OPEN}.get(verdict, _BROKEN)


def _declared_predicate(path: Path) -> dict[str, str] | None:
    """Parse a ``verify:`` block out of the plan's frontmatter, or None.

    Deliberately shallow: only the keys the Predicate model accepts, and only from
    frontmatter. Nothing in the plan's BODY is consulted — the body is where a plan
    describes its own progress, and that is the input this whole section refuses.

    `root` is among them because dropping it does not make a `root: code` predicate
    safe, it makes it silently resolve against the wrong tree (#170).
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    m = _FM_RE.match(text)
    if not m:
        return None

    block = m.group(1).splitlines()
    out: dict[str, str] = {}
    in_verify = False
    for line in block:
        if re.match(r"^verify:\s*$", line):
            in_verify = True
            continue
        if in_verify:
            if line and not line.startswith((" ", "\t")):
                break  # dedent ends the block
            kv = re.match(r"^\s+(kind|root|file|path|pattern):\s*(.+?)\s*$", line)
            if kv:
                out[kv.group(1)] = kv.group(2).strip("'\"")
    return out or None


def _label(path: Path, ctx: ScanCtx) -> str:
    """A pointer the reader can act on: the plan's identity, not a bare filename.

    `plan.md` alone names 26 different files here, so the spec directory travels with
    it — the referent rides along with the pointer.
    """
    for root in (ctx.repo_root, ctx.plans_dir.parent, ctx.project_root):
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        return str(rel)
    return path.name

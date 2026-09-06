"""predicate_derive.py — deterministic (no-LLM, no-network) verify-predicate synthesis.

Spec 105 kill-gate (Q2). For each accepted feedback item, try to synthesize a `verify:`
Predicate from STRUCTURED fields ONLY (location.file/section, suggested_fix, observation,
category). Where the structured fields do not pin down a checkable predicate, the item is
NOT derivable — we invent nothing.

A derived predicate is only credited when it is **red-at-attach**: evaluating it against
the CURRENT tree returns fail (the bug is still demonstrable; the predicate would flip to
pass only once the fix lands). An already-green predicate proves nothing and is not
credited (threat T2). Containment (Task A) refuses any predicate whose path escapes the
project root.

Deterministic rules, tried in order (first that fires wins):

  GA  grep-absent — "remove a named symbol from a named code file". Fires when
      location.file exists in the tree AND location.section is a lone code identifier
      (has `_` or an uppercase letter — a symbol, not a prose heading) AND the
      **suggested_fix itself** both names that symbol AND carries a removal cue
      (hardcode/replace/remove/drop/…). Requiring the cue and the symbol to co-occur in
      the post-fix instruction — not merely somewhere in the prose — is what stops the
      false positive where "hardcoded" describes the *problem* while the named symbol is
      a function that must SURVIVE (measured on the live backlog: grep-absent `cmd_set`,
      grep-absent `_step1_load_briefing` — both would delete load-bearing code). The
      predicate greps the symbol out of that file; red iff the symbol is still there.

  FC  file-contains — "a distinctive literal must appear in a named file". Fires when
      location.file exists AND the suggested_fix contains exactly ONE distinctive
      backticked literal that is NOT yet present in that file (the thing to be added).
      Red-at-attach by construction (the literal is currently absent → fail).

  FA  file-absent — "a named path should be gone". Fires when the fix carries a deletion
      cue naming a concrete path-with-extension that currently exists. Red iff it exists.

These rules are deliberately narrow: their job is to MEASURE how much of the backlog a
non-agentic deriver can honestly pin, not to maximize a number.
"""
from __future__ import annotations

import sys

# Interpreter floor, enforced before the first thing that can fail below it — here,
# `from typing import TypeGuard` below (TypeGuard was added in 3.10). /conclave:triage Step 2.5
# launches this file directly, which is what puts it in the enforced entrypoint set.
# Measured, not declared; see engine/__main__.py for the full note.
if sys.version_info < (3, 11):  # noqa: UP036 — see engine/__main__.py
    sys.stderr.write(
        f"Conclave requires Python 3.11 or newer.\n"
        f"This is Python {sys.version.split()[0]} at {sys.executable}.\n"
        f"Install a newer interpreter (e.g. `uv python install 3.13`) and re-run.\n"
    )
    sys.exit(1)

import re  # noqa: E402 — must follow the floor guard above
from dataclasses import dataclass  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import TypeGuard  # noqa: E402

from feedback_verify import _contained, _resolve, classify_predicate  # noqa: E402

from feedback.schema import Predicate  # noqa: E402

REMOVE_CUES = ("hardcode", "hardcodes", "hardcoded", "replace", "remove",
               "drop", "demote", "delete", "strip")
# a lone code identifier: symbol-shaped, not a prose heading like "Milestones / Labels"
_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_BACKTICK_RE = re.compile(r"`([^`]+)`")
# a path with an extension, e.g. hire.md, regen.py, .ai/foo.sh
_PATH_RE = re.compile(r"([\w./-]+\.[A-Za-z0-9]+)")


@dataclass
class Derivation:
    feedback_id: str
    item_id: str
    bucket: str          # DERIVED-AND-RED | DERIVED-BUT-GREEN | DERIVED-BUT-BROKEN | NOT-DERIVABLE
    rule: str            # GA | FC | FA | "" (when not derivable)
    predicate: dict | None
    verdict: str | None  # pass | fail | broken (classify result) or None
    reason: str


def _is_symbol(section: str | None) -> TypeGuard[str]:
    """TypeGuard, not bool: the None-rejection below is the whole point of the guard, and a
    plain bool leaves callers dereferencing `section` under a check the checker cannot see."""
    if not section:
        return False
    return bool(_IDENT_RE.match(section)) and ("_" in section or section != section.lower())


def _distinctive_literals(text: str) -> list[str]:
    """Backticked literals worth grepping: no whitespace, len>=4, and either an
    uppercase letter or one of the shell/path metacharacters — so `${VAR:-.}` or
    `--state open`-style tokens qualify but a plain word in backticks does not."""
    out: list[str] = []
    for lit in _BACKTICK_RE.findall(text):
        lit = lit.strip()
        if " " in lit or len(lit) < 4:
            continue
        if any(c.isupper() for c in lit) or any(c in lit for c in "${}=:./-"):
            out.append(lit)
    return out


def _file_exists(checkout: Path, rel: str | None) -> Path | None:
    if not rel:
        return None
    target = _resolve(checkout, rel)
    if not _contained(checkout, target) or not target.is_file():
        return None
    return target


def derive_predicate(item: dict, checkout: Path) -> tuple[dict | None, str, str]:
    """Return (predicate_dict | None, rule, reason). Deterministic; reads the tree only
    to disambiguate (which literal is absent, whether a symbol/path is present)."""
    loc = item.get("location") or {}
    file_rel = loc.get("file")
    section = loc.get("section")
    obs = (item.get("observation") or "")
    fix = (item.get("suggested_fix") or "")
    fix_l = fix.lower()
    blob = f"{obs}\n{fix}".lower()

    target = _file_exists(checkout, file_rel)

    # GA — remove a named symbol from a named code file. The removal cue AND the symbol
    # must BOTH appear in the suggested_fix, or the cue is just prose about the problem.
    if (target is not None and _is_symbol(section)
            and section.lower() in fix_l
            and any(cue in fix_l for cue in REMOVE_CUES)):
        return ({"kind": "grep-absent", "file": file_rel, "pattern": re.escape(section)},
                "GA", f"remove symbol `{section}` from {file_rel}")

    # FC — a distinctive literal from the fix must appear in a named file
    if target is not None:
        text = target.read_text(errors="replace")
        absent = [lit for lit in _distinctive_literals(fix) if lit not in text]
        if len(absent) == 1:
            return ({"kind": "file-contains", "file": file_rel,
                     "pattern": re.escape(absent[0])},
                    "FC", f"literal `{absent[0]}` must be present in {file_rel}")
        if len(absent) > 1:
            return (None, "", f"FC ambiguous: {len(absent)} distinctive literals absent")

    # FA — a named path should be gone
    if any(cue in blob for cue in ("delete", "remove")):
        for m in _PATH_RE.findall(fix):
            p = _resolve(checkout, m)
            if _contained(checkout, p) and p.is_file():
                return ({"kind": "file-absent", "path": m}, "FA",
                        f"path {m} should be deleted")

    # Nothing pinned a checkable predicate.
    if not file_rel:
        return (None, "", "no location.file — cannot pin a target")
    if target is None:
        return (None, "", f"location.file {file_rel!r} not a file in the tree")
    return (None, "", "structured fields do not pin a checkable literal (prose-only fix)")


def evaluate_item(item: dict, checkout: Path, code_root: Path | None = None) -> Derivation:
    fid = item.get("feedback_id", "")
    iid = item.get("item_id") or item.get("id") or ""
    pred_dict, rule, reason = derive_predicate(item, checkout)
    if pred_dict is None:
        return Derivation(fid, iid, "NOT-DERIVABLE", "", None, None, reason)
    verdict = classify_predicate(Predicate(**pred_dict), checkout, code_root)
    if verdict == "fail":
        bucket = "DERIVED-AND-RED"      # bug still demonstrable — counts
    elif verdict == "pass":
        bucket = "DERIVED-BUT-GREEN"    # already true — proves nothing (T2)
    else:
        bucket = "DERIVED-BUT-BROKEN"   # target rotted / escapes root — does not count
    return Derivation(fid, iid, bucket, rule, pred_dict, verdict, reason)


def run(rows: list[dict], checkout: Path, code_root: Path | None = None) -> list[Derivation]:
    """Derive over accepted rows only (the backlog the kill-gate measures)."""
    return [evaluate_item(r, checkout, code_root) for r in rows if r.get("status") == "accepted"]


def main(argv: list[str] | None = None) -> int:  # noqa: ARG001 — no flags today
    """Report which UNCOVERED accepted items (no `verify:`, no `verify_waiver:`) a
    deterministic rule can pin, and print a ready `--set-verify` invocation for each hit.

    Read-only: this only measures and prints. Attaching a predicate is still the operator
    running `feedback_verify.py --set-verify` themselves (Step 2.5 of triage.md), which
    re-runs the admission test before writing anything."""
    from feedback_triage import _load_index

    from enginelib.paths import engine_root, project_root
    from feedback.paths import index_path

    root = project_root()
    rows = _load_index(index_path())
    uncovered = [r for r in rows if r.get("status") == "accepted"
                 and not r.get("verify") and not r.get("verify_waiver")]
    derivations = run(uncovered, root, code_root=engine_root().parent)
    red = [d for d in derivations if d.bucket == "DERIVED-AND-RED"]

    pct = (100.0 * len(red) / len(uncovered)) if uncovered else 0.0
    print(f"uncovered={len(uncovered)} derived-and-red={len(red)} ({pct:.1f}%)")
    for d in red:
        p = d.predicate or {}
        target = f"--file {p['file']}" if "file" in p else f"--path {p['path']}"
        pattern = f" --pattern {p['pattern']}" if "pattern" in p else ""
        root_flag = f" --root {p['root']}" if p.get("root") and p["root"] != "project" else ""
        print(f"  [{d.rule}] {d.feedback_id} {d.item_id} :: {d.reason}\n"
              f"    --set-verify {d.feedback_id} {d.item_id} {p.get('kind')} "
              f"{target}{pattern}{root_flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())  # `sys` is imported at module level for the floor guard above

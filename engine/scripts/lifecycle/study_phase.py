"""study-phase.py — team.done Study phase orchestrator (Phase 4, spec 085).

Orchestrates team.done Study steps 1-3,5,6 (step 4 is P0-blocking — surfaced
as exit 3 and NEVER swallowed).

Steps:
  1. wiki-capture-suggest.sh --since HEAD~5
  2. promote-decision.sh --id <id>  (per candidate from step 1)
  3. wiki-bridge-rebuild.sh         (if step 2 promoted ≥1)
  4. wiki-audit-stale.sh            exit-3 = P0 BLOCKING — returned as-is
  5. wiki-hot-sync.sh               (always, non-blocking)
  6. wiki-link-check.sh --quiet     (informational)

Exit codes:
  0  = every step RAN and was clean (emit nothing to summary row)
  1  = error in orchestration itself
  2  = non-blocking findings (P1 stale, link violations, captures suggested)
       OR a step that never ran (absent script / exit=1) — see below
  3  = P0 BLOCKING (wiki-audit-stale exit 3) — must triage before close-session

Aggregate one-row study summary is printed to stdout:
  study: capture:{N} · promoted:{N} · stale:P0:{N}/P1:{N} · link:{N} · steps-not-run:{N}
Omit zero counters. Omit row entirely if all zero (caller checks exit code).

`steps-not-run` exists because exit 0 was previously returned when the step scripts were
absent — which, after the wiki extraction moved them out of `engine/scripts/wiki/` into the
`/wiki:*` plugin, is every install: all six steps missing, `clean — no findings` on stdout
(#56A). Omission asserts a check passed; a step that did not run asserts nothing.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Interpreter floor, enforced before the first thing that can fail below it — here, the
# `enginelib` import below, whose module-level PEP 604 annotations are evaluated on import.
# /conclave:done launches this file directly, so it cannot inherit another entrypoint's
# refusal. Measured, not declared; see engine/__main__.py for the full note.
if sys.version_info < (3, 11):  # noqa: UP036 — see engine/__main__.py
    sys.stderr.write(
        f"Conclave requires Python 3.11 or newer.\n"
        f"This is Python {sys.version.split()[0]} at {sys.executable}.\n"
        f"Install a newer interpreter (e.g. `uv python install 3.13`) and re-run.\n"
    )
    sys.exit(1)

# Reach the enginelib package when run as a standalone lifecycle script
# (`python3 lifecycle/study_phase.py`): sys.path[0] is lifecycle/, so add scripts/.
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)
from enginelib.advisors import (  # noqa: E402 (follows the sys.path bootstrap above)
    lifecycle_advisors,
)
from enginelib.paths import check_legacy_data_root_env  # noqa: E402


def _data_root() -> Path:
    """DATA root for advisor discovery (lifecycle env convention: CONCLAVE_AI_ROOT),
    else CWD. Deliberately does not raise where `repo_root()` would: a study phase with
    no advisors to discover is a no-op, not a failure."""
    check_legacy_data_root_env()
    env = os.environ.get("CONCLAVE_AI_ROOT")
    return Path(env).resolve() if env else Path.cwd()


def _engine_root() -> Path:
    """engine/ CODE root — wiki scripts are CODE, in the FLAT layout (engine/scripts),
    never under a DATA-root `.claude/`. Derived from this file
    (engine/scripts/lifecycle/study_phase.py -> engine/); CONCLAVE_ENGINE_ROOT overrides."""
    env = os.environ.get("CONCLAVE_ENGINE_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]


def _wiki_scripts_dir() -> Path:
    return _engine_root() / "scripts" / "wiki"


def _run(cmd: list[str], *, check: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


# ---------------------------------------------------------------------------
# Step 1 — capture suggest
# ---------------------------------------------------------------------------

def _parse_capture_count(stdout: str) -> int:
    """Extract candidate count from wiki-capture-suggest output."""
    m = re.search(r"Capture suggestions \((\d+)/", stdout)
    if m:
        return int(m.group(1))
    return 0


def _parse_promote_ids(stdout: str) -> list[str]:
    """Extract decision IDs from capture suggestions (run: promote-decision.sh --id <id>)."""
    return re.findall(r"promote-decision\.sh --id\s+(\S+)", stdout)


# ---------------------------------------------------------------------------
# Step 4 — audit-stale helpers
# ---------------------------------------------------------------------------

def _parse_stale_counts(stdout: str) -> tuple[int, int]:
    """Return (p0_count, p1_count) from wiki-audit-stale output."""
    p0 = p1 = 0
    m0 = re.search(r"P0 \(blocking\):\s+(\d+)", stdout)
    m1 = re.search(r"P1 \(informational\):\s+(\d+)", stdout)
    if m0:
        p0 = int(m0.group(1))
    if m1:
        p1 = int(m1.group(1))
    return p0, p1


# ---------------------------------------------------------------------------
# Result aggregate
# ---------------------------------------------------------------------------

@dataclass
class StudyResult:
    captures: int = 0
    promoted: int = 0
    stale_p0: int = 0
    stale_p1: int = 0
    link_violations: int = 0
    errors: list[str] = field(default_factory=list)

    def is_p0_blocking(self) -> bool:
        return self.stale_p0 > 0

    def has_findings(self) -> bool:
        return (
            self.captures > 0
            or self.promoted > 0
            or self.stale_p0 > 0
            or self.stale_p1 > 0
            or self.link_violations > 0
        )

    def ran_incompletely(self) -> bool:
        """True when some step never produced a verdict — absent script or exit=1.

        Distinct from has_findings(): a finding is something a step MEASURED, this is a
        step that measured nothing. Conflating the two is what let the phase report
        `clean` while every one of its six steps was missing (#56A).
        """
        return bool(self.errors)

    def summary_row(self) -> str:
        parts: list[str] = []
        if self.captures:
            parts.append(f"capture:{self.captures}")
        if self.promoted:
            parts.append(f"promoted:{self.promoted}")
        stale_str = ""
        if self.stale_p0 or self.stale_p1:
            stale_str = f"stale:P0:{self.stale_p0}/P1:{self.stale_p1}"
            parts.append(stale_str)
        if self.link_violations:
            parts.append(f"link:{self.link_violations}")
        # Last, so a real finding leads the row — but never omitted: per
        # output-formatting.md, omitting a row asserts the check passed, and a step that
        # did not run has asserted nothing. `not-run` covers both causes truthfully; the
        # per-step reasons go to stderr.
        if self.errors:
            parts.append(f"steps-not-run:{len(self.errors)}")
        if not parts:
            return ""
        glyph = "✗" if self.stale_p0 else "⚠"
        return f"▍ {glyph} **study**    {' · '.join(parts)}"


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run_study(wiki_dir: Path, since: str = "HEAD~5") -> StudyResult:
    res = StudyResult()

    # Step 1 — capture suggest
    capture_script = wiki_dir / "wiki-capture-suggest.sh"
    if capture_script.is_file():
        r1 = _run(["bash", str(capture_script), "--since", since])
        if r1.returncode == 1:
            res.errors.append(f"wiki-capture-suggest: exit=1 {r1.stderr.strip()[:100]}")
        elif r1.returncode == 2:
            res.captures = _parse_capture_count(r1.stdout)
            promote_ids = _parse_promote_ids(r1.stdout)

            # Step 2 — promote decisions from capture suggestions
            promote_script = wiki_dir / "promote-decision.sh"
            if promote_ids and promote_script.is_file():
                for decision_id in promote_ids:
                    rp = _run(["bash", str(promote_script), "--id", decision_id])
                    if rp.returncode == 2:
                        res.promoted += 1
                    elif rp.returncode == 1:
                        res.errors.append(f"promote-decision({decision_id}): error")
    else:
        res.errors.append(f"wiki-capture-suggest.sh not found: {capture_script}")

    # Step 3 — bridge rebuild (if ≥1 promoted)
    if res.promoted > 0:
        bridge_script = wiki_dir / "wiki-bridge-rebuild.sh"
        if bridge_script.is_file():
            r3 = _run(["bash", str(bridge_script)])
            if r3.returncode == 1:
                res.errors.append(f"wiki-bridge-rebuild: exit=1 {r3.stderr.strip()[:100]}")
        else:
            res.errors.append(f"wiki-bridge-rebuild.sh not found: {bridge_script}")

    # Step 4 — audit stale (P0 BLOCKING — NEVER swallow exit 3)
    audit_script = wiki_dir / "wiki-audit-stale.sh"
    if audit_script.is_file():
        r4 = _run(["bash", str(audit_script)])
        if r4.returncode == 3:
            # P0 BLOCKING — parse and propagate
            p0, p1 = _parse_stale_counts(r4.stdout + r4.stderr)
            res.stale_p0 = max(p0, 1)  # ensure non-zero so is_p0_blocking() fires
            res.stale_p1 = p1
        elif r4.returncode == 2:
            _, p1 = _parse_stale_counts(r4.stdout + r4.stderr)
            res.stale_p1 = max(p1, 1)
        elif r4.returncode == 1:
            res.errors.append(f"wiki-audit-stale: exit=1 {r4.stderr.strip()[:100]}")
        # exit 0 → clean
    else:
        res.errors.append(f"wiki-audit-stale.sh not found: {audit_script}")

    # Step 5 — hot-sync (always non-blocking per ADR-0003)
    hot_script = wiki_dir / "wiki-hot-sync.sh"
    if hot_script.is_file():
        _run(["bash", str(hot_script)])  # failures logged by the script itself; non-blocking

    # Step 6 — link check (informational)
    link_script = wiki_dir / "wiki-link-check.sh"
    if link_script.is_file():
        r6 = _run(["bash", str(link_script), "--quiet"])
        if r6.returncode == 3:
            # Count violation lines from stderr
            violations = len([
                ln for ln in (r6.stdout + r6.stderr).splitlines()
                if "wikilink outside" in ln
            ])
            res.link_violations = max(violations, 1)
        elif r6.returncode == 1:
            res.errors.append(f"wiki-link-check: exit=1 {r6.stderr.strip()[:100]}")
    else:
        res.errors.append(f"wiki-link-check.sh not found: {link_script}")

    return res


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="study-phase",
        description="Orchestrate team.done Study steps 1-3,5,6 (step 4 P0-blocking).",
    )
    parser.add_argument(
        "--advisor",
        help="Advisor slug (for context in output; optional)",
    )
    parser.add_argument(
        "--since",
        default="HEAD~5",
        help="Git ref for wiki-capture-suggest --since (default: HEAD~5)",
    )
    args = parser.parse_args(argv)

    if args.advisor:
        roster = lifecycle_advisors(_data_root())
        # Validate only against a populated registry; an empty result means
        # discovery couldn't resolve the root, so skip rather than block the
        # study phase on a (merely informational) advisor arg.
        if roster and args.advisor not in roster:
            known = ", ".join(sorted(roster))
            print(
                f"study-phase: advisor '{args.advisor}' is not a known advisor.\nKnown: {known}",
                file=sys.stderr,
            )
            return 1

    wiki_dir = _wiki_scripts_dir()
    res = run_study(wiki_dir, since=args.since)

    # Emit errors to stderr (non-blocking unless P0)
    for err in res.errors:
        print(f"  WARN: {err}", file=sys.stderr)

    # Emit summary row to stdout
    row = res.summary_row()
    if row:
        print(row)
    else:
        print("[study-phase] clean — no findings")

    if res.is_p0_blocking():
        print(
            "\n[study-phase] P0 BLOCKING — wiki-audit-stale found contradictions/"
            "canonical-ref drift.\nTriage required before close-session commit.",
            file=sys.stderr,
        )
        return 3

    # A step that never ran is a finding about the phase itself. Exit 0 here would repeat
    # the defect this branch closes: the caller reads 0 as "all clean; omit the row".
    if res.has_findings() or res.ran_incompletely():
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())

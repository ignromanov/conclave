"""session-init.py — session initialization helper (Phase 4, spec 085 / plugin 098).

Absorbs team.start Steps 1/1b/1c + Overlay loading:
  Step 1:   gh-fetch + briefing build-and-compare (#14)
  Step 1b:  resume-scan (ops/specs/*/resume-prompt.md + ops/handoffs/*-<advisor>-*.md)
  Step 1c:  reflexion extract — last-3 sessions' `reflexion:` frontmatter
  Overlays: scan agent-memory/advisors/<advisor>/contracts/*.md

Arg: --advisor <slug>

Exit codes (mirror gh-fetch contract):
  0  = success, nothing regenerated (cache-hit / briefing unchanged)
  2  = success, briefing regenerated
  1  = error (the briefing itself could not be built)

A failed gh-fetch or git-fetch is NOT an error (#76): both are advisory inputs to
the briefing, so they log a FAILED line plus a `degraded:` marker and the run
continues. Exit 3 ("stale-fail") is no longer emitted — it returned BEFORE the
briefing was built at all, which starved no-GitHub instances of a briefing
entirely, and its documented meaning ("regen attempted but gh-fetch unavailable")
never matched that behaviour because regen had not yet been attempted.

Output: one compact summary block on stdout.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# Interpreter floor, enforced before the first thing that can fail below it — here, the lazy
# `enginelib` imports further down, whose module-level PEP 604 annotations are evaluated on
# import. Measured, not declared; see engine/__main__.py for the full note.
if sys.version_info < (3, 11):  # noqa: UP036 — see engine/__main__.py
    sys.stderr.write(
        f"Conclave requires Python 3.11 or newer.\n"
        f"This is Python {sys.version.split()[0]} at {sys.executable}.\n"
        f"Install a newer interpreter (e.g. `uv python install 3.13`) and re-run.\n"
    )
    sys.exit(1)

# Reach the enginelib package when run as a standalone lifecycle script
# (`python3 lifecycle/session_init.py`): sys.path[0] is lifecycle/, so add scripts/.
# Matches study_phase.py / gh_board_query.py (GH#1 it-8).
_SCRIPTS_DIR = str(Path(__file__).resolve().parent.parent)
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

# Forge is a META-advisor: a valid explicit invocation/lifecycle target, but not a
# domain advisor — excluded from dashboard auto-enumeration (Forge invariant #7:
# inventory is discovered, not hardcoded). See spec 2026-07-01 §3.3. Sourced from
# enginelib.advisors — the shared roster|META seam other call sites route through
# too (doctor.py, briefing/__main__.py) — rather than redeclared here.
from enginelib.advisors import (  # noqa: E402 (follows the sys.path bootstrap above)
    META_ADVISORS,
    with_meta,
)
from enginelib.paths import (  # noqa: E402
    check_legacy_data_root_env,
    walk_for_data_root,
)


def _project_dir(root: Path) -> Path:
    """The CONSUMER project directory this session belongs to.

    CLAUDE_PROJECT_DIR when set; otherwise, a `.conclave` DATA root's project is its parent, and
    any other root is already project-like (in-repo / test use)."""
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        return Path(project)
    if root.name == ".conclave":
        return root.parent
    return root


def _agents_dir(root: Path) -> Path:
    """Minted-advisor directory. Under the plugin, advisors are CC-discoverable agents at
    ${CLAUDE_PROJECT_DIR}/.claude/agents/ (sibling of the .conclave/ DATA root)."""
    return _project_dir(root) / ".claude" / "agents"


def _known_advisors(root: Path) -> set[str]:
    """Advisor slugs discovered from the plugin agent registry — never hardcoded.

    Globs `_agents_dir(root)/*.md`; slug = file stem. Excludes META_ADVISORS
    and exec-* stems (plugin meta/executor agents). Forge invariant #7: inventory
    is always discovered, so a roster hired in any instance is valid without editing
    this file.
    """
    advisors: set[str] = set()
    for agent_file in _agents_dir(root).glob("*.md"):
        stem = agent_file.stem
        if stem in META_ADVISORS or stem.startswith("exec-"):
            continue
        advisors.add(stem)
    return advisors


def _repo_root() -> Path:
    check_legacy_data_root_env()
    env = os.environ.get("CONCLAVE_AI_ROOT")
    if env:
        return Path(env).resolve()
    # Intentional divergence from enginelib.paths.repo_root(): that function adds a
    # CLAUDE_PROJECT_DIR → <dir>/.conclave branch for plugin mode (D-5).  Here we omit
    # it because session_init is always invoked from the SessionStart hook after
    # conclave_init has already persisted CONCLAVE_AI_ROOT — the shortcut is never
    # needed and adding it would silently mask a missing CONCLAVE_AI_ROOT.
    #
    # The env POLICY is this function's own; the marker is not. The walk it used to
    # carry started from __file__ and asked only for ops/ + .claude/, which the engine
    # checkout satisfies — so with no env set it answered with the CODE tree, the same
    # self-confirming match as GH#29. It now shares the one walk.
    found = walk_for_data_root()
    if found is not None:
        return found
    raise RuntimeError("session-init: cannot locate .ai root (set CONCLAVE_AI_ROOT)")


def _engine_root() -> Path:
    """engine/ CODE root — forge scripts/contracts are CODE, in the FLAT layout
    (engine/scripts, engine/contracts), never under a DATA-root `.claude/`.
    Derived from this file and from nothing else
    (engine/scripts/lifecycle/session_init.py -> engine/).

    CONCLAVE_ENGINE_ROOT is deliberately NOT honoured here (GH#187). What this function
    answers is where to find the SIBLING HELPERS this script dispatches — it is the `cwd`
    of every `python -m engine ...` child below and the path of feedback_triage.py — so the
    only correct answer is the tree the running file lives in. The variable is baked into
    `.claude/settings.json` by the initialiser and inherited by every process on the
    machine, which made it win over `__file__` in exactly the case the fallback existed
    for: a worktree's session_init.py ran the main checkout's engine, measured. That is the
    mechanism behind #171 — a stale copy answered a real triage with older semantics and
    left a diverged index. A copy that errors costs a turn; one that silently answers costs
    a wrong conclusion.

    A deliberate override still has its seam: point it at a tree and run THAT tree's script.
    """
    return Path(__file__).resolve().parents[2]


def _pin_engine_root_to_own_copy() -> list[str]:
    """Make the inherited CONCLAVE_ENGINE_ROOT agree with the copy that is executing.

    Returns the warning lines to print when it had to be corrected, empty otherwise.

    `_engine_root()` above fixes where THIS process looks for helpers, but the children it
    spawns re-read the variable for their own path resolution — so without this the fix
    would only half-land: code from the copy that is running, contracts and skills from
    whichever copy the environment names. That split is worse than either tree alone.

    Silent when the two agree, which is the healthy case the initialiser produces.
    """
    own = _engine_root()
    inherited = os.environ.get("CONCLAVE_ENGINE_ROOT")
    os.environ["CONCLAVE_ENGINE_ROOT"] = str(own)
    if inherited and Path(inherited).resolve() != own:
        return [
            f"  WARNING: CONCLAVE_ENGINE_ROOT points at {inherited}",
            f"  but this script lives in {own} — using its own copy (GH#187).",
        ]
    return []


def _scripts_dir() -> Path:
    return _engine_root() / "scripts"


# ---------------------------------------------------------------------------
# Step 1 — gh-fetch + briefing build-and-compare
# ---------------------------------------------------------------------------

def _step1_load_briefing(advisor: str, root: Path) -> tuple[int, list[str]]:
    """Returns (exit_code, summary_lines)."""
    scripts = _scripts_dir()
    lines: list[str] = []

    # Pin every git-reading child to the CONSUMER project. Both verbs below run with
    # cwd=engine/scripts, and both shell out to git: gh-fetch for the repo-scope fallback
    # (`git remote get-url origin`), git-fetch for the session snapshot (status / worktree
    # list / symbolic-ref). Unpinned they read the ENGINE checkout — which on a dev machine
    # is a real repo, so a consumer's DATA tree got the engine's branch, a stranger's issue
    # board, and the maintainer's absolute worktree paths.
    #
    # Overwrite only a falsy value: the var is an existing test/ops seam and a deliberate
    # one must survive, but `setdefault` also preserved an EMPTY one — and the resolver
    # reads empty as unset, so `export CONCLAVE_GIT_REMOTE_CWD=` silently restored the
    # pre-fix behaviour. Resolve before handing it over: the child runs in engine/scripts,
    # so a relative CLAUDE_PROJECT_DIR (`.`) would re-open the same leak from the other end.
    git_env = os.environ.copy()
    if not git_env.get("CONCLAVE_GIT_REMOTE_CWD"):
        git_env["CONCLAVE_GIT_REMOTE_CWD"] = str(_project_dir(root).resolve())

    # git-fetch (non-blocking — writes git-cache/state.md for briefing-build consumers)
    t0 = time.monotonic()
    git_result = subprocess.run(
        [sys.executable, "-m", "engine", "lifecycle", "git-fetch"],
        capture_output=True,
        text=True,
        cwd=str(scripts),
        env=git_env,
    )
    git_ms = int((time.monotonic() - t0) * 1000)
    git_code = git_result.returncode
    if git_code == 0:
        lines.append(f"  git-fetch: cache-hit ({git_ms}ms)")
    elif git_code == 2:
        lines.append(f"  git-fetch: refreshed ({git_ms}ms)")
    else:
        # Non-fatal: log and continue — git state is advisory context only.
        lines.append(f"  git-fetch: FAILED exit={git_code} ({git_ms}ms) — continuing")
        if git_result.stderr.strip():
            lines.append(f"    stderr: {git_result.stderr.strip()[:120]}")

    # gh-fetch — domain GitHub board; meta-advisors (forge) have none, so skip.
    if advisor in META_ADVISORS:
        lines.append("  gh-fetch: skipped (meta-advisor)")
    else:
        # Same pin as git-fetch above (see the note there): resolve_repos() layers
        # roster → local git remote → refuse, and the middle layer must read the CONSUMER's
        # origin or a null-roster instance pulls a stranger's issue board into the briefing.
        t0 = time.monotonic()
        result = subprocess.run(
            [sys.executable, "-m", "engine", "lifecycle", "gh-fetch", "--advisor", advisor],
            capture_output=True,
            text=True,
            cwd=str(scripts),
            env=git_env,
        )
        gh_ms = int((time.monotonic() - t0) * 1000)
        gh_code = result.returncode

        if gh_code == 0:
            lines.append(f"  gh-fetch: cache-hit ({gh_ms}ms)")
        elif gh_code == 2:
            lines.append(f"  gh-fetch: refreshed ({gh_ms}ms)")
        else:
            # #76: non-fatal, mirroring git-fetch above. Returning here short-circuited
            # the mtime-guard and briefing build, so an instance whose roster declares no
            # repos — where gh-fetch fails on EVERY run — never got a briefing at all for
            # any advisor not carved out as a meta-advisor. The GH board is one section of
            # the briefing; losing it must not cost the whole briefing.
            #
            # This is loop-discipline policy (a) — use stale data with a warning. Non-fatal
            # must not mean silent, so the failure carries an explicit degraded marker
            # rather than being inferable only from the absence of a line.
            lines.append(f"  gh-fetch: FAILED exit={gh_code} ({gh_ms}ms) — continuing")
            if result.stderr.strip():
                lines.append(f"    stderr: {result.stderr.strip()[:120]}")
            lines.append("  degraded: gh-data-unavailable (board sections built from stale cache)")

    # Build-and-compare (#14): mtime cannot tell freshness — the build's 18 scans
    # read git state and the specs tree, which can move without touching the
    # briefing file, and vice versa. So always build; the build itself writes only
    # when the rendered content actually differs from what's on disk, and reports
    # that in its stdout via wrote=/unchanged=.
    briefing_path = root / "agent-memory" / "advisors" / "briefings" / f"{advisor}.md"

    t0 = time.monotonic()
    bb_result = subprocess.run(
        [sys.executable, "-m", "engine", "briefing", "build", advisor],
        cwd=str(scripts),
        capture_output=True,
        text=True,
    )
    bb_ms = int((time.monotonic() - t0) * 1000)

    if bb_result.returncode != 0:
        lines.append(f"  briefing-build: FAILED exit={bb_result.returncode} ({bb_ms}ms)")
        if bb_result.stderr.strip():
            lines.append(f"    stderr: {bb_result.stderr.strip()[:120]}")
        return 1, lines

    if "unchanged=" in bb_result.stdout:
        lines.append(f"  briefing: unchanged ({bb_ms}ms)")
        lines.append(f"  briefing-path: {briefing_path}")
        # Briefing did not regenerate; gh-refresh (exit 2) is orthogonal and already
        # surfaced in the gh-fetch line. Reserve exit 2 strictly for a real regen.
        return 0, lines

    lines.append(f"  briefing-build: regenerated ({bb_ms}ms)")
    lines.append(f"  briefing-path: {briefing_path}")
    return 2, lines


# ---------------------------------------------------------------------------
# Step 1b — resume-scan
# ---------------------------------------------------------------------------

# A handoff whose whole purpose is "pick this up next session" and that nothing has
# touched in two weeks is not interrupted work — it is residue. Handoffs have no terminal
# state (#55): the scan ranks by mtime and never learns that the work shipped, so an
# exhausted one resurfaces forever. Two observed at 1374h and 1226h; both tracked PRs that
# merged in July. Age is a proxy for the consumed-state the format still lacks, so this
# demotes rather than hides: the lines are still printed, under a heading that says what
# they are. Raise the bar for a genuinely long-running thread via the env var.
_HANDOFF_STALE_HOURS = 336


def _handoff_stale_hours() -> int:
    raw = os.environ.get("CONCLAVE_HANDOFF_STALE_HOURS", "")
    try:
        return int(raw) if raw else _HANDOFF_STALE_HOURS
    except ValueError:
        return _HANDOFF_STALE_HOURS


def _step1b_resume_scan(advisor: str, root: Path) -> tuple[list[str], list[str]]:
    """Return (live, stale) lines describing interrupted work; both empty if none found."""
    found: list[str] = []
    stale: list[str] = []

    # ops/specs/*/resume-prompt.md
    specs_dir = root / "ops" / "specs"
    if specs_dir.is_dir():
        for prompt in sorted(specs_dir.glob("*/resume-prompt.md")):
            spec_name = prompt.parent.name
            try:
                mtime_s = int(prompt.stat().st_mtime)
                age_h = (int(time.time()) - mtime_s) // 3600
            except OSError:
                age_h = -1
            found.append(f"  spec-resume: {spec_name} ({prompt}) age={age_h}h")

    # ops/handoffs/*-<advisor>-*.md
    handoffs_dir = root / "ops" / "handoffs"
    if handoffs_dir.is_dir():
        for handoff in sorted(handoffs_dir.glob(f"*-{advisor}-*.md")):
            try:
                age_h = (int(time.time()) - int(handoff.stat().st_mtime)) // 3600
            except OSError:
                age_h = -1
            line = f"  handoff: {handoff.name} age={age_h}h"
            if 0 <= age_h < _handoff_stale_hours():
                found.append(line)
            else:
                stale.append(line)

    return found, stale


# ---------------------------------------------------------------------------
# Step 1c — reflexion extract (last-3 sessions)
# ---------------------------------------------------------------------------

def _extract_reflexion(path: Path) -> str:
    """Read the `reflexion:` value from YAML frontmatter of a session file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    in_front = False
    for line in text.splitlines():
        if line.strip() == "---":
            if not in_front:
                in_front = True
                continue
            else:
                break
        if in_front and line.startswith("reflexion:"):
            val = line[len("reflexion:"):].strip().strip('"').strip("'")
            return val
    return ""


def _step1c_reflexion(advisor: str, root: Path) -> list[str]:
    """Return up to 3 non-empty reflexion lines, empty list if all blank."""
    sessions_dir = root / "agent-memory" / "advisors" / "sessions"
    if not sessions_dir.is_dir():
        return []

    from enginelib.advisors import files_for_advisor

    session_files = sorted(
        files_for_advisor(sessions_dir, advisor, field="advisor"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:3]

    reflexions: list[str] = []
    for f in session_files:
        val = _extract_reflexion(f)
        if val and val != "—":
            reflexions.append(f"  - [{f.name}] {val}")

    return reflexions


# ---------------------------------------------------------------------------
# Overlay loading
# ---------------------------------------------------------------------------

def _scan_overlays(advisor: str, root: Path) -> list[str]:
    """Return list of overlay paths that exist (contract overrides).

    Base contracts: <plugin-root>/skills/advisor-contracts/references/ (D-4 home: plugin top-level).
    Advisor overlay dir: root/agent-memory/advisors/<advisor>/contracts/ (DATA-side).
    """
    forge_contracts = _engine_root().parent / "skills" / "advisor-contracts" / "references"
    advisor_contracts = root / "agent-memory" / "advisors" / advisor / "contracts"

    if not advisor_contracts.is_dir():
        return []

    overlays: list[str] = []
    if forge_contracts.is_dir():
        for base in sorted(forge_contracts.glob("*.md")):
            candidate = advisor_contracts / base.name
            if candidate.is_file():
                overlays.append(f"  overlay: {candidate.relative_to(root)}")

    return overlays


# ---------------------------------------------------------------------------
# Resolved findings surface (G2)
# ---------------------------------------------------------------------------

def _load_resolved_findings(advisor: str, root: Path, top_n: int = 3) -> list[str]:
    """Read agent-memory/hot.md; return up to top_n lines matching the advisor domain."""
    hot = root / "agent-memory" / "hot.md"
    if not hot.is_file():
        return []
    # feedback_archive writes "[RESOLVED <id>] <slug>:" where <slug> is the item's
    # location.skill (a "team.<adv>" slug) or, when absent, the bare agent slug.
    # Real hot.md lines are bare ("] forge:"), so match both forms — matching only
    # "team.<adv>" silently missed every bare-slug finding (feedback 66f71b/it-2).
    slugs = (f"] {advisor}:", f"] team.{advisor}:")
    matches: list[str] = []
    for line in hot.read_text(encoding="utf-8").splitlines():
        # #49b: archive now writes findings via the section-aware writer, so the
        # RESOLVED marker is embedded in a "- [ts] advisor: [RESOLVED …]" bullet
        # rather than at the line start — match by substring, not startswith.
        if "[RESOLVED " in line and any(s in line for s in slugs):
            matches.append(line)
    return matches[:top_n]


# ---------------------------------------------------------------------------
# Critical feedback pending check (G6)
# ---------------------------------------------------------------------------

def _check_critical_feedback_pending(root: Path) -> int:
    """Count open critical items in ops/feedback/_index/index.jsonl."""
    import json
    index_file = root / "ops" / "feedback" / "_index" / "index.jsonl"
    if not index_file.is_file():
        return 0
    count = 0
    for line in index_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            if row.get("severity") == "critical" and row.get("status") == "open":
                count += 1
        except (json.JSONDecodeError, AttributeError):
            pass
    return count


# ---------------------------------------------------------------------------
# Cadence guard (feedback triage check)
# ---------------------------------------------------------------------------

def _step_cadence_guard() -> list[str]:
    """Run feedback_triage.py --check; return lines to print if triage is due.

    Returns a list with one 'feedback:' line when triage is due, empty list
    otherwise. Missing script → returns a warning line; subprocess error → same.
    A non-zero exit is also a failed check: its stdout is not trusted (a crash can
    print a partial/stale triage_due= line before dying), so it must warn rather
    than silently collapse to "nothing due" — this function feeds render_dashboard(),
    printed at the top of every session, so a swallowed failure is invisible by
    construction.
    """
    triage_script = _engine_root() / "scripts" / "feedback" / "feedback_triage.py"
    if not triage_script.is_file():
        return ["  feedback: warning — feedback_triage.py not found, skipping cadence check"]

    try:
        result = subprocess.run(
            [sys.executable, str(triage_script), "--check"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return [f"  feedback: warning — could not run feedback_triage.py: {exc}"]

    if result.returncode != 0:
        return [
            f"  feedback: warning — feedback_triage.py --check exited {result.returncode}, "
            f"skipping cadence check"
        ]

    # Parse triage_due=<true|false> and open_items=<n> from stdout
    triage_due = False
    open_items = 0
    for line in result.stdout.splitlines():
        if line.startswith("triage_due="):
            triage_due = line.split("=", 1)[1].strip().lower() == "true"
        elif line.startswith("open_items="):
            try:
                open_items = int(line.split("=", 1)[1].strip())
            except ValueError:
                pass

    if triage_due:
        return [f"  feedback: triage due — {open_items} open reviews, run /conclave:triage"]
    return []


# ---------------------------------------------------------------------------
# Per-advisor summary builder (shared by main and render_dashboard)
# ---------------------------------------------------------------------------

def _advisor_summary(advisor: str, root: Path) -> tuple[int, list[str]]:
    """Build the summary lines for one advisor. No side effects (no print).

    Returns (exit_code, lines) where exit_code mirrors _step1_load_briefing's contract.
    """
    lines: list[str] = [f"[session-init] advisor={advisor}"]

    # Step 1
    step1_code, step1_lines = _step1_load_briefing(advisor, root)
    lines.extend(step1_lines)

    # Step 1b
    resume_items, stale_handoffs = _step1b_resume_scan(advisor, root)
    if resume_items:
        lines.append("  resume: interrupted work found:")
        lines.extend(resume_items)
    else:
        lines.append("  resume: none")
    if stale_handoffs:
        # Demoted, not hidden: the operator is the only one who can tell an abandoned
        # handoff from a slow one, and retiring it is a decision, not a side effect of
        # reading the board.
        lines.append(f"  stale handoffs (untouched >{_handoff_stale_hours()}h — "
                     f"archive to ops/handoffs/archive/ or delete):")
        lines.extend(stale_handoffs)

    # Step 1c
    reflexions = _step1c_reflexion(advisor, root)
    if reflexions:
        lines.append("  reflexion (last 3 sessions):")
        lines.extend(reflexions)
    else:
        lines.append("  reflexion: none")

    # Overlays
    overlays = _scan_overlays(advisor, root)
    if overlays:
        lines.append("  overlays:")
        lines.extend(overlays)
    else:
        lines.append("  overlays: none")

    # Cadence guard
    lines.extend(_step_cadence_guard())

    # Resolved findings (G2)
    resolved = _load_resolved_findings(advisor, root)
    if resolved:
        lines.append(f"  reflexion-resolved: {len(resolved)}")
        for line in resolved:
            lines.append(f"    - [{line}]")

    # Critical feedback pending (G6)
    crit_count = _check_critical_feedback_pending(root)
    if crit_count > 0:
        lines.append(f"  feedback_critical: {crit_count} items pending")

    lines.append(f"[session-init] done exit={step1_code}")
    return step1_code, lines


# ---------------------------------------------------------------------------
# render_dashboard — advisor-agnostic importable entrypoint
# ---------------------------------------------------------------------------

def render_dashboard(data_root: Path) -> str:
    """Return the session dashboard as a string across all hired advisors.

    Advisor-agnostic: iterates advisors discovered by _known_advisors(data_root).
    For an empty/uninitialized data root (no advisors, missing dirs) returns a
    minimal non-crashing string. Never raises.
    """
    try:
        advisors = _known_advisors(data_root)
    except Exception:
        advisors = set()

    if not advisors:
        return "session-init: no advisors hired\n"

    parts: list[str] = []
    for advisor in sorted(advisors):
        try:
            _, lines = _advisor_summary(advisor, data_root)
            parts.extend(lines)
            parts.append("")  # blank line between advisors
        except Exception as exc:
            parts.append(f"[session-init] advisor={advisor} ERROR: {exc}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="session-init",
        description=(
            "Session initialization: gh-fetch + briefing + resume-scan + reflexion + overlays."
        ),
    )
    parser.add_argument("--advisor", required=True, help="Canonical advisor slug (e.g. kai-cto)")
    args = parser.parse_args(argv)

    # Before anything dispatches a child: this script runs its own copy's helpers (GH#187).
    for warning in _pin_engine_root_to_own_copy():
        print(warning, file=sys.stderr)

    advisor = args.advisor
    try:
        root = _repo_root()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    known = _known_advisors(root)
    if advisor not in with_meta(known):
        listing = ", ".join(sorted(known)) or "(none hired — run /conclave:forge to hire)"
        print(
            f"session-init: advisor '{advisor}' not in instance registry.\nKnown: {listing}",
            file=sys.stderr,
        )
        return 1

    # Seed a well-formed hot.md skeleton if missing (#49b) so the first
    # `engine file decision` this session can't crash on an absent section header.
    # Best-effort: never block session start. Explicit path avoids the repo_root
    # divergence between session_init and enginelib.paths.
    try:
        from enginelib.memory import hot
        hot.init(hot_path=root / "agent-memory" / "hot.md")
    except OSError as exc:
        print(f"  hot: skeleton seed skipped ({exc})", file=sys.stderr)

    # Register this session in hot.md's Now — the section's only producer (#149).
    # Remove-then-append rather than a bare append: re-running session-init for an
    # advisor that is already open must refresh its line, not stack a second one.
    # Best-effort, exactly like the seed above: Now is a convenience, never a gate.
    try:
        from enginelib.memory import hot
        hot.remove("now", advisor, hot.SESSION_OPEN)
        hot.append("now", advisor, hot.SESSION_OPEN)
    except (OSError, ValueError) as exc:
        print(f"  hot: Now registration skipped ({exc})", file=sys.stderr)

    step1_code, lines = _advisor_summary(advisor, root)
    for line in lines:
        print(line)
    return step1_code


if __name__ == "__main__":
    sys.exit(main())

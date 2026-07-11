"""regen.py — shared regen entry point for briefing triggers.

Called by:
  - Layer 1: mutation scripts (close-session.py, file-decision.py,
    mention.py, hot-md-append.py) after writing.
  - Layer 2: scripts/hooks/post-commit git hook.

Usage (subprocess or direct):
    python3 -m briefing.regen <advisor> [<advisor> ...]
    python3 -m briefing.regen --from-commit   # reads touched advisors from stdin
    python3 -m briefing.regen --all           # all 5 canonical advisors

Exit codes: 0 = all OK, 1 = at least one regen failed (non-fatal for callers).
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from enginelib.advisors import known_advisors


def _known() -> list[str]:
    """Registry-driven advisor set for this instance (sorted). Empty when the
    DATA root can't be resolved (colocated / test envs) — never a hardcoded tuple."""
    from briefing.paths import repo_root
    try:
        return sorted(known_advisors(repo_root()))
    except RuntimeError:
        return []


def regen_advisor(advisor: str) -> bool:
    """Regenerate one advisor's briefing in-process via the briefing package. True on success."""
    try:
        from briefing.__main__ import main as _briefing_main
        return _briefing_main([advisor]) == 0
    except SystemExit as e:            # argparse exit on a bad arg
        return (e.code or 0) == 0
    except Exception:                  # best-effort, non-fatal (callers swallow)
        return False


def regen_advisors(advisors: list[str]) -> int:
    """Regen a list of advisors. Returns count of failures."""
    known = set(_known())
    failures = 0
    for advisor in advisors:
        if advisor not in known:
            print(f"[regen] skipping unknown advisor: {advisor}", file=sys.stderr)
            continue
        ok = regen_advisor(advisor)
        if not ok:
            failures += 1
    return failures


def advisors_from_commit_diff(diff_output: str, advisors: Sequence[str]) -> list[str]:
    """Parse advisor names from a `git diff --name-only` output.

    Matches paths like:
      agent-memory/advisors/decisions/2026-05-21-kai-cto-foo.md
      agent-memory/advisors/sessions/2026-05-21-nexus-ceo-bar.md
      agent-memory/advisors/mentions/shade-ciso/open/...
      agent-memory/hot.md  →  regen all advisors

    `advisors` is the instance roster to match against (registry-driven, injected
    by the caller — never a hardcoded tuple). Returns a de-duplicated, sorted list.
    """
    roster = tuple(advisors)
    found: set[str] = set()
    for line in diff_output.splitlines():
        line = line.strip()
        if not line:
            continue
        # hot.md touched → regen everything
        if line.endswith("agent-memory/hot.md") or line == "hot.md":
            return list(roster)
        # decisions / sessions files: YYYY-MM-DD-<advisor>-<slug>.md
        for part in ("decisions/", "sessions/"):
            if part in line:
                # filename is last component
                fname = Path(line).name
                # strip YYYY-MM-DD- prefix (10 chars + dash)
                rest = fname[11:] if len(fname) > 11 else fname
                for adv in roster:
                    if rest.startswith(adv + "-") or rest.startswith(adv + "."):
                        found.add(adv)
        # mentions/<advisor>/... directory
        if "/mentions/" in line:
            parts = line.split("/mentions/")
            if len(parts) > 1:
                candidate = parts[1].split("/")[0]
                if candidate in roster:
                    found.add(candidate)
    return sorted(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="briefing.regen",
        description="Regenerate advisor briefings on mutation events.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--all",
        action="store_true",
        help="Regenerate all canonical advisors.",
    )
    group.add_argument(
        "--from-commit",
        action="store_true",
        help="Read touched file list from stdin (git diff --name-only output).",
    )
    parser.add_argument(
        "advisors",
        nargs="*",
        metavar="advisor",
        help="One or more canonical advisor names.",
    )
    args = parser.parse_args(argv)

    if args.all:
        targets = _known()
    elif args.from_commit:
        diff_output = sys.stdin.read()
        targets = advisors_from_commit_diff(diff_output, _known())
        if not targets:
            print("[regen] no advisor paths touched — nothing to regen", file=sys.stderr)
            return 0
    elif args.advisors:
        targets = args.advisors
    else:
        parser.print_help(sys.stderr)
        return 2

    failures = regen_advisors(targets)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

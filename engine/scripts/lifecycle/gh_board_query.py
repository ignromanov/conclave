"""gh-board-query.py — GitHub project board query helper (Phase 4, spec 085).

Replaces two inline Python heredocs:
  - team.start Step 3b  → --mode advisor-open --advisor <slug>
  - github-issues-protocol.md L192-204 board-audit → --mode missing-fields

Project board number + owner are read from roster.yaml (github.board_number,
github.owner). Reads from `gh project item-list` stdout piped in via stdin, or
calls gh directly when --fetch is passed.

Modes:
  advisor-open     Filter non-Done items for a given advisor.
                   Prints: `{repo}#{num} [{status}] {title}` per match.
  missing-fields   Audit items for missing advisor/priority/type/status fields.
                   Prints: `{title:55} MISSING: {field ...}` per item with gaps.

Exit codes:
  0  = success (items printed or none found)
  1  = error (bad args, JSON parse failure, gh call failed)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Interpreter floor, enforced before the first thing that can fail below it — here, `roster`,
# which reaches `enginelib.roster` and its `ruamel` dependency. Without this a sub-floor user
# gets `ModuleNotFoundError: ruamel` — a dep error naming neither Python nor a version — because
# the venv that would carry the dep was never built for this interpreter. /conclave:start and
# github-issues-protocol.md launch this file directly.
# Measured, not declared; see engine/__main__.py for the full note.
if sys.version_info < (3, 11):  # noqa: UP036 — see engine/__main__.py
    sys.stderr.write(
        f"Conclave requires Python 3.11 or newer.\n"
        f"This is Python {sys.version.split()[0]} at {sys.executable}.\n"
        f"Install a newer interpreter (e.g. `uv python install 3.13`) and re-run.\n"
    )
    sys.exit(1)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))
import roster  # noqa: E402  (lib/ is not a package; path-inserted above)

# enginelib lives one level up from lifecycle/ — the same insert lib/roster.py
# performs (relative to its own location) for itself; repeated here so this
# module's import of enginelib does not rely on import order against `import
# roster` above.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from enginelib.paths import check_legacy_data_root_env, iter_advisor_skills  # noqa: E402

# Engine lifecycle/forge skills are CODE, not advisors — exclude them when deriving
# the advisor set from the DATA-root team.* registry.
_LIFECYCLE_SKILLS = {
    "start", "processing", "done", "handoff",
    "forge", "hire", "retro", "feedback", "feedback-triage",
}


def _data_root() -> str:
    """DATA root (per-instance). Mirrors lib/roster._resolve: env override, else
    engine-relative fallback for the colocated back-compat case."""
    check_legacy_data_root_env()
    return (
        os.environ.get("CONCLAVE_AI_ROOT")
        or os.path.join(os.path.dirname(__file__), "..", "..", "..")
    )


def canonical_advisors() -> set[str]:
    """Derive the advisor set from the on-disk registry (DATA-root .claude/skills/),
    minus engine lifecycle/forge skills. Empty when the registry is absent — callers
    treat empty as 'no enforcement' (degrade to permissive, not reject-all).

    Reads through enginelib.paths.iter_advisor_skills, the shared #54 discovery
    helper that dual-reads both the current `conclave-<id>` skill-dir layout and
    the legacy `team.<id>` one. The direct `team.`-prefix os.listdir() scan this
    replaced went blind the moment an advisor migrated to `conclave-<id>` (PRs
    #95/#97) — which is every advisor on a modern instance.
    """
    skills_base = Path(_data_root()) / ".claude" / "skills"
    return {
        bare
        for bare, _skill_md in iter_advisor_skills(skills_base)
        if bare not in _LIFECYCLE_SKILLS
    }

# Board coordinates come from roster.yaml (per-instance config), not hardcoded.
PROJECT_NUM = int(roster.get("github.board_number", "0") or 0)
PROJECT_OWNER = roster.get("github.owner")


def _fetch_items() -> list[dict[str, Any]]:
    """Call `gh project item-list` and return the items list."""
    result = subprocess.run(
        [
            "gh", "project", "item-list", str(PROJECT_NUM),
            "--owner", PROJECT_OWNER,
            "--format", "json",
            "--limit", "100",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()[:200]
        raise RuntimeError(f"gh project item-list failed (exit {result.returncode}): {stderr}")
    try:
        return json.loads(result.stdout).get("items", [])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh output is not valid JSON: {exc}") from exc


def _load_items(fetch: bool) -> list[dict[str, Any]]:
    if fetch:
        return _fetch_items()
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"stdin is not valid JSON: {exc}") from exc
    if isinstance(data, list):
        return data
    return data.get("items", [])


def _board_advisor_matches(field_value: str, advisor: str) -> bool:
    """Does a board item's `advisor` field claim *advisor*?

    The Project board's advisor field is a THIRD surface, distinct from the
    `advisor:<id>` label that `enginelib.advisors.advisor_label` builds: boards
    populated before the protocol settled carry the bare stem (`kai`), newer ones
    carry the whole id (`kai-cto`). Both are accepted — a read path that misses
    items is the failure this whole change exists to remove.

    Matching is token-wise, not substring: the old `stem in field` test let
    `nexus-ceo` claim a hypothetical `nexus-design`'s items, and a multi-advisor
    field is comma-separated, so tokens are what the field actually holds.
    """
    tokens = {t for t in re.split(r"[^a-z0-9-]+", field_value.strip().lower()) if t}
    return advisor in tokens or advisor.split("-")[0] in tokens


def mode_advisor_open(items: list[dict[str, Any]], advisor: str) -> int:
    """Print non-Done items tagged for advisor. Returns item count printed."""
    count = 0
    for item in items:
        if item.get("status") == "Done":
            continue
        advisor_field = str(item.get("advisor", "")).lower()
        if not _board_advisor_matches(advisor_field, advisor):
            continue
        content = item.get("content", {})
        repo = content.get("repository", "")
        num = content.get("number", "")
        title = str(content.get("title", ""))[:60]
        status = item.get("status", "")
        print(f"{repo}#{num} [{status}] {title}")
        count += 1
    if count == 0:
        print(f"(no open items for advisor:{advisor})")
    return count


def mode_missing_fields(items: list[dict[str, Any]]) -> int:
    """Print items missing required fields. Returns count of items with gaps."""
    count = 0
    for item in items:
        missing: list[str] = []
        if not item.get("advisor"):
            missing.append("advisor")
        if not item.get("priority"):
            missing.append("priority")
        if not item.get("type"):
            missing.append("type")
        if not item.get("status"):
            missing.append("status")
        if missing:
            title = str(item.get("title", ""))[:55]
            print(f"{title:55} MISSING: {' '.join(missing)}")
            count += 1
    if count == 0:
        print("(all items have required fields)")
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gh-board-query",
        description="Query the GitHub project board (roster: github.board_number/owner).",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["advisor-open", "missing-fields"],
        help="Query mode",
    )
    parser.add_argument(
        "--advisor",
        help="Canonical advisor slug — required for advisor-open mode",
    )
    parser.add_argument(
        "--fetch",
        action="store_true",
        default=False,
        help="Call gh directly instead of reading from stdin",
    )
    args = parser.parse_args(argv)

    if args.mode == "advisor-open" and not args.advisor:
        print("gh-board-query: --advisor required for advisor-open mode", file=sys.stderr)
        return 1

    canonical = canonical_advisors()
    if args.advisor and canonical and args.advisor not in canonical:
        known = ", ".join(sorted(canonical))
        print(
            f"gh-board-query: advisor '{args.advisor}' is not in the instance registry.\nKnown: {known}",
            file=sys.stderr,
        )
        return 1

    try:
        items = _load_items(args.fetch)
    except RuntimeError as exc:
        print(f"gh-board-query: {exc}", file=sys.stderr)
        return 1

    if args.mode == "advisor-open":
        mode_advisor_open(items, args.advisor)
    else:
        mode_missing_fields(items)

    return 0


if __name__ == "__main__":
    sys.exit(main())

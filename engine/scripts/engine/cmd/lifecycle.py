"""engine/cmd/lifecycle.py — adapter for `engine lifecycle <verb>`.

Each verb has its own sub-subparser (PER-VERB design, unlike audit's shared-positional).
Adapters set args._runlog_verb and args._runlog_args for the dispatcher run-log hook.
"""
from __future__ import annotations

import os
import sys
from datetime import UTC
from pathlib import Path


def _resolve_finding(args) -> int:
    from enginelib.lifecycle import resolve_finding

    args._runlog_verb = "resolve-finding"
    if not args.path or not args.note:
        print('usage: engine lifecycle resolve-finding <path> --note "<text>"', file=sys.stderr)
        args._runlog_args = f"path={args.path or ''}"
        return 1
    path = Path(args.path)
    args._runlog_args = f"path={path}"
    if not path.is_file():
        print(f"file not found: {path}", file=sys.stderr)
        return 1
    status = resolve_finding.run(path, args.note)
    if status == "no-tags":
        print(f"file lacks status/open tag — refusing to transition: {path}", file=sys.stderr)
        return 1
    return 0


def _archive_aged(args) -> int:
    from enginelib.lifecycle import archive_aged
    from enginelib.paths import agent_memory_dir

    args._runlog_verb = "archive-aged"
    root = Path(args.root) if args.root else agent_memory_dir()
    if not root.is_dir():
        print(f"archive-aged: root directory not found: {root}", file=sys.stderr)
        args._runlog_args = f"root={root},archived=0"
        return 1
    paths = archive_aged.run(root, args.age_days, args.dry_run)
    if args.dry_run:
        for p in paths:
            print(f"WOULD ARCHIVE: {p}")
        args._runlog_args = f"root={root},archived=0"
    else:
        print(f"archived {len(paths)} file(s) older than {args.age_days} days under {root}")
        args._runlog_args = f"root={root},archived={len(paths)}"
    return 0


def _archive_handoff(args) -> int:
    from enginelib.lifecycle import archive_handoff
    from enginelib.paths import handoffs_dir

    args._runlog_verb = "archive-handoff"
    root = Path(args.handoffs_dir) if args.handoffs_dir else handoffs_dir()
    if not root.is_dir():
        print(f"archive-handoff: handoffs directory not found: {root}", file=sys.stderr)
        args._runlog_args = f"dir={root},archived=0"
        return 1
    try:
        moves = archive_handoff.run(root, args.names, args.dry_run)
    except ValueError as exc:
        print(f"archive-handoff: {exc}", file=sys.stderr)
        args._runlog_args = f"dir={root},archived=0"
        return 1
    if args.dry_run:
        for src, _dest in moves:
            print(f"WOULD ARCHIVE: {src.name}")
        args._runlog_args = f"dir={root},archived=0"
    else:
        for src, _dest in moves:
            print(f"archived: {src.name}")
        args._runlog_args = f"dir={root},archived={len(moves)}"
    return 0


def _git_fetch(args) -> int:
    import sys

    from enginelib.lifecycle import git_fetch
    from enginelib.paths import git_cache_dir

    args._runlog_verb = "git-fetch"
    args._runlog_args = f"no_cache={1 if args.no_cache else 0}"
    status = git_fetch.run(args.no_cache)
    if status == "lock-error":
        print(f"git-fetch: could not acquire lock for {git_cache_dir() / 'state.md'}", file=sys.stderr)
        return 1
    return 0 if status == "hit" else 2   # refreshed


def _gh_fetch(args) -> int:
    from enginelib.lifecycle import gh_fetch
    from enginelib.paths import snapshot_path_for_advisor

    args._runlog_verb = "gh-fetch"
    if not args.advisor:
        print("missing required argument: --advisor", file=sys.stderr)
        args._runlog_args = "advisor=,no_cache=" + ("1" if args.no_cache else "0")
        return 1
    args._runlog_advisor = args.advisor
    args._runlog_args = f"advisor={args.advisor},no_cache={1 if args.no_cache else 0}"
    status = gh_fetch.run(args.advisor, args.no_cache)
    if status == "lock-error":
        print(
            f"gh-fetch: could not acquire lock for {snapshot_path_for_advisor('gh', args.advisor)}",
            file=sys.stderr,
        )
        return 1
    if status == "gh-error":
        print(
            f"gh-fetch: gh search failed for advisor:{args.advisor.split('-')[0]}"
            " — cache left stale",
            file=sys.stderr,
        )
        return 1
    if status == "unscoped":
        print(
            "gh-fetch: no usable repo scope (roster declared none, or declared one that "
            "resolve_repos refused — see any `roster:` line above) — refusing account-wide "
            "search to avoid cross-project leak; cache left stale",
            file=sys.stderr,
        )
        return 1
    return 0 if status == "hit" else 2   # refreshed


def _gh_repos(args) -> int:
    """Print the resolved GH repo scope, one owner-qualified slug per line.

    Exists so advisor-facing command prose can iterate a resolved list instead of interpolating
    roster keys by hand: `-R "$OWNER/$(roster.py github.ai_repo)"` collapses to the malformed
    `owner/` on a single-repo instance. Same layering and same fail-closed refusal as gh-fetch —
    one resolution path, two callers.
    """
    from enginelib import roster
    from enginelib.lifecycle import gh_fetch

    args._runlog_verb = "gh-repos"
    owner = roster.roster_get("github.owner").strip()
    repos = gh_fetch.resolve_repos(owner)
    args._runlog_args = f"owner={owner},repos={len(repos)}"
    if not repos:
        print(
            "gh-repos: no usable repo scope (roster declared none, or declared one that "
            "resolve_repos refused — see any `roster:` line above) — refusing to emit an "
            "unscoped list",
            file=sys.stderr,
        )
        return 1
    for repo in repos:
        print(repo)
    return 0


def _migrate_add_type(args) -> int:
    from enginelib.lifecycle import migrate_add_type
    from enginelib.paths import agent_memory_dir

    args._runlog_verb = "migrate-add-type"
    root = Path(args.root) if args.root else agent_memory_dir()
    if not root.is_dir():
        print(f"migrate-add-type: root directory not found: {root}", file=sys.stderr)
        args._runlog_args = f"root={root},injected=0,skipped=0"
        return 1
    res = migrate_add_type.run(root, args.dry_run)
    for p in res.skipped_paths:
        print(f"migrate-add-type: skip (unknown path mapping): {p}", file=sys.stderr)
    if args.dry_run:
        for line in res.would_inject:
            print(f"WOULD INJECT {line}")
    else:
        print(f"migrate-add-type: injected={res.injected} skipped={res.skipped} under {root}")
    args._runlog_args = f"root={root},injected={res.injected},skipped={res.skipped}"
    return 0


def _migrate_router_bootstrap(args) -> int:
    from enginelib.lifecycle import migrate_router_bootstrap
    from enginelib.paths import project_skills_dir

    args._runlog_verb = "migrate-router-bootstrap"
    root = Path(args.root) if args.root else project_skills_dir()
    if not root.is_dir():
        print(f"migrate-router-bootstrap: skills dir not found: {root}", file=sys.stderr)
        args._runlog_args = f"root={root},updated=0,skipped=0"
        return 1
    try:
        res = migrate_router_bootstrap.run(root, args.dry_run)
    except RuntimeError as exc:
        print(f"migrate-router-bootstrap: {exc}", file=sys.stderr)
        args._runlog_args = f"root={root},updated=0,skipped=0"
        return 1
    if args.dry_run:
        for path in res.would_update:
            print(f"WOULD REFRESH {path}")
    print(f"migrate-router-bootstrap: updated={res.updated} skipped={res.skipped} under {root}")
    args._runlog_args = f"root={root},updated={res.updated},skipped={res.skipped}"
    return 0


def _runlog_summary(args) -> int:
    import sys
    from datetime import datetime

    from enginelib.lifecycle import runlog_summary

    args._runlog_verb = "runlog-summary"
    if not args.advisor:
        print("runlog-summary: --advisor required", file=sys.stderr)
        args._runlog_args = "advisor="
        return 2
    date_str = args.date or datetime.now(UTC).strftime("%Y-%m-%d")
    args._runlog_args = f"advisor={args.advisor},date={date_str}"
    print(runlog_summary.run(args.advisor, date_str))
    # 0 even for 🔴, deliberately (GH#186). This verb reports on failures, it does not have
    # them: it succeeded whenever it produced the row. Exiting non-zero on a red session
    # would (a) log THIS command as one more failed script into the very run-log it just
    # summarised, so re-running it inflates the count it reports, and (b) trip the
    # done-checklist's "non-zero lifecycle exit is P0" rule on the reporter rather than on
    # the script that actually broke. The failure is surfaced in the row's text instead —
    # which is why that text must name the script and its exit code.
    return 0


def _migrate_add_tags(args) -> int:
    from enginelib.lifecycle import migrate_add_tags
    from enginelib.paths import agent_memory_dir

    args._runlog_verb = "migrate-add-tags"
    root = Path(args.root) if args.root else agent_memory_dir()
    if not root.is_dir():
        print(f"migrate-add-tags: root directory not found: {root}", file=sys.stderr)
        args._runlog_args = f"root={root},injected=0,skipped=0"
        return 1
    res = migrate_add_tags.run(root, args.dry_run)
    for p in res.skipped_paths:
        print(f"migrate-add-tags: skip (no type: found — run migrate-add-type first): {p}", file=sys.stderr)
    if args.dry_run:
        for line in res.would_inject:
            print(f"WOULD INJECT {line}")
    else:
        print(f"migrate-add-tags: injected={res.injected} skipped={res.skipped} under {root}")
    args._runlog_args = f"root={root},injected={res.injected},skipped={res.skipped}"
    return 0


def register(sub) -> None:
    p = sub.add_parser("lifecycle", help="Lifecycle maintenance commands.")
    vsub = p.add_subparsers(dest="lifecycle_verb", required=True)

    aa = vsub.add_parser(
        "archive-aged",
        help="Sweep aged status/resolved files → status/archived.",
    )
    aa.add_argument(
        "--root",
        default=None,
        help="Vault root (default: agent-memory dir).",
    )
    aa.add_argument(
        "--age-days",
        type=int,
        default=int(os.environ.get("ARCHIVE_AGE_DAYS", "30")),
        help="Age threshold in days (default 30; env ARCHIVE_AGE_DAYS).",
    )
    aa.add_argument(
        "--dry-run",
        action="store_true",
        help="Report candidates without mutating.",
    )
    aa.set_defaults(func=_archive_aged)

    ah = vsub.add_parser(
        "archive-handoff",
        help="Move exhausted handoffs into ops/handoffs/archive/ (terminal state).",
    )
    ah.add_argument("names", nargs="+", help="Handoff filenames (bare names, not paths).")
    ah.add_argument(
        "--handoffs-dir",
        dest="handoffs_dir",
        default=None,
        help="Handoffs directory (default: DATA-root ops/handoffs).",
    )
    ah.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would move without moving it.",
    )
    ah.set_defaults(func=_archive_handoff)

    rf = vsub.add_parser("resolve-finding", help="Transition a status/open finding to status/resolved with a note.")
    rf.add_argument("path", nargs="?", default=None, help="Path to the finding .md file.")
    rf.add_argument("--note", default=None, help="Resolution note text.")
    rf.set_defaults(func=_resolve_finding)

    gf = vsub.add_parser("git-fetch", help="Snapshot git state to cache (TTL).")
    gf.add_argument("--no-cache", action="store_true", help="Force re-fetch, ignoring cache.")
    gf.set_defaults(func=_git_fetch)

    gh = vsub.add_parser("gh-fetch", help="Snapshot GH issues for an advisor to cache (TTL).")
    gh.add_argument("--advisor", default=None, help="Advisor id (e.g. kai-cto).")
    gh.add_argument("--no-cache", action="store_true", help="Force re-fetch, ignoring cache.")
    gh.set_defaults(func=_gh_fetch)

    gr = vsub.add_parser("gh-repos", help="Print the resolved GH repo scope, one slug per line.")
    gr.set_defaults(func=_gh_repos)

    mt = vsub.add_parser("migrate-add-type", help="Inject type: frontmatter by path mapping.")
    mt.add_argument("--root", default=None, help="Root dir (default: agent-memory).")
    mt.add_argument("--dry-run", action="store_true", help="Report WOULD INJECT without mutating.")
    mt.set_defaults(func=_migrate_add_type)

    mg = vsub.add_parser("migrate-add-tags", help="Inject tags: [op/<type>] after the type: line.")
    mg.add_argument("--root", default=None, help="Root dir (default: agent-memory).")
    mg.add_argument("--dry-run", action="store_true", help="Report WOULD INJECT without mutating.")
    mg.set_defaults(func=_migrate_add_tags)

    mr = vsub.add_parser(
        "migrate-router-bootstrap",
        help="Refresh the session-init bash fence in minted routers from the template.",
    )
    mr.add_argument("--root", default=None, help="Skills dir (default: .claude/skills).")
    mr.add_argument("--dry-run", action="store_true", help="Report WOULD REFRESH without mutating.")
    mr.set_defaults(func=_migrate_router_bootstrap)

    rs = vsub.add_parser("runlog-summary", help="Emit the Infra sidecar one-line run-log summary.")
    rs.add_argument("--advisor", default=None, help="Advisor slug to filter rows by.")
    rs.add_argument("--date", default=None, help="YYYY-MM-DD (default: today UTC).")
    rs.set_defaults(func=_runlog_summary)

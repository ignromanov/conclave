"""engine/cmd/memory.py — adapter for `engine memory <verb>`.

Verbs:
  index       — rebuild advisors/INDEX.md (port of memory-index.sh)
  hot-init    — initialize agent-memory/hot.md from template (port of hot-md-init.sh)
  hot-append  — atomically append a line to a hot.md section (port of hot-md-append.sh)
"""
from __future__ import annotations

import sys
from datetime import date as _date_cls


def _index(args) -> int:
    from enginelib.memory.index import rebuild

    now = args.now or _date_cls.today().isoformat()
    args._runlog_verb = "memory-index"
    args._runlog_args = f"now={now}"
    try:
        rebuild(now)
    except ValueError as e:
        print(f"memory-index: {e}", file=sys.stderr)
        return 1
    return 0


def _hot_init(args) -> int:
    from enginelib.memory.hot import init
    from enginelib.paths import hot_md_path

    args._runlog_verb = "memory-hot-init"
    args._runlog_args = f"force={args.force}"
    status = init(force=args.force)
    if status == "exists":
        print(f"[hot-md-init] {hot_md_path()} exists; use --force to overwrite", file=sys.stderr)
        return 0
    print(f"[hot-md-init] wrote {hot_md_path()}", file=sys.stderr)
    return 0


def _hot_append(args) -> int:
    from enginelib.memory.hot import append

    args._runlog_verb = "memory-hot-append"
    args._runlog_args = f"section={args.section or ''},advisor={args.advisor or ''}"
    args._runlog_advisor = args.advisor or "shared"
    try:
        append(args.section or "", args.advisor or "", args.line or "", no_compact=args.no_compact)
    except FileNotFoundError as e:
        print(f"hot-md-append: {e}", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"hot-md-append: {e}", file=sys.stderr)
        return 2
    print(f"[hot-md-append] appended to {args.section} by {args.advisor}", file=sys.stderr)
    return 0


def register(sub) -> None:
    p = sub.add_parser("memory", help="Memory index and related operations.")
    vsub = p.add_subparsers(dest="memory_verb", required=True)

    ix = vsub.add_parser("index", help="Rebuild the advisor memory INDEX.md.")
    ix.add_argument("--now", default=None, help="Date override (YYYY-MM-DD).")
    ix.set_defaults(func=_index)

    hi = vsub.add_parser("hot-init", help="Initialize agent-memory/hot.md from template.")
    hi.add_argument("--force", action="store_true", help="Overwrite existing hot.md.")
    hi.set_defaults(func=_hot_init)

    ha = vsub.add_parser("hot-append", help="Atomically append a line to a hot.md section.")
    ha.add_argument("--section", default=None, help="Section: now|open-threads|recent-decisions|watch.")
    ha.add_argument("--advisor", default=None, help="Advisor or executor identifier.")
    ha.add_argument("--line", default=None, help="Single-line content to append.")
    ha.add_argument("--no-compact", action="store_true", help="Skip post-append compaction.")
    ha.set_defaults(func=_hot_append)

"""engine/cmd/advisor.py — adapter for `engine advisor <verb>`.

Per-verb sub-subparser design (matches register.py). Adapters set _runlog_verb.
Exit codes: 1 validation error, 2 collision, 0 success (JSON to stdout).
"""
from __future__ import annotations

import json
import sys


def _create(args) -> int:
    from enginelib import advisor

    args._runlog_verb = "advisor-create"
    args._runlog_args = f"id={args.id or ''}"
    opts = advisor.AdvisorOpts(
        id=args.id or "",
        role=args.role or "",
        color=args.color or "",
        name=args.name or "",
        emoji=args.emoji or "",
        tone=args.tone or "",
    )
    try:
        info = advisor.create(opts)
    except FileExistsError as e:
        print(str(e), file=sys.stderr)
        return 2
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(info, indent=2))
    return 0


def _scaffold_router(args) -> int:
    from enginelib import router

    args._runlog_verb = "advisor-scaffold-router"
    args._runlog_args = f"id={args.id or ''}"
    try:
        info = router.scaffold_router(args.id or "", force=getattr(args, "force", False))
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(json.dumps(info, indent=2))
    return 0


def register(sub) -> None:
    p = sub.add_parser("advisor", help="Advisor management commands.")
    vsub = p.add_subparsers(dest="advisor_verb", required=True)

    c = vsub.add_parser("create", help="Scaffold a new flat advisor agent-def.")
    c.add_argument("--id", default="", help="Advisor slug (^[a-z0-9-]+$).")
    c.add_argument("--role", default="", help="Advisor role description.")
    c.add_argument("--color", default="", help="Color name.")
    c.add_argument("--name", default="", help="Display name (defaults to --id).")
    c.add_argument("--emoji", default="", help="Emoji glyph (default 🧭).")
    c.add_argument("--tone", default="", help="Tone hint (default pragmatic).")
    c.set_defaults(func=_create)

    r = vsub.add_parser("scaffold-router", help="Scaffold the /conclave-<id> router skill.")
    r.add_argument("--id", default="", help="Advisor slug (^[a-z0-9-]+$).")
    r.add_argument(
        "--force", action="store_true",
        help="Overwrite even an enriched wrapper (default: skip to preserve enrichment).",
    )
    r.set_defaults(func=_scaffold_router)

"""engine/cmd/briefing.py — adapter for `engine briefing <verb>`.

Verbs:
  build         — generate a briefing for one canonical advisor (port of briefing-build.sh)
  team-digest   — emit briefings/_team.md (one line per advisor)
"""
from __future__ import annotations

import sys


def _build(args) -> int:
    # Accept either the positional advisor or the --advisor alias (#52) — the alias
    # aligns `briefing build` with `file decision --by` / `session close --advisor`.
    advisor = args.advisor_flag or args.advisor_pos
    if not advisor:
        print("briefing build: advisor required (positional or --advisor)", file=sys.stderr)
        return 2
    args._runlog_verb = "briefing-build"
    args._runlog_advisor = advisor
    args._runlog_args = f"advisor={advisor}"
    from briefing.__main__ import main as _bmain
    return _bmain([advisor])


def _team_digest(args) -> int:
    args._runlog_verb = "team-digest-build"
    args._runlog_args = f"advisors={','.join(args.advisors) if args.advisors else 'all'}"
    from briefing.team_digest import main as _tdmain
    return _tdmain(args.advisors)


def register(sub) -> None:
    p = sub.add_parser("briefing", help="Briefing generation operations.")
    vsub = p.add_subparsers(dest="briefing_verb", required=True)

    bd = vsub.add_parser("build", help="Generate a briefing for a canonical advisor.")
    bd.add_argument("advisor_pos", nargs="?", metavar="advisor", default=None,
                    help="Canonical advisor name (e.g. kai-cto).")
    bd.add_argument("--advisor", dest="advisor_flag", default=None,
                    help="Canonical advisor name (alias for the positional form).")
    bd.set_defaults(func=_build)

    td = vsub.add_parser("team-digest", help="Emit briefings/_team.md (one line per advisor).")
    td.add_argument("advisors", nargs="*", metavar="advisor",
                    help="Canonical advisor names (default: all).")
    td.set_defaults(func=_team_digest)

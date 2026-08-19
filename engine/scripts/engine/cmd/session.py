"""engine/cmd/session.py — adapter for `engine session <verb>`.

Verbs:
  close          — close an advisor session (port of close-session.sh)
  emission-gate  — mandatory emission check for /conclave:done (port of emission-gate.sh)
"""
from __future__ import annotations

import os
import sys
from datetime import date as _date_cls


def _close(args) -> int:
    from enginelib.filing import CloseSessionOpts, close_session

    args._runlog_verb = "session-close"
    args._runlog_args = f"advisor={args.advisor or ''},slug={args.slug or ''}"
    args._runlog_advisor = args.advisor or "shared"

    opts = CloseSessionOpts(
        advisor=args.advisor or "",
        slug=args.slug or "",
        date=args.date or "",
        body_file=args.body_file or "",
        goal=args.goal or "",
        followups_file=args.followups_file or "",
        decisions_csv=args.decisions_csv or "",
        issues_csv=args.issues_csv or "",
        mentions_csv=args.mentions_csv or "",
        handoff_file=args.handoff_file or "",
        handoff_to=args.handoff_to or "",
        handoff_priority=args.handoff_priority or "",
        handoff_title=args.handoff_title or "",
        handoff_slug=args.handoff_slug or "",
        duration_estimate=args.duration_estimate or "",
        reflexion=args.reflexion or "",
    )
    try:
        close_session(opts)
    except ValueError as e:
        print(f"close-session: {e}", file=sys.stderr)
        return 1
    return 0


def _emission_gate(args) -> int:
    from enginelib.filing import emission_gate
    from enginelib.paths import check_legacy_data_root_env

    args._runlog_verb = "session-emission-gate"

    check_legacy_data_root_env()
    ai_root = os.environ.get("CONCLAVE_AI_ROOT")
    advisor = os.environ.get("ADVISOR_NAME")
    session_id = os.environ.get("SESSION_ID")
    today = os.environ.get("TODAY") or _date_cls.today().isoformat()

    if not ai_root:
        print("emission-gate: CONCLAVE_AI_ROOT must be set", file=sys.stderr)
        return 1
    if not advisor:
        print("emission-gate: ADVISOR_NAME must be set", file=sys.stderr)
        return 1
    if not session_id:
        print("emission-gate: SESSION_ID must be set", file=sys.stderr)
        return 1

    blocking_path = emission_gate(ai_root, advisor, session_id, today)
    if blocking_path is not None:
        print(f"WARNING: Missing or draft emission: {blocking_path}", file=sys.stderr)
        print("Run /conclave:feedback before completing /conclave:done.", file=sys.stderr)
        return 1
    return 0


def register(sub) -> None:
    p = sub.add_parser("session", help="Session lifecycle operations (close, emission-gate).")
    vsub = p.add_subparsers(dest="session_verb", required=True)

    c = vsub.add_parser("close", help="Close an advisor session.")
    c.add_argument("--advisor", default=None)
    c.add_argument("--slug", default=None)
    c.add_argument("--date", default=None)
    c.add_argument("--body-file", dest="body_file", default=None)
    c.add_argument("--goal", default=None)
    c.add_argument("--followups-file", dest="followups_file", default=None)
    c.add_argument("--decisions", dest="decisions_csv", default=None)
    c.add_argument("--issues-touched", dest="issues_csv", default=None)
    c.add_argument("--resolves-mentions", dest="mentions_csv", default=None)
    c.add_argument("--handoff-file", dest="handoff_file", default=None)
    c.add_argument("--handoff-to", dest="handoff_to", default=None)
    c.add_argument("--handoff-priority", dest="handoff_priority", default=None)
    c.add_argument("--handoff-title", dest="handoff_title", default=None)
    c.add_argument("--handoff-slug", dest="handoff_slug", default=None)
    c.add_argument("--duration-estimate", dest="duration_estimate", default=None)
    c.add_argument("--reflexion", default=None)
    c.set_defaults(func=_close)

    eg = vsub.add_parser("emission-gate", help="Check mandatory emission file for /conclave:done.")
    eg.set_defaults(func=_emission_gate)

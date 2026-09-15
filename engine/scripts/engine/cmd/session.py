"""engine/cmd/session.py — adapter for `engine session <verb>`.

Verbs:
  close          — close an advisor session (port of close-session.sh)
  checkpoint     — record one unit of work in the in-flight session record (spec 117)
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
        handoff_issue=args.handoff_issue or "",
        handoff_no_issue=args.handoff_no_issue or "",
        duration_estimate=args.duration_estimate or "",
        reflexion=args.reflexion or "",
    )
    try:
        close_session(opts)
    except ValueError as e:
        print(f"close-session: {e}", file=sys.stderr)
        return 1
    return 0


def _checkpoint(args) -> int:
    """One verb, two line kinds (design §4). The refusal is the feature.

    R2 calls intent and completion "distinct lines", not distinct acts, so two verbs would
    double the surface every gate and contract must name for one bit of information.

    A `--done` must carry evidence and that evidence must resolve *now*: R6's whole point is
    that `M` rests on an executed external check rather than on the agent's summary. Writing
    the line first and checking later would make the record a diary — the failure mode the
    spec cites at 44-76% self-reported-completion error.

    The opposite rule applies four paragraphs away in the spec and someone will reach for the
    wrong one: R11, on a *part's* `verify:` predicate, demands a predicate that is currently
    FAILING, because it is a closing condition. R6, here, demands a check that is currently
    TRUE, because it is a completion record. Same machinery, opposite admission rules.
    """
    from enginelib.checkpoint import record, store
    from enginelib.checkpoint.evidence import Roots, resolve_all

    args._runlog_verb = "session-checkpoint"
    args._runlog_args = f"kind={'intent' if args.intent else 'done'}"

    advisor = args.advisor or os.environ.get("ADVISOR_NAME") or ""
    if not advisor:
        print("checkpoint: --advisor, or ADVISOR_NAME in the environment", file=sys.stderr)
        return 1

    kind, text = ((record.KIND_INTENT, args.intent) if args.intent
                  else (record.KIND_DONE, args.done))
    refs = tuple(args.evidence or ())

    if kind == record.KIND_INTENT and refs:
        print("checkpoint: --intent takes no --evidence — nothing has completed yet",
              file=sys.stderr)
        return 1
    if kind == record.KIND_DONE:
        if not refs:
            print("checkpoint: --done needs --evidence (commit:, file:, predicate:, issue:) — "
                  "a completion nothing can confirm is not a completion (R6)", file=sys.stderr)
            return 1
        # Every ref, not merely one: an unresolved ref is a typo or a claim, and keeping it
        # beside the resolved ones would put unverified text in the record's evidence field.
        refused = [c for c in resolve_all(refs, Roots.current()) if not c.ok]
        for check in refused:
            print(f"checkpoint: refused {check.ref} — {check.reason}", file=sys.stderr)
        if refused:
            return 1

    try:
        line = record.render(kind, text, evidence=refs)
    except ValueError as exc:
        print(f"checkpoint: {exc}", file=sys.stderr)
        return 1

    session_id = os.environ.get("CLAUDE_CODE_SESSION_ID")
    path = store.ensure(advisor, session_id)
    store.append(path, line)
    if store.token_for(session_id) == store.UNFENCED:
        print("checkpoint: no CLAUDE_CODE_SESSION_ID — this record is fenced to no session, "
              "so a concurrent session of the same advisor shares it", file=sys.stderr)
    print(f"{path}: {line}")
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
    c.add_argument("--handoff-issue", dest="handoff_issue", default=None,
                   help="Resolvable reference for the handoff: #12, AI#12, owner/repo#12, "
                        "or a github.com issue/pull URL (#55).")
    c.add_argument("--handoff-no-issue", dest="handoff_no_issue", default=None,
                   help="Why the handoff has no issue to resolve against.")
    c.add_argument("--duration-estimate", dest="duration_estimate", default=None)
    c.add_argument("--reflexion", default=None)
    c.set_defaults(func=_close)

    cp = vsub.add_parser(
        "checkpoint",
        help="Record one unit of work: --intent, or --done with resolving --evidence.",
    )
    mode = cp.add_mutually_exclusive_group(required=True)
    mode.add_argument("--intent", default=None, metavar="TEXT",
                      help="A unit taken on. No evidence — nothing has completed yet.")
    mode.add_argument("--done", default=None, metavar="TEXT",
                      help="A unit completed. Requires --evidence that resolves now.")
    cp.add_argument("--evidence", action="append", default=None, metavar="REF",
                    help="commit:<sha> | file:<path> | predicate:<fb>/<item> | issue:<n>. "
                         "Repeatable; every ref must resolve or the line is refused.")
    cp.add_argument("--advisor", default=None,
                    help="Defaults to ADVISOR_NAME in the environment.")
    cp.set_defaults(func=_checkpoint)

    eg = vsub.add_parser("emission-gate", help="Check mandatory emission file for /conclave:done.")
    eg.set_defaults(func=_emission_gate)

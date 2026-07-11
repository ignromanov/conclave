"""engine/cmd/overlay.py — adapter for `engine overlay <verb>`."""
from __future__ import annotations

import sys

_USAGE = (
    "usage: engine overlay apply"
    " --advisor <id> --contract <name>"
    " --type {constraint|extension|replacement}"
    " --action {add|modify|remove}"
)

_VALID_ACTIONS = {"add", "modify", "remove"}


def _apply(args) -> int:
    from enginelib import paths
    from enginelib.overlay import apply_overlay

    args._runlog_verb = "overlay-apply"
    args._runlog_args = (
        f"advisor={args.advisor or ''},"
        f"contract={args.contract or ''},"
        f"action={args.action or ''}"
    )

    # Validate required args and action value.
    if not args.advisor or not args.contract or not args.action:
        print(_USAGE, file=sys.stderr)
        return 1
    if args.action not in _VALID_ACTIONS:
        print(_USAGE, file=sys.stderr)
        return 1

    result = apply_overlay(
        advisor=args.advisor,
        contract=args.contract,
        type_=args.type or "",
        action=args.action,
        contracts_dir=paths.contracts_dir(),
        repo_root=paths.repo_root(),
    )

    status = result.status
    overlay = result.overlay_path

    if status == "base-missing":
        print(f"base contract missing: {result.base_path}", file=sys.stderr)
        return 2
    if status == "created":
        print(f"created: {overlay}")
        return 0
    if status == "exists":
        print(f"overlay already exists: {overlay}", file=sys.stderr)
        return 3
    if status == "removed":
        print(f"removed: {overlay}")
        return 0
    if status == "no-remove":
        print(f"no overlay to remove: {overlay}", file=sys.stderr)
        return 0
    if status == "modify":
        print(f"modify in editor: {overlay}")
        return 0
    if status == "no-modify":
        print(f"no overlay to modify: {overlay}", file=sys.stderr)
        return 3

    # Unreachable — enginelib.overlay raises on unknown action.
    print(f"engine overlay: unexpected status {status!r}", file=sys.stderr)
    return 1


def register(sub) -> None:
    p = sub.add_parser("overlay", help="Manage per-advisor contract overlays.")
    vsub = p.add_subparsers(dest="overlay_verb", required=True)

    v = vsub.add_parser("apply", help="Add, modify, or remove a per-advisor contract overlay.")
    v.add_argument("--advisor", default=None, help="Advisor id (e.g. kai-cto).")
    v.add_argument("--contract", default=None, help="Contract name (basename without .md).")
    v.add_argument(
        "--type",
        default=None,
        dest="type",
        help="Overlay type: constraint|extension|replacement.",
    )
    v.add_argument(
        "--action",
        default=None,
        help="Action: add|modify|remove.",
    )
    v.set_defaults(func=_apply)

"""engine/cmd/doctor.py — adapter for `engine doctor` (#49c).

First-Launch preflight: verifies data-root, hot.md well-formedness, and (optional)
advisor canonicality before an advisor starts filing. `--fix` seeds a missing
hot.md skeleton. Exit 0 when all checks pass, 1 otherwise.
"""
from __future__ import annotations

import sys


def _doctor(args) -> int:
    from enginelib import doctor, paths

    args._runlog_verb = "doctor"
    args._runlog_args = f"advisor={args.advisor or ''},fix={args.fix}"

    try:
        root = paths.repo_root()
    except RuntimeError as exc:
        print(f"doctor: {exc}", file=sys.stderr)
        return 1

    checks = doctor.run_checks(root, advisor=args.advisor, fix=args.fix)
    for c in checks:
        mark = "ok  " if c.ok else "FAIL"
        print(f"[{mark}] {c.name}: {c.detail}")
    code = doctor.exit_code(checks)
    if code != 0:
        print("doctor: preflight found issues (see FAIL rows above)", file=sys.stderr)
    return code


def register(sub) -> None:
    p = sub.add_parser("doctor", help="First-Launch preflight: data-root, hot.md, advisor canonicality.")
    p.add_argument("--advisor", default=None, help="Advisor slug to verify against the registry.")
    p.add_argument("--fix", action="store_true", help="Seed a missing hot.md skeleton.")
    p.set_defaults(func=_doctor)

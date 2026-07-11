"""engine/cmd/spec.py — adapter for `engine spec <verb>`."""
from __future__ import annotations

import sys


def _normalize(args) -> int:
    from enginelib import paths
    from enginelib.spec import normalize_specs

    args._runlog_verb = "spec-normalize-frontmatter"
    args._runlog_args = f"apply={args.apply}"

    specs_dir = paths.repo_root() / "ops" / "specs"
    spec_files = list(specs_dir.glob("*/spec.md")) if specs_dir.is_dir() else []
    if not spec_files:
        print(
            f"normalize-spec-frontmatter: no spec.md files found under {specs_dir}",
            file=sys.stderr,
        )
        return 1

    result = normalize_specs(specs_dir, args.apply)

    for line in result.inline_lines:
        print(line)

    if result.report_lines:
        print("\n--- Reports (no action taken) ---")
        for line in result.report_lines:
            print(line)

    print("\n--- Summary ---")
    if args.apply:
        print(f"Files changed: {result.files_changed}")
    else:
        print("Dry-run mode. Run with --apply to commit changes.")
    print(f"Files reported (need manual review): {result.files_reported}")

    return 0


def register(sub) -> None:
    p = sub.add_parser("spec", help="Spec frontmatter normalization and related operations.")
    vsub = p.add_subparsers(dest="spec_verb", required=True)

    nf = vsub.add_parser(
        "normalize-frontmatter",
        help="Normalize status: and inject id:/advisor: aliases in ops/specs/*/spec.md.",
    )
    nf.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Write changes to disk (default: dry-run).",
    )
    nf.set_defaults(func=_normalize)

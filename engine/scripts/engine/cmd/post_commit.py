"""engine/cmd/post_commit.py — adapter for `engine post-commit`.

Owns argparse + sys.exit contract (Q5). Delegates core logic to enginelib.post_commit.
"""
from __future__ import annotations

import argparse


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser(
        "post-commit",
        help="Run git post-commit tasks: briefing regen + feedback index rebuild.",
    )
    p.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    from enginelib.post_commit import post_commit
    return post_commit()

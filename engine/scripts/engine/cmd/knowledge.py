"""engine/cmd/knowledge.py — adapter for `engine knowledge <verb>` (spec 110 rotation slice).

  autoload           — the project files loaded at every session start, with sizes
  rotation-worklist  — which blocks of one such file are closed; moves nothing
"""
from __future__ import annotations

import json
import subprocess
import sys


def _num(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _ceilings() -> tuple[dict[str, int], list[str]]:
    from enginelib import roster
    from enginelib.knowledge import autoload
    return autoload.parse_ceilings(roster.roster_get_mapping("knowledge.autoload_ceilings"))


def _cmd_autoload(args) -> int:
    from enginelib import paths
    from enginelib.knowledge import autoload

    args._runlog_verb = "knowledge-autoload"
    root = paths.project_root()
    loaded = autoload.autoload_set(root)
    for f in loaded:
        print(f"{_num(f.size):>9}  {f.via:<40}  {f.rel}")
    print(f"{_num(sum(f.size for f in loaded)):>9}  total ({len(loaded)} files)")
    ceilings, errors = _ceilings()
    for e in errors:
        print(f"knowledge autoload: {e}", file=sys.stderr)
    breaches = autoload.check_ceilings(loaded, root, ceilings)
    for b in breaches:
        state = "not loaded" if b.size is None else f"{_num(b.size)} B"
        print(f"over/absent: {b.rel} — {state} against {_num(b.ceiling)} B", file=sys.stderr)
    return 1 if args.check and (breaches or errors) else 0


def _gh_states() -> tuple[dict[int, str] | None, str]:
    """Issue and PR states across the instance's repo scope; None when any read fails."""
    from enginelib import roster
    from enginelib.lifecycle import gh_fetch

    repos = gh_fetch.resolve_repos(roster.roster_get("github.owner").strip())
    if not repos:
        return None, "github: no repo scope — refs render as unknown"
    merged: dict[int, str | None] = {}
    for repo in repos:
        for kind in ("pr", "issue"):
            try:
                r = subprocess.run(
                    ["gh", kind, "list", "-R", repo, "--state", "all", "--limit", "1000",
                     "--json", "number,state"], capture_output=True, text=True)
                rows = json.loads(r.stdout or "[]") if r.returncode == 0 else None
            except (OSError, ValueError) as exc:
                return None, f"github: unreadable ({repo} {kind} list: {exc}) — refs render as unknown"
            if rows is None:
                return None, (f"github: unreadable ({repo} {kind} list exited {r.returncode})"
                              f" — refs render as unknown")
            for row in rows:
                n, s = int(row["number"]), str(row["state"])
                # A number whose state differs across repos is ambiguous: neither reading wins.
                merged[n] = s if merged.get(n, s) == s else None
    states = {n: s for n, s in merged.items() if s is not None}
    return states, f"github: {', '.join(repos)} · {len(states)} refs readable"


def _cmd_worklist(args) -> int:
    from enginelib import paths
    from enginelib.knowledge import autoload, rotation

    args._runlog_verb = "knowledge-rotation-worklist"
    root = paths.project_root()
    target = (root / args.path).resolve()
    if target not in {f.path for f in autoload.autoload_set(root)}:
        print(f"rotation-worklist: {args.path} is not auto-loaded — nothing to rotate",
              file=sys.stderr)
        return 2
    text = target.read_text(encoding="utf-8", errors="replace")
    states, gh_line = (None, "github: skipped (--offline)") if args.offline else _gh_states()
    ceilings, _ = _ceilings()
    size = len(text.encode())
    head = f"rotation worklist — {args.path} · {_num(size)} B"
    if args.path in ceilings:
        c = ceilings[args.path]
        delta = f"{_num(size - c)} B over" if size > c else f"{_num(c - size)} B under"
        head += f" · ceiling {_num(c)} B ({delta})"
    print(head)
    print(gh_line)
    print(f"{'verdict':<10} {'bytes':>7} {'line':>5}  heading — reason")
    for row in rotation.worklist(text, states):
        b = row.block
        print(f"{row.verdict:<10} {_num(b.size):>7} {b.line:>5}  {b.heading} — {row.reason}")
    print("Nothing was moved. The rotation follows the project's own rules.")
    return 0


def register(sub) -> None:
    p = sub.add_parser("knowledge", help="Auto-loaded project knowledge: size and rotation.")
    vsub = p.add_subparsers(dest="knowledge_verb", required=True)
    a = vsub.add_parser("autoload", help="List files loaded at every session start.")
    a.add_argument("--check", action="store_true",
                   help="Exit 1 when a declared ceiling is breached.")
    a.set_defaults(func=_cmd_autoload)
    w = vsub.add_parser("rotation-worklist", help="Which blocks of an auto-loaded file are closed.")
    w.add_argument("path", help="Path relative to the project root, e.g. .claude/progress.md")
    w.add_argument("--offline", action="store_true", help="Do not ask GitHub for ref states.")
    w.set_defaults(func=_cmd_worklist)

"""enginelib.lifecycle.runlog_summary — one-line Infra sidecar summary from run-log JSONL.

Contract: no stdout, no argparse, no sys.exit. File read is allowed.
Port of lifecycle/runlog-summary.sh (deliberate deviations: no jq dependency;
jq-unavailable branch dropped; "jq parse failed" → "parse failed").

run(advisor, date_str) -> str
    Returns a formatted summary line ready to print.
    The adapter (engine/cmd/lifecycle.py) prints the result and exits 0.
"""
from __future__ import annotations

import json
import re

from enginelib.paths import run_log_dir

# P0 script set — the run-log `script` field is "engine <noun> <verb>" (dispatcher format).
# The three P0 commands log verbs briefing-build / session-close / file-decision.
_P0_RE = re.compile(r"^engine \S+ (briefing-build|session-close|file-decision)$")


def run(advisor: str, date_str: str) -> str:
    """Return the one-line summary string for `advisor` on `date_str` (YYYY-MM-DD)."""
    log_file = run_log_dir() / f"{date_str}.jsonl"

    if not log_file.is_file():
        return "🟢 0 scripts · 0ms · 0 errors"

    rows: list[dict] = []
    try:
        for line in log_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    except json.JSONDecodeError:
        return f"🟡 parse failed for {log_file}"

    mine = [r for r in rows if r.get("advisor") == advisor]

    count = len(mine)
    total_ms = sum(int(r.get("duration_ms", 0)) for r in mine)
    # exit 2 = refresh = SUCCESS (ADR-0003 loop-discipline §2); excluded from error tally.
    errors = sum(1 for r in mine if r.get("exit_code") not in (0, 2))
    p0 = sum(
        1
        for r in mine
        if r.get("exit_code") not in (0, 2)
        and _P0_RE.match(str(r.get("script", "")))
    )

    if p0 > 0:
        sev = "🔴"
    elif errors > 0:
        sev = "🟡"
    else:
        sev = "🟢"

    return f"{sev} {count} scripts · {total_ms}ms · {errors} errors"

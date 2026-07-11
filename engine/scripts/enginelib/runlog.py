"""runlog.py — append-on-exit JSONL observability primitive. Port of lib/run-log.sh."""
import datetime
import json

from enginelib.paths import ensure_dir, run_log_dir


def run_log_append(
    script: str,
    args_hash: str,
    exit_code: int,
    duration_ms: int,
    advisor: str,
) -> None:
    """Append one JSONL row to run_log_dir()/<UTC-today>.jsonl.

    Mirrors bash: coerce exit_code/duration_ms to int (non-numeric → 0).
    Field order: ts, script, args_hash, exit_code, duration_ms, advisor.
    Format: compact JSON (no spaces after : or ,) + newline, append mode.
    """
    try:
        ec = int(exit_code)
    except (TypeError, ValueError):
        ec = 0
    try:
        dm = int(duration_ms)
    except (TypeError, ValueError):
        dm = 0

    now = datetime.datetime.now(datetime.UTC)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = now.strftime("%Y-%m-%d")

    log_dir = run_log_dir()
    ensure_dir(log_dir)

    log_file = log_dir / f"{today}.jsonl"

    row = {
        "ts": ts,
        "script": script,
        "args_hash": args_hash,
        "exit_code": ec,
        "duration_ms": dm,
        "advisor": advisor,
    }
    line = json.dumps(row, separators=(",", ":")) + "\n"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)

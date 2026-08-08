"""ledger.py — the session-end duty ledger (spec 091 §4).

One append per activated duty per session: `{duty_id, session_id, outcome, ts}`. This is the
only record that a duty was ever acted on, and therefore the only input the §5 health sweep
can compute `dead` / `erroneous` / `stale` from.

Two properties are load-bearing:

  - **Only ever extended.** New entries go on the end; nothing is rewritten or pruned. A
    rewrite would erase exactly the history the sweep reads.
  - **Honest outcomes.** `errored`, `skipped` and `condition-unmet` are recorded as readily
    as `discharged`. A ledger holding only successes would let a duty that fails every time
    read as healthy — the unhappy outcomes carry the diagnostic value.

An unparseable ledger raises rather than reading as empty: treating corruption as "no
entries" means the next append silently replaces the file and the history is gone.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import yaml

from enginelib.lock import with_lock

#: Spec §4's vocabulary, exactly. Pinned as a set so a sixth outcome is a deliberate edit
#: here rather than a silent widening at a call site.
OUTCOMES = {"discharged", "deferred", "skipped", "errored", "condition-unmet"}

LEDGER_NAME = "duty-ledger.yaml"


@dataclass(frozen=True)
class LedgerEntry:
    duty_id: str
    session_id: str
    outcome: str
    ts: str
    note: str | None = None


def ledger_path(agent_dir: Path) -> Path:
    return Path(agent_dir) / LEDGER_NAME


def read_entries(agent_dir: Path) -> list[LedgerEntry]:
    """Every entry, oldest first. An absent ledger is empty — an agent that has never closed
    a session simply has no history, which is not a fault."""
    path = ledger_path(agent_dir)
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        LedgerEntry(
            duty_id=str(row["duty_id"]),
            session_id=str(row["session_id"]),
            outcome=str(row["outcome"]),
            ts=str(row["ts"]),
            note=row.get("note"),
        )
        for row in (data.get("entries") or [])
    ]


def append_entry(
    agent_dir: Path,
    *,
    duty_id: str,
    session_id: str,
    outcome: str,
    note: str | None = None,
    ts: str | None = None,
) -> LedgerEntry:
    """Append one entry and return it. Creates the ledger on first use."""
    if outcome not in OUTCOMES:
        raise ValueError(
            f"unknown outcome {outcome!r} — expected one of {sorted(OUTCOMES)}")

    entry = LedgerEntry(
        duty_id=duty_id,
        session_id=session_id,
        outcome=outcome,
        ts=ts or datetime.now(UTC).isoformat(timespec="seconds"),
        note=note,
    )

    agent_dir = Path(agent_dir)
    agent_dir.mkdir(parents=True, exist_ok=True)

    # Read-modify-write under an exclusive lock. Without it two sessions closing at once
    # both read the same history and the second write drops the first one's entry — the
    # same hazard memory/hot.py takes this lock for, and parallel sessions are ordinary
    # here, not hypothetical.
    #
    # The lock lives under LOCK_DIR, not beside the ledger: memory/hot.py's convention, and
    # the ledger sits in the tracked DATA tree where a stray .lock would be committed. Keyed
    # by the ledger's full path so two agents' ledgers never share one lock.
    lock_key = str(ledger_path(agent_dir).resolve()).replace(os.sep, "_").lstrip("_")
    lock_file = Path(os.environ.get("LOCK_DIR", "/tmp/conclave-locks")) / f"{lock_key}.lock"
    with with_lock(lock_file):
        existing = read_entries(agent_dir)      # raises on corruption, before any write
        rows = [
            {k: v for k, v in
             (("duty_id", e.duty_id), ("session_id", e.session_id), ("outcome", e.outcome),
              ("ts", e.ts), ("note", e.note))
             if v is not None}
            for e in [*existing, entry]
        ]
        ledger_path(agent_dir).write_text(
            yaml.safe_dump({"entries": rows}, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    return entry

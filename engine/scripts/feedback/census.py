"""census.py — how many feedback items exist, and how many of them closed (GH#294).

The notebook keeps its items in two registers, and neither one is the population:

- `_index/index.jsonl` is the **working set**. `feedback_archive` stamps every terminal
  item with `archived_at` and `feedback_index` skips stamped items; a review whose items
  are *all* done loses its markdown to `md_file.unlink()` entirely. So a `resolved` row
  cannot survive here, and `resolved / len(index)` is a ratio whose numerator is the
  complement of its denominator — zero in every reachable world, which is what
  `engine status` printed for as long as the row existed.
- `_archive/*.jsonl` is the **closed register**, and it is the only record of an item
  whose review was unlinked.

The intake is their union. Measured on this instance 2026-09-15: 304 live + 157 closed +
11 unrecoverable = 472 items, 131 resolved — 27.8%, against the 0% on the surface.

Three row shapes live in the ledger, all three reachable, all three counted here:

1. `{"kind": "item", ..., "item": {...}}` — one closed item (149 rows here).
2. a whole review with `items: [...]` — written when every item closed at once (5 rows,
   21 items, 13 of which the per-item path had already written).
3. a whole review with neither `items` nor `body`, carrying only `item_count` (6 rows,
   11 items) — the husks from the 2026-08-18 data-loss event. `feedback_archive` cannot
   make new ones: `_archive_row_is_reconstructable` refuses to unlink first. Their items
   were terminal (the path's precondition is `_all_done`) but WHICH terminal is lost, so
   they are intake and not `resolved` — the same treatment `rejected` already gets.
   Dropping them instead would shrink the denominator silently, which is this bug.

Dedup is not defensive: `feedback_index._merge_rows` keeps an existing row whose item the
current pass skipped, so between an archive run and the next `--rebuild` one item sits in
the index as `open` and in the ledger as `resolved`. The ledger wins — it is the register
that records terminality.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# Rule 5 (state-report.md): a count is one hop from its source, and this one sums two
# files, so naming either alone would misdescribe the number.
PROOF = "ops/feedback/_index/index.jsonl ∪ ops/feedback/_archive/*.jsonl"


@dataclass(frozen=True)
class Intake:
    """Every feedback item on record, split by which register holds it."""

    live: int
    closed: int
    unrecoverable: int
    resolved: int

    @property
    def total(self) -> int:
        return self.live + self.closed + self.unrecoverable

    def __post_init__(self) -> None:
        if self.resolved > self.live + self.closed:
            raise ValueError(
                f"resolved {self.resolved} exceeds the items whose status is known "
                f"({self.live + self.closed}) — unrecoverable items cannot be resolved"
            )


def read_closed_items(archive_dir: Path) -> tuple[dict[tuple[str, str], dict], int]:
    """Return ({(feedback_id, item_id): item}, count of items whose record is lost).

    The one reader of the ledger's three row shapes. It hands back the item bodies, not a
    derived field, because its two callers need different things from them: `read_intake`
    below reads only `status`, while `feedback_emit._reopen_matches` recomputes each
    item's fingerprint from `location` + `category` (GH#297). A reader that returned
    statuses alone would force the second caller to re-parse the shapes itself, which is
    how the shapes came to be parsed in three places to begin with.
    """
    closed: dict[tuple[str, str], dict] = {}
    unrecoverable = 0
    if not archive_dir.is_dir():
        return closed, unrecoverable

    for shard in sorted(archive_dir.glob("*.jsonl")):
        for line in shard.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # An unreadable row is an item that existed and whose fate is now
                # unknown. Skipping it would understate the intake in silence.
                unrecoverable += 1
                continue

            feedback_id = str(row.get("feedback_id", ""))
            item = row.get("item")
            if isinstance(item, dict):
                # Shape 1 wins over shape 2 on the 13 keys both carry: it is written by
                # the per-item path at the moment that item closed.
                closed[(feedback_id, str(item.get("id", "")))] = item
                continue

            items = row.get("items")
            if isinstance(items, list) and items:
                for entry in items:
                    if isinstance(entry, dict):
                        closed.setdefault((feedback_id, str(entry.get("id", ""))), entry)
                continue

            unrecoverable += int(row.get("item_count") or 0)

    return closed, unrecoverable


def read_intake(feedback_root: Path) -> Intake:
    """Census over `ops/feedback/`. The caller has already established the index exists."""
    closed, unrecoverable = read_closed_items(feedback_root / "_archive")

    live = 0
    live_resolved = 0
    index = feedback_root / "_index" / "index.jsonl"
    if index.is_file():
        for line in index.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                # Malformed rows count toward the intake and nothing else — the
                # denominator must not shrink because a line went bad.
                live += 1
                continue
            if (str(row.get("feedback_id", "")), str(row.get("item_id", ""))) in closed:
                continue  # the ledger already holds this item's terminal state
            live += 1
            if row.get("status") == "resolved":
                live_resolved += 1

    return Intake(
        live=live,
        closed=len(closed),
        unrecoverable=unrecoverable,
        resolved=live_resolved + sum(1 for it in closed.values() if it.get("status") == "resolved"),
    )

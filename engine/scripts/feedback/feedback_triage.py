"""feedback_triage.py — dedup, digest, status write-back for spec 086.

CLI: python feedback_triage.py [--digest] [--check] [--monthly]
                                [--set <feedback_id> <item_id> <status> [--owner <a>]]

First step always: run feedback_index.py rebuild (defensive — resolves B2).

--digest   Dedup index rows on fingerprint (duplicates → hit_count); print the
           3-column digest (what · why · urgency); critical-severity rows sorted top.
           --status <s> scopes the digest to one status (e.g. open); --json emits a
           machine-readable array carrying feedback_id/item_id per row for direct --set.
--check    Compare last-triage marker mtime + new-review count → print
           triage_due=<true|false>.
--set      Write status/owner/resolved_at back into the review markdown file via
           frontmatter_io.read_commented + write (comment-preserving); bump updated_at.
           Touch the last-triage marker when a triage session completes.
--monthly  List items with status in {open, deferred} older than 90 days.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from briefing.frontmatter_io import read as fm_read  # noqa: E402
from briefing.frontmatter_io import read_commented  # noqa: E402
from briefing.paths import repo_root  # noqa: E402
from enginelib import snapshot  # noqa: E402
from feedback.feedback_emit import write_preserving_header  # noqa: E402
from feedback.paths import index_path, last_triage_marker  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
import typing as _typing  # noqa: E402

from feedback.schema import Status as _Status  # noqa: E402

# Derived from the single source of truth so a new status (e.g. re-occurred) can never
# be silently rejected by triage write-back (#89). Add a status to schema.Status only.
_VALID_STATUSES = set(_typing.get_args(_Status))


def _rebuild_index(root: Path) -> int:
    """Defensively rebuild index via feedback_index.main().

    Returns the exit code from feedback_index.main().
    Non-zero means one or more _draft:false reviews are schema-invalid.
    Callers must abort triage when this returns non-zero.
    """
    from feedback import feedback_index  # noqa: PLC0415
    # --rebuild: triage must see a clean index — stale rows from archived/deleted
    # reviews would otherwise resurface as phantom clusters in the digest (#9).
    return feedback_index.main(["--rebuild"])


def _load_index(idx_path: Path) -> list[dict]:
    if not idx_path.exists():
        return []
    rows = []
    for line in idx_path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows


def _find_review_file(root: Path, feedback_id: str) -> Path | None:
    """Walk dated dirs + _migrated to find the .md file for a given feedback_id."""
    fb_root = root / "ops" / "feedback"
    if not fb_root.exists():
        return None
    for d in fb_root.iterdir():
        if not d.is_dir():
            continue
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name) or d.name == "_migrated":
            for md in d.glob("*.md"):
                try:
                    meta, _ = fm_read(md)
                    if meta.get("feedback_id") == feedback_id:
                        return md
                except Exception:
                    pass
    return None


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_digest(rows: list[dict], as_json: bool = False) -> None:
    """Dedup rows on fingerprint, print 3-column digest sorted critical-first.

    as_json=True emits a machine-readable JSON array on stdout instead: each row
    carries the representative feedback_id/item_id plus a `members` list of every
    (feedback_id, item_id) in the cluster, so triage classification maps straight
    to --set without an out-of-band index query (#10)."""
    clusters: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        fp = row.get("fingerprint") or "no-fp"
        clusters[fp].append(row)

    # Build digest entries
    entries = []
    for fp, group in clusters.items():
        rep = group[0]
        hit_count = len(group)
        entries.append({
            "fingerprint": fp,
            "feedback_id": rep.get("feedback_id", ""),
            "item_id": rep.get("item_id", ""),
            "hit_count": hit_count,
            "severity": rep.get("severity", "low"),
            "observation": rep.get("observation", ""),
            "category": rep.get("category", ""),
            "layer": rep.get("layer", ""),
            "location": rep.get("location", {}),
            "suggested_fix": rep.get("suggested_fix", ""),
            "frequency": rep.get("frequency", ""),
            "status": rep.get("status", "open"),
            "members": [
                {"feedback_id": r.get("feedback_id", ""), "item_id": r.get("item_id", "")}
                for r in group
            ],
        })

    # Sort: critical first, then by hit_count desc
    entries.sort(key=lambda e: (
        _SEVERITY_ORDER.get(e["severity"], 99),
        -e["hit_count"],
    ))

    if as_json:
        print(json.dumps(entries, indent=2))
        return

    # Print 3-column digest
    print(f"{'WHAT (observation · location)':<45} {'WHY (category · layer)':<30} {'URGENCY (severity · freq · hits)'}")
    print("-" * 110)
    for e in entries:
        loc = e["location"]
        loc_str = loc.get("file") or loc.get("skill") or loc.get("section") or ""
        what = f"{e['observation'][:30]} @ {loc_str}"
        why = f"{e['category']} / {e['layer']}"
        urgency = f"{e['severity']} · {e['frequency']} · hit_count={e['hit_count']}"
        print(f"{what:<45} {why:<30} {urgency}")


def cmd_check(rows: list[dict], triage_marker: Path) -> None:
    """Print triage_due=<true|false> based on marker mtime + new-review count."""
    open_count = sum(1 for r in rows if r.get("status") == "open")

    if not triage_marker.exists():
        triage_due = True
    else:
        marker_mtime = triage_marker.stat().st_mtime
        now = datetime.now(UTC).timestamp()
        # 7 days cadence
        days_since = (now - marker_mtime) / 86400
        triage_due = days_since > 7 or open_count > 0

    print(f"triage_due={'true' if triage_due else 'false'}")
    print(f"open_items={open_count}")


def cmd_monthly(rows: list[dict]) -> None:
    """List items with status open/deferred older than 90 days."""
    now = datetime.now(UTC)
    cutoff_days = 90
    found = []
    for row in rows:
        status = row.get("status", "open")
        if status not in ("open", "deferred"):
            continue
        updated_str = row.get("updated_at", "")
        try:
            updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
            age_days = (now - updated).days
        except (ValueError, AttributeError):
            age_days = 0
        if age_days >= cutoff_days:
            found.append((age_days, row))

    if not found:
        print("No zombie items found (open/deferred > 90 days).")
        return

    found.sort(key=lambda x: -x[0])
    print(f"{'feedback_id':<25} {'item_id':<15} {'age_days':<10} {'status':<12} observation")
    print("-" * 90)
    for age, row in found:
        print(f"{row.get('feedback_id', ''):<25} {row.get('item_id', ''):<15} "
              f"{age:<10} {row.get('status', ''):<12} {row.get('observation', '')[:40]}")


def cmd_set(root: Path, feedback_id: str, item_id: str, status: str,
            owner: str | None, triage_marker: Path) -> int:
    """Write status/owner/resolved_at back to the review file."""
    if status not in _VALID_STATUSES:
        print(f"ERROR: invalid status={status!r} (allowed: {sorted(_VALID_STATUSES)})",
              file=sys.stderr)
        return 1
    review_path = _find_review_file(root, feedback_id)
    if review_path is None:
        print(f"ERROR: review not found for feedback_id={feedback_id}", file=sys.stderr)
        return 1

    # NOTE: the DATA-root advisory lock is held by main() across the whole triage
    # mutation (index rebuild + this write-back), so cmd_set does not re-acquire it
    # here — mkdir-poll locks are not reentrant (#51).
    meta, body = read_commented(review_path)

    now_str = datetime.now(UTC).isoformat()

    # Find and update the item
    items = meta.get("items", [])
    found = False
    for item in items:
        if item.get("id") == item_id:
            item["status"] = status
            if owner is not None:
                item["owner"] = owner
            if status in ("resolved", "rejected"):
                item["resolved_at"] = now_str
            if status == "accepted":
                item["accepted_at"] = now_str
            found = True
            break

    if not found:
        print(f"ERROR: item_id={item_id} not found in feedback_id={feedback_id}", file=sys.stderr)
        return 1

    meta["updated_at"] = now_str
    write_preserving_header(review_path, meta, body)

    # Touch the last-triage marker
    triage_marker.parent.mkdir(parents=True, exist_ok=True)
    triage_marker.touch()

    print(f"Updated {feedback_id}/{item_id}: status={status}" +
          (f" owner={owner}" if owner else ""))
    return 0


def cmd_set_verify(root: Path, feedback_id: str, item_id: str,
                   predicate: dict, triage_marker: Path) -> int:
    """Attach a verify: predicate to an existing item (093 P1 T3).

    Sanctioned write path so feeding an accepted backlog never needs hand-editing
    finalized frontmatter. Caller must hold the .triage-lock (the mkdir-poll lock is
    not reentrant, so cmd_set_verify — like cmd_set — never re-acquires it here).
    """
    from feedback.schema import Predicate
    try:
        Predicate(**predicate)  # validate shape before writing
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: invalid predicate: {exc}", file=sys.stderr)
        return 1
    review_path = _find_review_file(root, feedback_id)
    if review_path is None:
        print(f"ERROR: review not found for feedback_id={feedback_id}", file=sys.stderr)
        return 1
    meta, body = read_commented(review_path)
    found = False
    for item in meta.get("items", []):
        if item.get("id") == item_id:
            item["verify"] = predicate
            found = True
            break
    if not found:
        print(f"ERROR: item_id={item_id} not found in feedback_id={feedback_id}",
              file=sys.stderr)
        return 1
    meta["updated_at"] = datetime.now(UTC).isoformat()
    write_preserving_header(review_path, meta, body)
    triage_marker.parent.mkdir(parents=True, exist_ok=True)
    triage_marker.touch()
    print(f"Attached verify to {feedback_id}/{item_id}: kind={predicate.get('kind')}")
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Feedback triage: dedup, digest, write-back")
    parser.add_argument("--digest", action="store_true", help="Print dedup digest")
    parser.add_argument("--status", default=None,
                        help="Filter --digest to rows with this status (e.g. open)")
    parser.add_argument("--json", action="store_true",
                        help="Emit --digest as machine-readable JSON (feedback_id/item_id per row)")
    parser.add_argument("--check", action="store_true", help="Check if triage is due")
    parser.add_argument("--monthly", action="store_true", help="List zombie items > 90 days")
    parser.add_argument("--set", nargs=3, metavar=("FEEDBACK_ID", "ITEM_ID", "STATUS"),
                        help="Write status back to review file")
    parser.add_argument("--owner", default=None, help="Owner to assign with --set")
    args = parser.parse_args(argv)

    root = repo_root()

    # Serialize the whole triage mutation — index rebuild + any write-back — on a
    # DATA-root advisory lock, so two concurrent triage sessions on the same root
    # can't corrupt index.jsonl or clobber each other's review write-back (#51).
    lock_dir = root / ".triage-lock"
    lock_timeout = int(os.environ.get("CONCLAVE_TRIAGE_LOCK_TIMEOUT", "5"))
    if not snapshot.acquire_lock(lock_dir, lock_timeout):
        print(f"ERROR: could not acquire triage lock at {lock_dir} "
              f"(concurrent triage session?)", file=sys.stderr)
        return 1
    try:
        # Step 1: Always rebuild index defensively.
        # Non-zero exit means _draft:false reviews are schema-invalid — abort triage
        # so corrupted reviews never silently bypass the queue.
        index_rc = _rebuild_index(root)
        if index_rc != 0:
            print(
                "ERROR: triage aborted — one or more author-complete (_draft:false) reviews "
                "failed schema validation. Fix the DROPPED files shown above, then re-run.",
                file=sys.stderr,
            )
            return index_rc

        idx_path = index_path()
        rows = _load_index(idx_path)
        triage_marker = last_triage_marker()

        if args.set:
            feedback_id, item_id, status = args.set
            return cmd_set(root, feedback_id, item_id, status, args.owner, triage_marker)

        if args.digest:
            digest_rows = rows
            if args.status:
                digest_rows = [r for r in rows if r.get("status") == args.status]
            cmd_digest(digest_rows, as_json=args.json)

        if args.check:
            cmd_check(rows, triage_marker)

        if args.monthly:
            cmd_monthly(rows)

        if not any([args.digest, args.check, args.monthly, args.set]):
            parser.print_help()

        return 0
    finally:
        snapshot.release_lock(lock_dir)


if __name__ == "__main__":
    sys.exit(main())

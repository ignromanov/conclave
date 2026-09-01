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
--set      Write status/owner/issue/waiver/resolved_at back into the review file via
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

# Interpreter floor, enforced before the first thing that can fail below it — here,
# `from datetime import UTC` below (UTC was added in 3.11), which is the very measurement the
# floor comes from. /conclave:triage launches this file directly.
# Measured, not declared; see engine/__main__.py for the full note.
if sys.version_info < (3, 11):  # noqa: UP036 — see engine/__main__.py
    sys.stderr.write(
        f"Conclave requires Python 3.11 or newer.\n"
        f"This is Python {sys.version.split()[0]} at {sys.executable}.\n"
        f"Install a newer interpreter (e.g. `uv python install 3.13`) and re-run.\n"
    )
    sys.exit(1)

from datetime import UTC, datetime  # noqa: E402 — must follow the floor guard above
from pathlib import Path  # noqa: E402

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
# #163 — a number parked in a name field. Before the issue: field existed, an item's GH
# binding was written as `owner: forge:#102`; 53 accepted items held their link ONLY there
# and none carried an `issue:`. `owner` is overwritten unconditionally and
# `feedback_verify --apply` always supplies owner="verify:auto", so each of them was one
# auto-close away from losing the binding with no trace and no warning. It happened once,
# to fb-1783808596-f85349/i1, and the link survives only in git. An item with no issue link
# is a defect the next session re-observes and triage re-accepts as new — the index dedups
# on fingerprint and knows nothing about GitHub — so 53 lost bindings would have
# manufactured 53 future duplicates. Matches forge:#102, forge:102 and forge:AI#12.
LEGACY_OWNER_ISSUE_RE = re.compile(r"^[^:]+:(AI)?#?\d+$")

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
            owner: str | None, triage_marker: Path, issue: int | None = None,
            waiver: str | None = None) -> int:
    """Write status/owner/issue/waiver/resolved_at back to the review file."""
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
            previous = item.get("status")
            if waiver is not None:
                item["verify_waiver"] = waiver
            # 093/#165 — accepting an item is the one moment the protocol has the
            # operator's attention on its closing condition, and the cheapest moment to
            # state it. An accepted item carrying neither a predicate nor a recorded
            # waiver can never be closed by the verify sweep: it is backlog nobody can
            # drain. When this gate was written 2 of 171 accepted items carried a
            # predicate and the loop had closed nothing in seven weeks.
            # The gate fires only on a GENUINE transition (status != previous), so the
            # documented issue-binding step of triage.md Step 4 — which re-passes an
            # already-accepted item's own status — still works, and so does every later
            # correction to the items that predate the rule. Enforcing on every write
            # would push operators into hand-editing finalized frontmatter, a second
            # writer, which is worse than the gap it closes.
            if (status == "accepted" and status != previous
                    and not item.get("verify") and not item.get("verify_waiver")):
                print(
                    f"ERROR: refusing to accept {feedback_id}/{item_id}: it carries no "
                    f"verify: predicate and no verify_waiver.\n"
                    f"       Accepting it now would add one more item the verify sweep "
                    f"can never close.\n"
                    f"       Attach a predicate first:\n"
                    f"         python feedback_verify.py --set-verify {feedback_id} "
                    f"{item_id} <grep-absent|file-contains|file-absent> "
                    f"--file <path> --pattern <regex>\n"
                    f"       Or record why no mechanical predicate is possible, on this "
                    f"same call:\n"
                    f"         --waiver \"<reason>\"",
                    file=sys.stderr)
                return 1
            # Guard before the write, not after: the audited path is where both the
            # manual and the auto-close routes pass, so it is the only place that sees
            # every overwrite.
            prev_owner = item.get("owner")
            if (owner is not None and prev_owner and issue is None
                    and not item.get("issue")
                    and LEGACY_OWNER_ISSUE_RE.match(str(prev_owner))):
                print(
                    f"ERROR: refusing to overwrite owner on {feedback_id}/{item_id}: "
                    f"{prev_owner!r} is this item's only issue link, and the item "
                    f"carries no issue: field.\n"
                    f"       Overwriting it would drop the binding with no trace, and "
                    f"the next triage would re-accept the defect as new.\n"
                    f"       Carry the number across on this same call:\n"
                    f"         --set {feedback_id} {item_id} {status} "
                    f"--owner <name> --issue <n>",
                    file=sys.stderr)
                return 1
            item["status"] = status
            if owner is not None:
                item["owner"] = owner
            if issue is not None:
                item["issue"] = issue
            # A lifecycle timestamp records a TRANSITION, not the act of writing the field.
            # triage.md Step 4 binds an issue by re-passing the item's current status
            # (`--set <id> <item> accepted --owner ... --issue N`), so stamping on every
            # write made the documented binding step reset the acceptance date it walked
            # past: 53 of 53 items lost up to 58 days of age in one migration, on the field
            # cmd_monthly reads to find items older than 90 days (#164). The `or not ...`
            # clause keeps a missing timestamp backfillable without overwriting a present one.
            if status in ("resolved", "rejected") and (
                    status != previous or not item.get("resolved_at")):
                item["resolved_at"] = now_str
            if status == "accepted" and (
                    status != previous or not item.get("accepted_at")):
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
          (f" owner={owner}" if owner else "") +
          (f" issue=#{issue}" if issue else "") +
          (" waiver=recorded" if waiver else ""))
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
    parser.add_argument("--waiver", default=None,
                        help="Record why this item can carry no mechanical verify: "
                             "predicate. Satisfies the accept-gate; an unmeasurable "
                             "waiver is indistinguishable from having forgotten (#165).")
    parser.add_argument("--issue", type=int, default=None,
                        help="GH issue number to bind to the item with --set (Step 4). "
                             "Binding the item to its issue is what stops a defect that "
                             "already has an open issue from re-entering the queue as new.")
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
            set_rc = cmd_set(root, feedback_id, item_id, status, args.owner, triage_marker,
                             issue=args.issue, waiver=args.waiver)
            if set_rc == 0:
                # Reconcile the cache with the review we just wrote. The rebuild above runs
                # BEFORE the write, so without this the index lags the source of truth by
                # exactly one --set: the last item classified in a session stays invisible
                # to the digest, --check and the dashboard until something else rebuilds.
                # feedback_verify already does this after its own writes; cmd_set did not.
                _rebuild_index(root)
            return set_rc

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

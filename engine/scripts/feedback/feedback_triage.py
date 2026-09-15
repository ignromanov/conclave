"""feedback_triage.py — dedup, digest, status write-back for spec 086.

CLI: python feedback_triage.py [--digest] [--check] [--monthly]
                                [--set <feedback_id> <item_id> <status> [--owner <a>]]

First step always: read every review. A path that writes (--set, --complete-triage)
rebuilds the index from what it read; a path that only reports (--check, --digest,
--monthly) writes nothing at all (#102, resolves B2).

--digest   Dedup index rows on fingerprint (duplicates → hit_count); print the
           3-column digest (what · why · urgency); critical-severity rows sorted top.
           --status <s> scopes the digest to one status (e.g. open); --json emits a
           machine-readable array carrying feedback_id/item_id per row for direct --set.
--check    Compare the last-triage marker's recorded timestamp + new-review count → print
           triage_due=<true|false>.
--set      Write status/owner/issue/waiver/resolved_at back into the review file via
           frontmatter_io.read_commented + write (comment-preserving); bump updated_at.
           Does NOT move the cadence clock — see --complete-triage.
--complete-triage
           Record that a triage session finished (writes the timestamp into the
           last-triage marker). The only write that resets the cadence clock.
--monthly  List items with status in {open, deferred} older than 90 days.
"""
from __future__ import annotations

import argparse
import contextlib
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
from pathlib import Path
from typing import NamedTuple  # noqa: E402

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from briefing.frontmatter_io import read as fm_read  # noqa: E402
from briefing.frontmatter_io import read_commented  # noqa: E402
from briefing.paths import repo_root  # noqa: E402
from enginelib.advisors import META_ADVISORS, canonical_advisors  # noqa: E402
from enginelib.lock import LockTimeout, lock_path_for, with_lock  # noqa: E402
from enginelib.paths import project_root  # noqa: E402
from feedback.feedback_emit import write_preserving_header  # noqa: E402
from feedback.paths import (  # noqa: E402
    index_path,
    last_triage_marker,
    triage_lock_target,
)

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

# The status field has been validated against a closed vocabulary since it existed;
# `owner` was written through unchecked. Two different mistakes persisted for the same
# reason: `sage` was a short name hand-typed at triage that never was an advisor id, and
# `forge` was a real id until the 106 rename created `forge-chro` beside it. 71 live items
# name an owner that resolves to nobody, and every owner-scoped query -- the briefing's
# `owed` scan, triage routing -- silently omits them. Absence is the failure mode with no
# error message.
_RESERVED_OWNERS = frozenset({"verify:auto"})


def _unknown_owner(owner: str) -> bool:
    """True when *owner* names an advisor this instance's roster does not hold.

    The roster comes from `canonical_advisors()`, not `known_advisors()`: Forge's
    definition lives under skills/ rather than agents/, so the latter omits it, and
    forge-chro owns 35 live items. A guard on the wrong resolver would reject a fifth
    of the notebook.

    When the roster resolves to nothing beyond the shipped meta-advisor, the project
    anchor did not point at a real instance and membership is unjudgeable. The write
    then passes: an unreadable roster must degrade to the previous behaviour, never to
    an accusation that every real advisor does not exist (the shape of #170).
    """
    if owner in _RESERVED_OWNERS:
        return False
    roster = set(canonical_advisors())
    if not roster - set(META_ADVISORS):
        return False
    return owner not in roster

import typing as _typing  # noqa: E402

from feedback.schema import Status as _Status  # noqa: E402

# Derived from the single source of truth so a new status (e.g. re-occurred) can never
# be silently rejected by triage write-back (#89). Add a status to schema.Status only.
_VALID_STATUSES = set(_typing.get_args(_Status))

# Categories that report no defect and therefore carry no fix to schedule (#250).
_NON_DEFECT_CATEGORIES = frozenset({"positive", "near-miss"})


class IndexRebuild(NamedTuple):
    """What one index run did, for a caller that must decide whether to continue.

    Carried by the read-only scan as well as by the rebuild since #102. The three fields
    mean the same thing either way — a scan that could not read a file leaves a caller
    exactly as unable to report as a rebuild that could not write one.

    `fatal` is the decision, computed once here so the two callers cannot drift apart.
    It is NOT `rc != 0`: one author's schema-invalid review is survivable by the
    2026-09-15 ruling, and every other non-zero is not.
    """

    rc: int
    skipped_reviews: list[str]
    fatal: bool


def _rebuild_index_reporting() -> IndexRebuild:
    """Rebuild the index and say whether the failure is one a caller may continue past.

    The exit code says only "something was wrong". The decision turns on which thing:
    a dropped author-complete review is one author's file failing validation, which the
    rest of the corpus survives; an unreadable file or a lock the run could not take is
    not, because then the index a caller is about to read was never produced.

    The predicate is subtractive and fails closed — an exit is survivable only if it
    reported reasons AND every one of them is in the survivable set. An unclassified
    non-zero reports no reasons and is therefore fatal. The first cut of this function
    asked the opposite question, "is there an explainable cause?", and so continued past
    a lock timeout whenever any unrelated review happened to be schema-invalid — which
    on the instance this was written for is the permanent state, since the offending
    review is deliberately left unrepaired.

    This deliberately replaced a plain `_rebuild_index(root) -> int` rather than widening
    that function's return type. Widening it left `feedback_verify.py:391`'s
    `if _rebuild_index(root) != 0:` comparing a tuple to an integer — always true, so
    --apply took its failure branch unconditionally and exited 1 with an empty stderr.
    Python will not catch that, and neither will any gate here; six sibling tests did.
    The int-returning wrapper outlived that repair and is now gone: a caller that reads
    only `.rc` cannot see the fatal/skipped distinction, and all three of its remaining
    call sites were discarding even the int.
    """
    from feedback import feedback_index  # noqa: PLC0415

    report: dict = {}
    # --rebuild: triage must see a clean index — stale rows from archived/deleted
    # reviews would otherwise resurface as phantom clusters in the digest (#9).
    rc = feedback_index.main(["--rebuild"], report=report)
    return _classify(rc, report)


def _classify(rc: int, report: dict) -> IndexRebuild:
    """Read one index run's outcome into the verdict its caller has to act on.

    Shared by the rebuild above and the read-only scan below, because the 2026-09-15
    ruling — one author's schema-invalid review is survivable, every other non-zero is
    not — must not depend on whether the run that hit it wrote anything. A second copy
    of this predicate is how a path acquires its own idea of what is survivable.
    """
    from feedback import feedback_index  # noqa: PLC0415

    # Read from the module rather than restated here, so the two vocabularies are one.
    survivable = {feedback_index.REASON_AUTHOR_COMPLETE_INVALID}
    reasons = set(report.get("exit_reasons") or ())
    return IndexRebuild(
        rc=rc,
        skipped_reviews=list(report.get("author_complete_drops") or []),
        fatal=rc != 0 and not (reasons and reasons <= survivable),
    )


def _scan_index_reporting() -> tuple[list[dict], IndexRebuild]:
    """The rows a rebuild WOULD publish, for a run that is not entitled to publish them.

    Triage's read commands — `--check`, `--digest`, `--monthly` — report over the corpus;
    they do not change it. Until #102 they all reached it through `feedback_index
    --rebuild`, so rendering a report REWROTE the operator's index: `session_init` runs
    `--check` on every session start to print one dashboard line, and measured on
    2026-09-15 that line moved the live `index.jsonl` mtime while leaving its bytes
    identical. A caller is entitled to assume a command called `check` is safe.

    The rows come from a full scan rather than from the index file, so dropping the write
    costs no freshness: they are computed from the reviews themselves and are, if
    anything, fresher than the file a rebuild would have left behind. What is given up is
    only the side effect — which is what spec 086 specified all along ("`/team.start`
    only READS the pre-built index; it never rebuilds"), and what `commands/triage.md`
    already claimed `--check` did ("without mutating anything").
    """
    from feedback import feedback_index  # noqa: PLC0415

    report: dict = {}
    rows, rc = feedback_index.scan(report)
    return rows, _classify(rc, report)


def skipped_reviews_note(skipped: list[str], absent_from: str) -> str:
    """The one wording for "N reviews are missing from everything this run reports".

    One formatter rather than one per call site: triage and the verify sweep both have
    to say it, and a reader who learns the sentence at one of them should recognise it
    at the other. The wording itself is a display contract and belongs to kosmos-cxo —
    this function only keeps the two copies from drifting.
    """
    return (
        f"NOTE: {len(skipped)} author-complete review(s) were skipped as schema-invalid "
        f"and are absent from {absent_from}. Re-run `feedback_emit.py --finalize <path>` "
        f"on each to see what it rejects."
    )


def reconcile_index_after_writes(what: str) -> int:
    """Rebuild the index after a run has already written, and report a failure loudly.

    The same rebuild as the pre-write callers above, with the opposite verdict. BEFORE
    the writes, a fatal rebuild means the run must not report over an index it never
    produced, so it aborts. AFTER them there is nothing left to abort: the writes landed
    and are correct on disk, and what failed is the cache every consumer reads.

    So `return 0` and "the operation failed" are both false, and the run says the two
    things separately — its own stdout keeps reporting what it wrote, and this line plus
    a non-zero exit report that the cache no longer matches. Measured on 8702a27: an
    archive printed feedback_index's own lock ERROR on stderr, then "Done: 1 item(s)
    archived" on stdout, and exited 0. The message existed; no decision read it.

    The recovery named is the rebuild, because it is the idempotent half. Re-running the
    WRITE is not: for `--set` it is a re-transition, the operation that rewrote all 53
    `accepted_at` stamps on 2026-08-31.

    A rebuild that only skipped a schema-invalid review is NOT a stale cache — it did
    rewrite the index, which matches the tree for everything it holds. That is the
    2026-09-15 ruling, read from the same `fatal` field as the pre-write callers so the
    two vocabularies cannot drift apart.

    The wording is a display contract and belongs to kosmos-cxo; this function only
    keeps the three call sites from drifting.
    """
    rebuild = _rebuild_index_reporting()
    if not rebuild.fatal:
        return 0
    print(f"ERROR: {what} completed, but the feedback index could NOT be rebuilt "
          f"(cause above), so it no longer matches the reviews on disk — every figure "
          f"read from it is stale until that is fixed. The writes stand; do not repeat "
          f"them. Clear the cause, then re-run `feedback_index.py --rebuild`.",
          file=sys.stderr)
    return rebuild.rc


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


def unreachable_accepted(rows: list[dict]) -> list[dict]:
    """Accepted rows carrying no predicate, no waiver and no issue link.

    Such a row is reachable by no mechanism: `--monthly`'s zombie pass scopes to
    open/deferred, and closing verification needs one of `verify`, `verify_waiver`
    or `issue` to fire on. Sorted by `accepted_at` ascending (oldest first); rows
    with no `accepted_at` sort last, since their age is unknown rather than zero.
    """
    found = [
        row for row in rows
        if row.get("status") == "accepted"
        and not row.get("verify")
        and not row.get("verify_waiver")
        and not row.get("issue")
    ]
    found.sort(key=lambda r: r.get("accepted_at") or "9999-99-99")
    return found


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
            # `or ""`, not a get-default: since suggested_fix became optional the index
            # writes the key with a null, and `.get(k, "")` only substitutes for a MISSING
            # key — a present null passes straight through and changes the type.
            "suggested_fix": rep.get("suggested_fix") or "",
            "frequency": rep.get("frequency", ""),
            "status": rep.get("status", "open"),
            "members": [
                {"feedback_id": r.get("feedback_id", ""), "item_id": r.get("item_id", "")}
                for r in group
            ],
        })

    # Sort: every defect first (critical-first among themselves), then the categories
    # that name no fix. Severity on a `positive` or a `near-miss` describes how much was
    # learned, not how much is broken, so ranking the two on one scale spends a
    # reviewer's attention on rows with nothing to decide (#250).
    entries.sort(key=lambda e: (
        e["category"] in _NON_DEFECT_CATEGORIES,
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


# #89 — the cadence, as commands/triage.md and feedback-protocol.md both state it:
#     now - last_triage > 7 days   OR   new reviews since last triage >= 15
# The code used to read `days_since > 7 or open_count > 0` — an ITEM count against a
# threshold of one. So a completed triage re-armed the notice that demands a triage: the
# session's own freshly filed review left open items behind. The banner then appeared at
# every SessionStart forever and carried no information, a backlog of 27 and a backlog of
# 1 being indistinguishable. It also implemented precisely the behaviour the protocol's
# own anti-patterns table forbids ("running triage outside the weekly window for a single
# urgent item").
TRIAGE_CADENCE_DAYS = 7
TRIAGE_NEW_REVIEW_THRESHOLD = 15


def _created_ts(row: dict) -> float | None:
    """Epoch seconds of a row's `created`, or None when it cannot be read.

    Index rows carry both `2026-05-22T10:00:00Z` and `2026-08-18 22:32:07+00:00`;
    fromisoformat takes both on 3.11+."""
    raw = row.get("created")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)).timestamp()
    except (ValueError, TypeError):
        return None


def _last_triage_ts(marker: Path) -> float | None:
    """When the last triage session completed, or None when none ever has.

    The marker records the completion timestamp in its body. Its mtime cannot carry
    that: every write to the file moves the mtime, and before this the writes were
    `--set` and `--set-verify` — per-item edits, run once per item, which reset the
    cadence clock on each classified item. So an unreadable or empty marker is `None`
    (never triaged), never "triaged when the file was last touched": absence and zero
    must not render alike (state-report.md rule 6), and the live instance carries
    exactly that file — 0 bytes with a fresh mtime, from the last --set-verify."""
    if not marker.exists():
        return None
    try:
        raw = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.splitlines()[0].strip()).timestamp()
    except (ValueError, TypeError):
        return None


def _mark_triage_complete(marker: Path) -> str:
    """Record that a triage session finished. The only write that moves the clock."""
    stamp = datetime.now(UTC).isoformat()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(stamp + "\n", encoding="utf-8")
    return stamp


def _new_review_count(rows: list[dict], since_ts: float | None) -> int:
    """Distinct reviews created after `since_ts` (all of them when never triaged).

    Counted per feedback_id, not per row: a review carries several items and the
    documented rule counts REVIEWS. Conflating the two is the original defect."""
    seen = set()
    for r in rows:
        if since_ts is not None:
            ts = _created_ts(r)
            if ts is None or ts <= since_ts:
                continue
        seen.add(r.get("feedback_id"))
    return len(seen)


def cmd_check(rows: list[dict], triage_marker: Path, skipped_invalid: int = 0) -> None:
    """Print the cadence verdict and, beside it, every quantity it was computed from.

    `skipped_invalid` is printed unconditionally, including as 0. A field that appears
    only when it is non-zero cannot be told from a field a consumer forgot to emit, so
    a run that could not see part of the corpus would render identically to a clean one
    — which is the failure this whole line exists to report.
    """
    open_count = sum(1 for r in rows if r.get("status") == "open")

    last_triage = _last_triage_ts(triage_marker)
    if last_triage is None:
        days_since_str = "never"
        triage_due = True
    else:
        days_since = (datetime.now(UTC).timestamp() - last_triage) / 86400
        days_since_str = f"{days_since:.1f}"
        triage_due = days_since > TRIAGE_CADENCE_DAYS
    new_reviews = _new_review_count(rows, last_triage)
    triage_due = triage_due or new_reviews >= TRIAGE_NEW_REVIEW_THRESHOLD

    print(f"triage_due={'true' if triage_due else 'false'}")
    # open_items is no longer the trigger, but it is still the backlog size an operator
    # wants beside the verdict — and it is an ITEM count, which the banner used to render
    # as "open reviews".
    print(f"open_items={open_count}")
    print(f"new_reviews={new_reviews}")
    print(f"days_since={days_since_str}")
    print(f"unreachable_accepted={len(unreachable_accepted(rows))}")
    print(f"skipped_invalid_reviews={skipped_invalid}")
    # Not a cadence figure, and not rendered on this line at all: session_init's G6 row
    # counts open critical items, and until #102 it got them by reading the index file
    # that THIS command had just rebuilt ten lines earlier. Two dashboard steps joined by
    # a side effect, with no call and no argument between them. Emitting the count here
    # makes the dependency an argument; the predicate is `severity == critical and
    # status == open`, the same one G6 applied to the file.
    print(f"critical_open={sum(1 for r in rows if r.get('severity') == 'critical' and r.get('status') == 'open')}")


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
    else:
        found.sort(key=lambda x: -x[0])
        print(f"{'feedback_id':<25} {'item_id':<15} {'age_days':<10} {'status':<12} observation")
        print("-" * 90)
        for age, row in found:
            print(f"{row.get('feedback_id', ''):<25} {row.get('item_id', ''):<15} "
                  f"{age:<10} {row.get('status', ''):<12} {row.get('observation', '')[:40]}")

    # Second, independent section: accepted items reachable by no mechanism (no
    # predicate, no waiver, no issue link). Printed unconditionally, even when
    # count is 0 — this is an inventory surface, and a zero is load-bearing
    # (Global Constraint 3). Keyed on accepted_at (R1), no age cutoff (R2).
    unreachable = unreachable_accepted(rows)
    print()
    print(f"Unreachable accepted items (no predicate, no waiver, no issue link): "
          f"{len(unreachable)}")
    if unreachable:
        print(f"{'feedback_id':<25} {'item_id':<15} {'age_days':<10} {'status':<12} observation")
        print("-" * 90)
        for row in unreachable:
            accepted_at = row.get("accepted_at")
            if accepted_at:
                try:
                    accepted = datetime.fromisoformat(accepted_at.replace("Z", "+00:00"))
                    age_str = str((now - accepted).days)
                except (ValueError, AttributeError):
                    age_str = "—"
            else:
                age_str = "—"
            print(f"{row.get('feedback_id', ''):<25} {row.get('item_id', ''):<15} "
                  f"{age_str:<10} {row.get('status', ''):<12} {row.get('observation', '')[:40]}")


def cmd_set(root: Path, feedback_id: str, item_id: str, status: str,
            owner: str | None, issue: int | None = None,
            waiver: str | None = None) -> int:
    """Write status/owner/issue/waiver/resolved_at back to the review file."""
    if status not in _VALID_STATUSES:
        print(f"ERROR: invalid status={status!r} (allowed: {sorted(_VALID_STATUSES)})",
              file=sys.stderr)
        return 1
    if owner is not None and _unknown_owner(owner):
        print(
            f"ERROR: refusing to set owner={owner!r} on {feedback_id}/{item_id}: "
            f"no advisor by that id is on the roster.\n"
            f"       An owner nothing resolves is not a routing error you can see -- "
            f"every owner-scoped query simply omits the item.\n"
            f"       Roster: {', '.join(sorted(canonical_advisors())) or '(empty)'}\n"
            f"       Use one of those, or hire the advisor first "
            f"(`engine advisor create`).",
            file=sys.stderr,
        )
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
            # #218 — item-level touch, on THIS item only, same timestamp as meta's
            # updated_at below so the two never disagree by a microsecond. Do not drop
            # this: it is what stops closing one item from restamping its siblings.
            item["touched_at"] = now_str
            found = True
            break

    if not found:
        print(f"ERROR: item_id={item_id} not found in feedback_id={feedback_id}", file=sys.stderr)
        return 1

    meta["updated_at"] = now_str
    write_preserving_header(review_path, meta, body)

    print(f"Updated {feedback_id}/{item_id}: status={status}" +
          (f" owner={owner}" if owner else "") +
          (f" issue=#{issue}" if issue else "") +
          (" waiver=recorded" if waiver else ""))
    return 0


def cmd_set_verify(root: Path, feedback_id: str, item_id: str,
                   predicate: dict, *, force: bool = False,
                   project_root_path: Path | None = None,
                   code_root: Path | None = None) -> int:
    """Attach a verify: predicate to an existing item (093 P1 T3).

    Sanctioned write path so feeding an accepted backlog never needs hand-editing
    finalized frontmatter. Caller must hold the .triage-lock (the mkdir-poll lock is
    not reentrant, so cmd_set_verify — like cmd_set — never re-acquires it here).

    #161 — the admission test (refuse a predicate that already passes or is broken)
    lives HERE, not one level up in the CLI. `feedback_verify.py`'s --set-verify
    branch keeps its own pre-check for the richer human-facing message, but that
    made the guard a one-caller-deep property rather than an invariant: this is
    the writer, so this is where every caller is bound by it.
    """
    from feedback.schema import Predicate
    try:
        Predicate(**predicate)  # validate shape before writing
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: invalid predicate: {exc}", file=sys.stderr)
        return 1
    # feedback_verify imports cmd_set_verify from this module, so this import
    # stays inside the function to avoid the cycle.
    from feedback_verify import classify_predicate  # noqa: PLC0415
    verdict = classify_predicate(Predicate(**predicate), project_root_path or project_root(), code_root)
    if verdict != "fail" and not force:
        print(f"ERROR: refusing to attach verify to {feedback_id}/{item_id}: "
              f"verdict={verdict} (expected 'fail')", file=sys.stderr)
        return 1
    review_path = _find_review_file(root, feedback_id)
    if review_path is None:
        print(f"ERROR: review not found for feedback_id={feedback_id}", file=sys.stderr)
        return 1
    meta, body = read_commented(review_path)
    now_str = datetime.now(UTC).isoformat()
    found = False
    for item in meta.get("items", []):
        if item.get("id") == item_id:
            item["verify"] = predicate
            # #218 — item-level touch, on THIS item only; same timestamp as meta's
            # updated_at below so the two never disagree by a microsecond.
            item["touched_at"] = now_str
            found = True
            break
    if not found:
        print(f"ERROR: item_id={item_id} not found in feedback_id={feedback_id}",
              file=sys.stderr)
        return 1
    meta["updated_at"] = now_str
    write_preserving_header(review_path, meta, body)
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
    parser.add_argument("--complete-triage", action="store_true",
                        help="Record that a triage session finished — the one write that "
                             "resets the cadence clock. Run it as the last step of "
                             "/conclave:triage, never per item.")
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

    # Whether this invocation WRITES is what decides how it reaches the corpus — not the
    # name of the flag. `--set` rewrites a review file and `--complete-triage` moves the
    # cadence clock; the other three only report. Until #102 the distinction did not
    # exist: every path rebuilt the index first, so `--check` — the one session_init runs
    # on EVERY session start to render a single dashboard line — mutated instance state
    # in order to read it.
    writes = bool(args.set or args.complete_triage)

    # Serialize the whole triage mutation — index rebuild + any write-back — on a
    # DATA-root advisory lock, so two concurrent triage sessions on the same root
    # can't corrupt index.jsonl or clobber each other's review write-back (#51).
    #
    # A reporting run takes no lock because it has nothing to serialize: it writes
    # neither the index nor a review. Nor can it read a torn review — every writer on
    # this path goes through snapshot_write (tmp sibling + os.replace), so a concurrent
    # reader sees the whole old file or the whole new one, never half of either. The
    # lock was costing what it could not buy: four advisors starting at once serialised
    # on it, each for a full walk of the review tree, to print one line apiece.
    lock = contextlib.ExitStack()
    if writes:
        lock_file = lock_path_for(triage_lock_target(root))
        lock_timeout = int(os.environ.get("CONCLAVE_TRIAGE_LOCK_TIMEOUT", "5"))
        try:
            lock.enter_context(with_lock(lock_file, timeout=lock_timeout))
        except LockTimeout:
            print(f"ERROR: could not acquire triage lock at {lock_file} "
                  f"(concurrent triage session?)", file=sys.stderr)
            return 1
    try:
        # Step 1: see the corpus whole, before reporting over it or writing into it.
        # Non-zero exit means _draft:false reviews are schema-invalid — abort triage
        # so corrupted reviews never silently bypass the queue. The two branches differ
        # only in whether the result is published to disk; the verdict they read is
        # derived by one function from one field, so neither can drift from the other.
        rows: list[dict] | None = None
        if writes:
            rebuild = _rebuild_index_reporting()
        else:
            rows, rebuild = _scan_index_reporting()
        skipped_reviews = rebuild.skipped_reviews
        if rebuild.fatal:
            # Still fatal: a file the run could not read, a lock it could not take, or a
            # non-zero it cannot account for. Continuing past an unexplained failure would
            # be the silence this whole path exists to prevent.
            print(
                "ERROR: triage aborted — the index rebuild failed for a reason other than "
                "a schema-invalid review. Fix the errors shown above, then re-run.",
                file=sys.stderr,
            )
            return rebuild.rc
        if skipped_reviews:
            # Ruled 2026-09-15 (Helm, engine scope) after one hand-flipped `_draft: false`
            # review took the cadence check down for all three advisors of an instance for
            # ~34 hours: aborting converts one author's defect into an instance-wide outage,
            # and a check that reports nothing is read as "nothing is wrong".
            #
            # Spec 086 AC2's invariant is kept and read literally — the review never enters
            # the index, and the DROPPED line above names it. What it forbids is a *silent*
            # bypass, and the count below is what makes this one not silent.
            print(skipped_reviews_note(skipped_reviews, "every figure below"),
                  file=sys.stderr)

        if rows is None:
            # The write path reads back the index it has just rebuilt. The reporting
            # path already holds the same rows — computed from the reviews, never
            # written — so it never touches this file at all.
            rows = _load_index(index_path())
        triage_marker = last_triage_marker()

        if args.set:
            feedback_id, item_id, status = args.set
            set_rc = cmd_set(root, feedback_id, item_id, status, args.owner,
                             issue=args.issue, waiver=args.waiver)
            if set_rc == 0:
                # Reconcile the cache with the review we just wrote. The rebuild above runs
                # BEFORE the write, so without this the index lags the source of truth by
                # exactly one --set: the last item classified in a session stays invisible
                # to the digest, --check and the dashboard until something else rebuilds.
                # feedback_verify already does this after its own writes; cmd_set did not.
                set_rc = reconcile_index_after_writes("the --set write")
            return set_rc

        if args.digest:
            digest_rows = rows
            if args.status:
                digest_rows = [r for r in rows if r.get("status") == args.status]
            cmd_digest(digest_rows, as_json=args.json)

        if args.check:
            cmd_check(rows, triage_marker, skipped_invalid=len(skipped_reviews))

        if args.monthly:
            cmd_monthly(rows)

        if args.complete_triage:
            stamp = _mark_triage_complete(triage_marker)
            print(f"triage recorded complete at {stamp}")

        if not any([args.digest, args.check, args.monthly, args.set,
                    args.complete_triage]):
            parser.print_help()

        return 0
    finally:
        lock.close()


if __name__ == "__main__":
    sys.exit(main())

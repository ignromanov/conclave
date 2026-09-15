"""feedback_index.py — validate + build JSONL index for spec 086.

CLI: python feedback_index.py [--check]

Default: rebuild _index/index.jsonl from every review under
ops/feedback/YYYY-MM-DD/ and _migrated/. Incrementally skips files
whose updated_at < the existing index row's updated_at (a tie is
re-read, since it may hide a status change from a batch --set run).

--check: print reviews=<n> pending_triage=<n> without writing.

Validation (per spec):
- _draft: true reviews → skipped silently
- items missing evidence (unless migrated: true) → reject + stderr + non-zero exit
- items missing location / observation → reject (suggested_fix became optional 2026-09-08,
  spec 117: evidence carries the mandate, a fix is recorded only when the agent has one)
- review with below_threshold_count > 0 and empty items → reject
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from briefing.frontmatter_io import read as fm_read  # noqa: E402
from briefing.paths import repo_root  # noqa: E402
from enginelib import integrity  # noqa: E402
from enginelib.lock import LockTimeout, lock_path_for, with_lock  # noqa: E402
from enginelib.snapshot import snapshot_write  # noqa: E402
from feedback.paths import index_lock_target, index_path  # noqa: E402
from feedback.schema import Review, fingerprint  # noqa: E402


def _ts_to_epoch(ts: str) -> int:
    try:
        return int(datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
    except (ValueError, AttributeError):
        return 0


def _review_dirs(root: Path) -> list[Path]:
    """Return all dated YYYY-MM-DD dirs + _migrated dir under ops/feedback/."""
    fb_root = root / "ops" / "feedback"
    if not fb_root.exists():
        return []
    dated = [
        d for d in fb_root.iterdir()
        if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)
    ]
    mig = fb_root / "_migrated"
    dirs = sorted(dated, key=lambda d: d.name)
    if mig.is_dir():
        dirs.append(mig)
    return dirs


def _load_existing_index(idx_path: Path) -> dict[str, str]:
    """Return {(review_id, item_id): updated_at} from existing index for incremental skip."""
    if not idx_path.exists():
        return {}
    rows: dict[str, str] = {}
    for line in idx_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
            key = f"{row.get('feedback_id', '')}:{row.get('item_id', '')}"
            rows[key] = row.get("updated_at", "")
        except json.JSONDecodeError:
            pass
    return rows


def _merge_rows(rows: list[dict], idx_path: Path, *, rebuild: bool) -> list[dict]:
    """Rows to publish: a clean set on --rebuild, else new rows over the kept old ones.

    Malformed existing lines are counted rather than dropped in silence. The detector
    was already here (`except json.JSONDecodeError: pass`) — it just threw the evidence
    away, which is why no one could say whether index corruption was rare or routine.
    """
    if rebuild:
        # Clean rebuild: every live item is in `rows` (nothing was skipped), so
        # write rows-only. Rows whose source review is gone simply don't reappear.
        return rows

    # Incremental default: existing rows not in the new batch are preserved,
    # since _process_reviews skips items already indexed at a newer updated_at.
    existing_rows: list[dict] = []
    malformed = 0
    if idx_path.exists():
        for line in idx_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing_rows.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1

    if malformed:
        integrity.record(
            integrity.log_path_beside(idx_path),
            "index.malformed_line",
            count=malformed,
            path=str(idx_path),
        )

    # Build map of new rows keyed by (feedback_id, item_id)
    new_keys = {(r["feedback_id"], r["item_id"]) for r in rows}

    # Keep old rows not replaced by new ones
    kept = [r for r in existing_rows if (r.get("feedback_id"), r.get("item_id")) not in new_keys]
    return kept + rows


def _process_reviews(dirs: list[Path], existing: dict[str, str], check: bool) -> tuple[list[dict], list[str], list[str], list[str], int]:
    """Walk dirs, validate, produce index rows + rejection messages.

    Returns (rows, parse_errors, author_complete_drops, review_count).
    author_complete_drops: paths of _draft:false files that failed schema validation.
    """
    rows: list[dict] = []
    parse_errors: list[str] = []
    author_complete_drops: list[str] = []
    # Files that could not be READ, as distinct from files that were read and failed
    # validation. Both land in parse_errors, so parse_errors cannot tell a caller which
    # it is holding — and the two are not equally survivable.
    unreadable: list[str] = []
    review_count = 0

    for d in dirs:
        for md_file in sorted(d.glob("*.md")):
            try:
                meta, _body = fm_read(md_file)
            except Exception as e:
                parse_errors.append(f"SKIP {md_file}: parse error: {e}")
                unreadable.append(str(md_file))
                continue

            # Draft reviews skipped silently
            if meta.get("_draft", False):
                continue

            review_count += 1

            # Validate via pydantic Review model
            try:
                review = Review.model_validate(meta)
            except ValidationError as exc:
                msg = f"REJECT {md_file}: {exc.error_count()} validation error(s): {exc}"
                parse_errors.append(msg)
                author_complete_drops.append(str(md_file))
                continue

            for item in review.items:
                key = f"{review.feedback_id}:{item.id}"
                existing_ts = existing.get(key, "")
                if existing_ts and _ts_to_epoch(existing_ts) > _ts_to_epoch(str(review.updated_at)):
                    # Incremental skip: already indexed at a strictly newer updated_at.
                    # A tie re-reads the file rather than trusting the stale row — batch
                    # feedback_triage.py --set calls can leave several items sharing one
                    # final review updated_at, so a tie doesn't mean "unchanged" (issue #8).
                    continue

                # An archived item lives on in the review file verbatim; it is out of the
                # working set, so it must not re-enter the index the next rebuild rewrites.
                if item.archived_at:
                    continue

                fp = fingerprint(item.location, item.category)

                row = {
                    "feedback_id": review.feedback_id,
                    "agent": review.agent,
                    "agent_type": review.agent_type,
                    "session_ref": review.session_ref,
                    "created": str(review.created),
                    # Review-level "has this file been rewritten since I indexed it" —
                    # `_process_reviews`'s incremental-skip check above needs exactly this
                    # field. touched_at below answers a different question ("how long has
                    # THIS item sat"); one field cannot answer both (#218).
                    "updated_at": str(review.updated_at),
                    # Item-level, only ever set by a write path that modified THIS item
                    # (cmd_set, cmd_set_verify). No fallback to review.updated_at here: an
                    # untouched item's touched_at is unknown, not the review's timestamp —
                    # consumers do the falling back, visibly (#218).
                    "touched_at": str(item.touched_at) if item.touched_at else "",
                    "item_id": item.id,
                    "category": item.category,
                    "layer": item.layer,
                    "location": item.location.model_dump(),
                    "fingerprint": fp,
                    "observation": item.observation,
                    "suggested_fix": item.suggested_fix,
                    "severity": item.severity,
                    "frequency": item.frequency,
                    "evidence": item.evidence,
                    "status": item.status,
                    "owner": item.owner,
                    "issue": item.issue,
                    "accepted_at": item.accepted_at,
                    "resolved_at": str(item.resolved_at) if item.resolved_at else None,
                    "reopened_from": item.reopened_from,
                    "migrated": item.migrated,
                    "legacy_source": item.legacy_source,
                    "verify": item.verify.model_dump() if item.verify else None,
                    "verify_waiver": item.verify_waiver,
                }
                rows.append(row)

    return rows, parse_errors, author_complete_drops, unreadable, review_count


def main(argv: list[str] | None = None, report: dict | None = None) -> int:
    """Build the index; `report`, when given, receives what the exit code cannot carry.

    The exit code says only "something was wrong". A caller that must decide whether to
    continue needs to know *which* thing: a dropped author-complete review is one
    author's defect and is survivable, an unreadable file is not. Passing a dict here
    is how feedback_triage tells them apart; the CLI passes nothing and is unchanged.
    """
    parser = argparse.ArgumentParser(description="Validate + build feedback JSONL index")
    parser.add_argument("--check", action="store_true", default=False,
                        help="print stats without writing index")
    parser.add_argument("--rebuild", action="store_true", default=False,
                        help="ignore the existing index and write a clean one from the "
                             "review files (drops stale rows from deleted/archived reviews)")
    args = parser.parse_args(argv)

    root = repo_root()

    dirs = _review_dirs(root)
    # One derivation, shared with the lock target: a lock keyed off a second
    # spelling of this path would guard a file this writer never writes.
    idx_path = index_path()
    # --rebuild passes an empty `existing` so no item is incrementally skipped —
    # every live review is re-processed and the write path emits rows-only (#9).
    existing = {} if args.rebuild else _load_existing_index(idx_path)

    rows, parse_errors, author_complete_drops, unreadable, review_count = _process_reviews(dirs, existing, args.check)

    # Populated before either exit path below, so a caller's view never depends on
    # which branch the run took.
    if report is not None:
        report["author_complete_drops"] = list(author_complete_drops)
        report["parse_errors"] = list(parse_errors)
        report["unreadable"] = list(unreadable)
        report["review_count"] = review_count

    if args.check:
        pending = sum(1 for r in rows if r.get("status") == "open")
        print(f"reviews={review_count} pending_triage={pending}")
        if parse_errors:
            for msg in parse_errors:
                print(msg, file=sys.stderr)
        if author_complete_drops:
            paths = ", ".join(author_complete_drops)
            print(
                f"DROPPED {len(author_complete_drops)} author-complete reviews (schema-invalid): {paths}",
                file=sys.stderr,
            )
        return 1 if (parse_errors or author_complete_drops) else 0

    # Write index — the read-modify-write below runs under the index's OWN lock.
    #
    # Its own, deliberately: `flock` is not reentrant across file descriptors, and
    # triage rebuilds the index while holding the triage lock, so one shared lock
    # would self-deadlock. Lock per resource, always taken triage -> index.
    #
    # Before 118 C1.1 there was no lock here at all, while the other writer (triage,
    # via the post-commit hook's sibling path) held one. The lock existed; it was
    # not the lock this writer took.
    idx_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = lock_path_for(index_lock_target())
    lock_timeout = float(os.environ.get("CONCLAVE_INDEX_LOCK_TIMEOUT", "10"))
    try:
        with with_lock(lock_file, timeout=lock_timeout):
            merged = _merge_rows(rows, idx_path, rebuild=args.rebuild)
            # snapshot_write, not a fixed `index.tmp`: it stages in `.tmp.<pid>` so two
            # concurrent writers cannot rename each other's half-written file into place.
            snapshot_write(
                idx_path,
                "\n".join(json.dumps(r) for r in merged) + ("\n" if merged else ""),
            )
    except LockTimeout:
        print(f"ERROR: could not acquire the feedback index lock at {lock_file} "
              f"(concurrent writer?)", file=sys.stderr)
        return 1

    if parse_errors:
        for msg in parse_errors:
            print(msg, file=sys.stderr)
    if author_complete_drops:
        paths = ", ".join(author_complete_drops)
        print(
            f"DROPPED {len(author_complete_drops)} author-complete reviews (schema-invalid): {paths}",
            file=sys.stderr,
        )
    if author_complete_drops or parse_errors:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

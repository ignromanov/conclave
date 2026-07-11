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
- items missing location / observation / suggested_fix → reject
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


def _process_reviews(dirs: list[Path], existing: dict[str, str], check: bool) -> tuple[list[dict], list[str], list[str], int]:
    """Walk dirs, validate, produce index rows + rejection messages.

    Returns (rows, parse_errors, author_complete_drops, review_count).
    author_complete_drops: paths of _draft:false files that failed schema validation.
    """
    rows: list[dict] = []
    parse_errors: list[str] = []
    author_complete_drops: list[str] = []
    review_count = 0

    for d in dirs:
        for md_file in sorted(d.glob("*.md")):
            try:
                meta, _body = fm_read(md_file)
            except Exception as e:
                parse_errors.append(f"SKIP {md_file}: parse error: {e}")
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

                fp = fingerprint(item.location, item.category)

                row = {
                    "feedback_id": review.feedback_id,
                    "agent": review.agent,
                    "agent_type": review.agent_type,
                    "session_ref": review.session_ref,
                    "updated_at": str(review.updated_at),
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
                    "migrated": item.migrated,
                    "legacy_source": item.legacy_source,
                    "verify": item.verify.model_dump() if item.verify else None,
                }
                rows.append(row)

    return rows, parse_errors, author_complete_drops, review_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate + build feedback JSONL index")
    parser.add_argument("--check", action="store_true", default=False,
                        help="print stats without writing index")
    parser.add_argument("--rebuild", action="store_true", default=False,
                        help="ignore the existing index and write a clean one from the "
                             "review files (drops stale rows from deleted/archived reviews)")
    args = parser.parse_args(argv)

    root = repo_root()

    dirs = _review_dirs(root)
    idx_path = root / "ops" / "feedback" / "_index" / "index.jsonl"
    # --rebuild passes an empty `existing` so no item is incrementally skipped —
    # every live review is re-processed and the write path emits rows-only (#9).
    existing = {} if args.rebuild else _load_existing_index(idx_path)

    rows, parse_errors, author_complete_drops, review_count = _process_reviews(dirs, existing, args.check)

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

    # Write index
    idx_path.parent.mkdir(parents=True, exist_ok=True)

    if args.rebuild:
        # Clean rebuild: every live item is in `rows` (nothing was skipped), so
        # write rows-only. Rows whose source review is gone simply don't reappear.
        merged = rows
    else:
        # Incremental default: existing rows not in the new batch are preserved,
        # since _process_reviews skips items already indexed at a newer updated_at.
        existing_rows: list[dict] = []
        if idx_path.exists():
            for line in idx_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    existing_rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

        # Build map of new rows keyed by (feedback_id, item_id)
        new_keys = {(r["feedback_id"], r["item_id"]) for r in rows}

        # Keep old rows not replaced by new ones
        kept = [r for r in existing_rows if (r.get("feedback_id"), r.get("item_id")) not in new_keys]
        merged = kept + rows

    tmp = idx_path.with_suffix(".tmp")
    tmp.write_text(
        "\n".join(json.dumps(r) for r in merged) + ("\n" if merged else ""),
        encoding="utf-8",
    )
    os.replace(tmp, idx_path)

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

"""feedback_archive.py — archive resolved reviews + hot.md finding for spec 086.

CLI: python feedback_archive.py [--note "<text>"]

Moves every review whose items are ALL resolved/rejected into
_archive/YYYY-MM.jsonl (append), removes the source markdown, and appends
a one-line finding to agent-memory/hot.md (via briefing.paths.hot_md_path).
Refuses to re-archive an id already present in any archive file.

The archive row carries the review's items and body verbatim: once the markdown is
unlinked it is the only record. The hot.md line is a deduped, truncated projection.
"""
from __future__ import annotations

import argparse
import json
import re
import sys

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
from feedback.feedback_emit import write_preserving_header  # noqa: E402

_DONE_STATUSES = {"resolved", "rejected"}


def _load_archived_item_keys(arch_dir: Path) -> set[tuple[str, str]]:
    """Return {(feedback_id, item_id)} already written as item-kind archive rows.

    Item rows and review rows share the ledger, so the review-level guard (which keys on
    feedback_id alone) must not see an item row as "this review is archived" — and an
    item row must not be appended twice. Two guards, two key shapes.
    """
    keys: set[tuple[str, str]] = set()
    if not arch_dir.exists():
        return keys
    for arch_file in sorted(arch_dir.glob("*.jsonl")):
        with arch_file.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("kind") == "item" and row.get("item_id"):
                    keys.add((row.get("feedback_id", ""), row["item_id"]))
    return keys


def _load_archived_ids(arch_dir: Path) -> set[str]:
    """Collect feedback_ids archived as WHOLE reviews in any _archive/*.jsonl file.

    Item-kind rows are skipped: one archived item does not make its review archived, and
    counting it would make the review-level guard refuse a review it never wrote.
    """
    ids: set[str] = set()
    if not arch_dir.exists():
        return ids
    for jsonl in arch_dir.glob("*.jsonl"):
        for line in jsonl.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("kind") == "item":
                    continue
                fid = row.get("feedback_id")
                if fid:
                    ids.add(fid)
            except json.JSONDecodeError:
                pass
    return ids


def _review_dirs(fb_root: Path) -> list[Path]:
    """Return all dated YYYY-MM-DD dirs under ops/feedback/ (not _archive/_index etc.)."""
    if not fb_root.exists():
        return []
    return sorted(
        [d for d in fb_root.iterdir()
         if d.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", d.name)],
        key=lambda d: d.name,
    )


def _all_done(items: list[dict]) -> bool:
    return bool(items) and all(
        item.get("status", "open") in _DONE_STATUSES for item in items
    )


def _archive_month(created_str: str) -> str:
    """Return 'YYYY-MM' from a created datetime string."""
    try:
        dt = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m")
    except (ValueError, AttributeError):
        return datetime.now(UTC).strftime("%Y-%m")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Archive resolved feedback reviews")
    parser.add_argument("--note", default=None,
                        help="Optional extra note appended to the hot.md line")
    args = parser.parse_args(argv)

    root = repo_root()
    fb_root = root / "ops" / "feedback"
    arch_dir = fb_root / "_archive"

    # Build set of already-archived ids (dedup guard)
    archived_ids = _load_archived_ids(arch_dir)
    archived_item_keys = _load_archived_item_keys(arch_dir)

    dirs = _review_dirs(fb_root)
    archived_count = 0
    archived_items = 0
    errors: list[str] = []

    for d in dirs:
        for md_file in sorted(d.glob("*.md")):
            try:
                meta, body = fm_read(md_file)
            except Exception as e:
                errors.append(f"SKIP {md_file}: parse error: {e}")
                continue

            # Skip drafts
            if meta.get("_draft", False):
                continue

            feedback_id = meta.get("feedback_id", "")
            items = meta.get("items", [])

            if not _all_done(items):
                # Partial review: archive its already-closed items one by one. The archive
                # unit has to be the ITEM because the lifecycle unit is — a review closes
                # only when every one of its items does, which for a multi-item review
                # effectively never happens, so a review-only archiver never fires at all.
                #
                # Nothing is removed here. The item stays in the review verbatim and only
                # gains `archived_at`; the index skips marked items, which is what takes
                # them out of the working set. Cutting items out of the source file is the
                # variant this does NOT do — six reviews already lost their bodies that way.
                arch_dir.mkdir(parents=True, exist_ok=True)
                month = _archive_month(str(meta.get("created", "")))
                arch_file = arch_dir / f"{month}.jsonl"
                # Two sets, because the ledger append and the review stamp are separate
                # writes: if the append lands and the stamp does not, the item is in the
                # ledger with no `archived_at` and would otherwise sit in the index forever
                # while the key guard blocks a retry. Stamp everything closed-and-unstamped;
                # append only what the ledger has not already got.
                to_stamp = [it for it in items
                            if it.get("status") in _DONE_STATUSES and not it.get("archived_at")]
                to_append = [it for it in to_stamp
                             if (feedback_id, it.get("id")) not in archived_item_keys]
                if not to_stamp:
                    continue
                with arch_file.open("a", encoding="utf-8") as fh:
                    for it in to_append:
                        fh.write(json.dumps({
                            "kind": "item",
                            "feedback_id": feedback_id,
                            "item_id": it.get("id"),
                            "agent": meta.get("agent", ""),
                            "agent_type": meta.get("agent_type", ""),
                            "session_ref": meta.get("session_ref", ""),
                            "created": str(meta.get("created", "")),
                            "archived_at": datetime.now(UTC).isoformat(),
                            "source_file": str(md_file.relative_to(root)),
                            "item": it,
                        }) + "\n")
                        archived_item_keys.add((feedback_id, it.get("id")))
                stamp = datetime.now(UTC).isoformat()
                cmeta, cbody = read_commented(md_file)
                marked = {it.get("id") for it in to_stamp}
                for it in cmeta.get("items", []):
                    if it.get("id") in marked:
                        it["archived_at"] = stamp
                write_preserving_header(md_file, cmeta, cbody)
                archived_items += len(to_append)
                # Deliberately no hot.md append here. The review-level path posts one
                # finding per archived review; doing the same per item would push ~60 lines
                # into a capped "Recent decisions" list that silently evicts its oldest
                # entries — trading a real decision record for rows nothing reads.
                if to_append:
                    print(f"Archived {len(to_append)} item(s) of {feedback_id} "
                          f"→ {arch_file.name}")
                else:
                    print(f"Stamped {len(to_stamp)} already-ledgered item(s) of {feedback_id}")
                continue

            # Refuse re-archive
            if feedback_id in archived_ids:
                msg = f"ERROR: feedback_id={feedback_id} already archived — re-archive refused"
                print(msg, file=sys.stderr)
                errors.append(msg)
                continue

            # Determine archive file from review's created date
            month = _archive_month(str(meta.get("created", "")))
            arch_dir.mkdir(parents=True, exist_ok=True)
            arch_file = arch_dir / f"{month}.jsonl"

            # Build archive row
            row = {
                "feedback_id": feedback_id,
                "agent": meta.get("agent", ""),
                "agent_type": meta.get("agent_type", ""),
                "session_ref": meta.get("session_ref", ""),
                "created": str(meta.get("created", "")),
                "updated_at": str(meta.get("updated_at", "")),
                "summary": meta.get("summary", ""),
                "archived_at": datetime.now(UTC).isoformat(),
                "item_count": len(items),
                "source_file": str(md_file.relative_to(root)),
                # The row IS the record once the markdown is unlinked below. hot.md keeps a
                # deduped, truncated projection; nothing else holds the item bodies.
                "items": items,
                "body": body,
            }

            # Append to archive JSONL
            with arch_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")

            # Track for idempotency within this run
            archived_ids.add(feedback_id)

            # Remove source markdown
            md_file.unlink()

            # Append structured finding(s) to hot.md via the section-aware writer,
            # seeding the skeleton first so a later `engine file decision` (also
            # hot.append) can't crash on a missing "## Recent decisions" header (#49b).
            # A raw open("a") here dumped lines below "## Last updated" and left a
            # skeleton-less hot.md on first archive, breaking First Launch.
            from enginelib.memory import hot as hot_writer
            hot_writer.init()  # idempotent: "exists" when already present
            agent = meta.get("agent", "unknown")
            seen_pairs: set[tuple[str, str]] = set()
            finding_lines: list[str] = []
            for item in items:
                loc = item.get("location", {})
                skill_slug = (
                    (loc.get("skill") if isinstance(loc, dict) else None)
                    or agent
                )
                severity = item.get("severity", "low")
                observation = (item.get("observation") or "").replace("\n", " ")[:120]
                key = (feedback_id, skill_slug)
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)
                finding_lines.append(
                    f"[RESOLVED {feedback_id}] {skill_slug}: {observation} (was {severity})"
                )
            if not finding_lines:
                summary = (meta.get("summary") or "").replace("\n", " ")[:120]
                finding_lines.append(f"[RESOLVED {feedback_id}] {agent}: {summary} (was low)")
            if args.note:
                safe_note = args.note[:200].replace("\n", " ").replace("\r", " ")
                finding_lines.append(f"note ({feedback_id}): {safe_note}")
            # no_compact: don't truncate mid-batch; the next normal append compacts.
            for finding in finding_lines:
                hot_writer.append("recent-decisions", agent, finding, no_compact=True)

            archived_count += 1
            print(f"Archived {feedback_id} → {arch_file.name}")

    if errors:
        # not `e`: the name is bound by an `except ... as e` earlier in this function, and Python
        # deletes it at the end of that block — reusing it here reads as resurrecting a dead name.
        for err in errors:
            print(err, file=sys.stderr)
        return 1

    if archived_count or archived_items:
        # Reconcile the cache: archived items are stamped out of the working set and an
        # archived review's file is gone, but the index still holds their rows until a
        # rebuild. Leaving it stale is how a closed item keeps costing every consumer.
        from feedback_triage import _rebuild_index
        _rebuild_index(root)

    print(f"Done: {archived_count} review(s) archived, {archived_items} item(s) archived.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

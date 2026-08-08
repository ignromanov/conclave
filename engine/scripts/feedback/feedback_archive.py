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
from briefing.paths import repo_root  # noqa: E402

_DONE_STATUSES = {"resolved", "rejected"}


def _load_archived_ids(arch_dir: Path) -> set[str]:
    """Collect all feedback_ids already present in any _archive/*.jsonl file."""
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

    dirs = _review_dirs(fb_root)
    archived_count = 0
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

    print(f"Done: {archived_count} review(s) archived.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

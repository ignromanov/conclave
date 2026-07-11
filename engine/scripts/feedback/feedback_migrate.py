"""feedback_migrate.py — one-shot legacy channel A/B import for spec 086.

CLI: python feedback_migrate.py [--channel-a <journal.jsonl>] [--channel-b <dir>]

Channel A: agent-memory/advisors/feedback/journal.jsonl (JSONL rows)
Channel B: ops/skill-feedback/*/*.md (markdown with frontmatter)

Each legacy record maps to a FeedbackItem with:
  - migrated: true
  - legacy_source: path/id of original
  - evidence: None (migrated flag exempts evidence gate)
  - interpretation: None (not in legacy schema)
  - severity: "blocker" → "critical" (channel A only)

Items are grouped by emitting agent + date into Review files under
ops/feedback/_migrated/. Prints a count summary on stdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from briefing.frontmatter_io import read as fm_read  # noqa: E402
from briefing.frontmatter_io import write as fm_write  # noqa: E402
from briefing.paths import repo_root  # noqa: E402
from feedback.paths import migrated_dir  # noqa: E402

_SEVERITY_MAP = {
    "blocker": "critical",
    "critical": "critical",
    "high": "high",
    "medium": "medium",
    "low": "low",
}

_CATEGORY_TYPE_MAP = {
    "inconsistency": "doc-contradiction",
    "docs-gap": "doc-contradiction",
    "error": "script-defect",
    "naming": "naming-inconsistency",
    "skill-inaccuracy": "skill-inaccuracy",
    "skill-gap": "skill-gap",
    "process-friction": "process-friction",
    "data-access": "data-access",
    "idea": "idea",
}

_DEFAULT_CATEGORY = "process-friction"
_DEFAULT_LAYER = "skill"


def _map_severity(raw: str) -> str:
    return _SEVERITY_MAP.get(raw.lower(), "medium")


def _map_category(raw: str) -> str:
    return _CATEGORY_TYPE_MAP.get(raw.lower(), _DEFAULT_CATEGORY)


def _make_feedback_id(agent: str, ts: str) -> str:
    raw_ts = ts or datetime.now(tz=UTC).isoformat()
    try:
        dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        epoch = int(dt.timestamp())
    except ValueError:
        epoch = 0
    short = hashlib.sha256(f"{agent}:{raw_ts}".encode()).hexdigest()[:6]
    return f"fb-{epoch}-{short}"


def _parse_location_str(loc_str: str) -> dict:
    """Parse 'file.py:42' or 'file.py' into a Location dict."""
    if ":" in loc_str:
        parts = loc_str.rsplit(":", 1)
        try:
            return {"file": parts[0], "line": int(parts[1])}
        except ValueError:
            pass
    return {"file": loc_str}


def _migrate_channel_a(journal_path: Path) -> dict[str, list[dict]]:
    """Read JSONL rows; group items by (advisor, date) → {group_key: [item_dict]}."""
    groups: dict[str, list[dict]] = {}

    for raw_line in journal_path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        advisor = row.get("advisor") or row.get("agent") or "unknown"
        ts = row.get("ts") or row.get("created") or ""
        date_str = ts[:10] if ts else "unknown"
        group_key = f"{advisor}:{date_str}"

        severity_raw = row.get("severity", "medium")
        category_raw = row.get("type") or row.get("scope") or "process-friction"
        location_raw = row.get("location") or row.get("skill") or advisor
        message = row.get("message") or ""
        item_id = row.get("id") or f"legacy-{hashlib.sha256(raw_line.encode()).hexdigest()[:8]}"

        item = {
            "id": item_id,
            "category": _map_category(category_raw),
            "layer": _DEFAULT_LAYER,
            "location": _parse_location_str(location_raw),
            "observation": message,
            "suggested_fix": "Review and address legacy finding.",
            "severity": _map_severity(severity_raw),
            "frequency": "occasional",
            "evidence": None,
            "migrated": True,
            "legacy_source": f"{journal_path.name}#{item_id}",
        }
        groups.setdefault(group_key, []).append(item)

    return groups


def _migrate_channel_b(b_root: Path) -> dict[str, list[dict]]:
    """Walk ops/skill-feedback/*/*.md; group by (emitter, date)."""
    groups: dict[str, list[dict]] = {}

    if not b_root.exists():
        return groups

    for date_dir in sorted(b_root.iterdir()):
        if not date_dir.is_dir():
            continue
        date_str = date_dir.name  # e.g. "2026-05-17"

        for md_file in sorted(date_dir.glob("*.md")):
            try:
                meta, _body = fm_read(md_file)
            except Exception:
                continue

            emitter = meta.get("emitter") or meta.get("agent") or "unknown"
            group_key = f"{emitter}:{date_str}"

            # Build one FeedbackItem from the skill-feedback emission
            emission_id = meta.get("emission_id") or md_file.stem
            severity_raw = meta.get("severity", "low")
            observation_parts = []
            if meta.get("improvisations"):
                improvs = meta["improvisations"]
                if isinstance(improvs, list):
                    observation_parts.append("Improvisations: " + "; ".join(str(i) for i in improvs))
            if meta.get("friction_note"):
                observation_parts.append(str(meta["friction_note"]))
            observation = " | ".join(observation_parts) or f"Skill feedback from {emission_id}"

            suggested_fix = str(meta.get("suggested_fix", "Review and address."))
            skill_id = meta.get("skill_id") or meta.get("skill") or emitter

            item = {
                "id": f"legacy-b-{md_file.stem[:20]}",
                "category": "skill-gap",
                "layer": _DEFAULT_LAYER,
                "location": {"skill": skill_id},
                "observation": observation,
                "suggested_fix": suggested_fix,
                "severity": _map_severity(severity_raw),
                "frequency": "occasional",
                "evidence": None,
                "migrated": True,
                "legacy_source": str(md_file),
            }
            groups.setdefault(group_key, []).append(item)

    return groups


def _write_migrated_reviews(groups: dict[str, list[dict]], out_dir: Path) -> int:
    """Write one Review file per group key; return total item count."""
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0

    for group_key, items in groups.items():
        # Disambiguate collision-prone truncated-stem ids within this review so
        # feedback_triage.py --set can address each item uniquely (#9). The first
        # occurrence keeps the base id; later duplicates get a -N suffix.
        seen_ids: dict[str, int] = {}
        for it in items:
            base = it["id"]
            n = seen_ids.get(base, 0)
            if n:
                it["id"] = f"{base}-{n + 1}"
            seen_ids[base] = n + 1

        parts = group_key.split(":", 1)
        agent = parts[0]
        date_str = parts[1] if len(parts) > 1 else "unknown"
        feedback_id = _make_feedback_id(agent, date_str)
        iso = f"{date_str}T00:00:00Z" if len(date_str) == 10 else datetime.now(tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        filename = f"{agent}-{date_str}-migrated.md"
        out_path = out_dir / filename
        # Avoid overwriting if multiple groups map to same file
        if out_path.exists():
            suffix = feedback_id[-4:]
            out_path = out_dir / f"{agent}-{date_str}-{suffix}-migrated.md"

        meta = {
            "feedback_id": feedback_id,
            "agent": agent,
            "agent_type": "advisor" if not agent.startswith("exec.") else "executor",  # "other" unreachable in one-shot migration
            "session_ref": f"legacy-migration:{group_key}",
            "skill_version": "sha256:legacy000000",
            "created": iso,
            "updated_at": iso,
            "_draft": False,
            "summary": f"Migrated legacy feedback from {agent} ({date_str})",
            "items": items,
            "below_threshold_count": 0,
        }
        fm_write(out_path, meta, "")
        total += len(items)

    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate legacy feedback channels A and B")
    parser.add_argument("--channel-a", type=Path, default=None,
                        help="Path to journal.jsonl (channel A)")
    parser.add_argument("--channel-b", type=Path, default=None,
                        help="Root dir of skill-feedback/* dirs (channel B)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview what would be migrated without writing any files")
    args = parser.parse_args(argv)

    _root = repo_root()
    out_dir = migrated_dir()

    groups: dict[str, list[dict]] = {}

    if args.channel_a and args.channel_a.exists():
        for k, v in _migrate_channel_a(args.channel_a).items():
            groups.setdefault(k, []).extend(v)
    elif args.channel_a:
        print(f"WARNING: channel-a path not found: {args.channel_a}", file=sys.stderr)

    if args.channel_b and args.channel_b.exists():
        for k, v in _migrate_channel_b(args.channel_b).items():
            groups.setdefault(k, []).extend(v)
    elif args.channel_b:
        print(f"WARNING: channel-b path not found: {args.channel_b}", file=sys.stderr)

    if not groups:
        print("migrated: 0 items (no input sources found)")
        return 0

    total_items = sum(len(v) for v in groups.values())
    total_files = len(groups)

    if args.dry_run:
        print(f"dry-run: would migrate {total_items} items into {total_files} review files → {out_dir}")
        return 0

    total = _write_migrated_reviews(groups, out_dir)
    print(f"migrated: {total} items into {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

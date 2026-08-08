"""feedback_emit.py — scaffold a review file for spec 086.

CLI: python feedback_emit.py --agent <id> --agent-type <advisor|executor|other>
     --session-ref <id> --skill-version sha256:<hex> [--no-op]

Writes ops/feedback/<today>/<agent>-<session>.md with _draft: true and empty items.
Prints the written path to stdout.

CLI (finalize): python feedback_emit.py --finalize <path>
     Validates the filled review against the schema and flips _draft:false only
     if it passes. The sanctioned way to finalize — never hand-edit _draft.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys

# Interpreter floor, enforced before the first thing that can fail below it — here,
# `from datetime import UTC` on the next line (UTC was added in 3.11), which is the very
# measurement the floor comes from. /conclave:feedback, /conclave:done and
# feedback-protocol.md launch this file directly.
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

from pydantic import ValidationError  # noqa: E402

from briefing.frontmatter_io import read_commented, write  # noqa: E402
from feedback.paths import review_dir  # noqa: E402
from feedback.schema import Review  # noqa: E402

_DATA_CLASSIFICATION_HEADER = """\
<!--
DATA CLASSIFICATION WARNING — DO NOT include in observation/evidence:
- wallet addresses (0x[a-fA-F0-9]{40})
- private keys / tx-hashes (0x[a-fA-F0-9]{64})
- GH tokens (gh[ps]_[A-Za-z0-9_]{36,})
- RPC URLs containing alchemy|infura|quicknode|drpc
- invoice URL fragments (#N4Ig, #H4sI)
- ?og= params
- social URLs (t.me|twitter.com|x.com|farcaster.xyz|warpcast.com)
- IP addresses, email addresses
- paths under the knowledge wiki outside _bridges/
-->
"""


def write_preserving_header(path: Path, meta: dict, body: str) -> None:
    """Write frontmatter+body, re-prepending the leading HTML comment header.

    briefing.frontmatter_io.write emits only the ---fm---body envelope, and
    read_commented strips the leading DATA CLASSIFICATION comment. Any caller
    that round-trips a review file (emit --finalize, triage --set) must preserve
    that header: capture it from the on-disk file before writing, re-prepend after.
    """
    raw = path.read_text(encoding="utf-8") if path.exists() else ""
    header = ""
    if raw.lstrip().startswith("<!--"):
        header = raw[: raw.index("-->") + 3].lstrip() + "\n"
    write(path, meta, body, header=header)


def _make_feedback_id(agent: str, session_ref: str, now: datetime) -> str:
    ts = int(now.timestamp())
    short = hashlib.sha256(f"{agent}:{session_ref}:{ts}".encode()).hexdigest()[:6]
    return f"fb-{ts}-{short}"


def _reopen_matches(root: Path, meta: dict) -> list[str]:
    """Stamp re-occurred + reopened_from on any new item whose fingerprint matches a
    RESOLVED item (live index or archived), unless a live non-terminal duplicate
    already exists at that fingerprint (an ordinary open dup is not a regression).

    Makes Constitution VI's reversal path real (093 Component E, closes #89). Never
    resurrects the archived record — the recurrence is recorded on THIS new item, and
    the archive itself is left untouched. Archive shards store whole reviews
    ({items:[...]}); the fingerprint is recomputed per item exactly as feedback_index
    does.

    Abstains on a file-level-only match (#59). Without `location.section` the fingerprint
    buckets an entire file+category, so any two script-defects in the same file collide
    and the stamp asserts a regression that never happened — and 093 Component E reads
    `re-occurred` as proof an earlier fix failed. Only the NEW item needs checking:
    section is part of the hash, so if it has one, a match proves the resolved side named
    the same section.

    Returns the abstention notes, for the caller to surface.
    """
    import json

    from feedback.schema import fingerprint
    fb_root = root / "ops" / "feedback"
    resolved_fp: dict[str, str] = {}
    live_nonterminal_fp: set[str] = set()

    idx = fb_root / "_index" / "index.jsonl"
    if idx.is_file():
        for line in idx.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            fp = r.get("fingerprint")
            if not fp:
                continue
            if r.get("status") == "resolved":
                resolved_fp.setdefault(fp, f"{r.get('feedback_id')}:{r.get('item_id')}")
            elif r.get("status") in ("open", "accepted", "in_progress", "re-occurred"):
                live_nonterminal_fp.add(fp)

    arch_dir = fb_root / "_archive"
    if arch_dir.is_dir():
        for shard in sorted(arch_dir.glob("*.jsonl")):
            for line in shard.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                review = json.loads(line)
                for item in review.get("items", []):
                    if item.get("status") != "resolved":
                        continue
                    fp = fingerprint(item.get("location", {}), item.get("category", ""))
                    resolved_fp.setdefault(fp, f"{review.get('feedback_id')}:{item.get('id')}")

    abstained: list[str] = []
    for item in meta.get("items", []):
        loc = item.get("location") or {}
        fp = fingerprint(loc, item.get("category", ""))
        if fp not in resolved_fp or fp in live_nonterminal_fp:
            continue
        if not str(loc.get("section") or "").strip():
            abstained.append(
                f"{item.get('id')}: fingerprint matches resolved {resolved_fp[fp]}, but "
                f"location carries no `section` — a file-level match cannot tell a "
                f"regression from a different defect in the same file. Left as-is; add "
                f"`location.section` if this really is the same finding recurring."
            )
            continue
        item["status"] = "re-occurred"
        item["reopened_from"] = resolved_fp[fp]
    return abstained


def _finalize(path: Path) -> int:
    """Validate a filled review against the schema, then flip _draft:false.

    The only sanctioned path to finalize a review. If the file fails schema
    validation the flip is refused and _draft is left untouched, so a malformed
    review can never reach the triage index (which would hard-abort the cadence).
    """
    if not path.exists():
        print(f"ERROR: file not found: {path}", file=sys.stderr)
        return 1

    meta, body = read_commented(path)

    # 093 E: reopen fingerprint-matched regressions BEFORE validation so the stamped
    # status/provenance are validated too.
    from briefing.paths import repo_root
    for note in _reopen_matches(repo_root(), meta):
        print(f"  NOTE: reopen abstained — {note}", file=sys.stderr)

    try:
        Review.model_validate(dict(meta))
    except ValidationError as exc:
        print(f"REJECT {path}: schema-invalid — _draft left unchanged.\n{exc}",
              file=sys.stderr)
        return 1

    if meta.get("_draft") is False:
        print(f"{path}: already finalized (_draft already false)")
        return 0

    meta["_draft"] = False
    meta["updated_at"] = datetime.now(tz=UTC).isoformat()
    write_preserving_header(path, meta, body)

    print(f"FINALIZED {path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scaffold or finalize a feedback review file")
    parser.add_argument("--agent")
    parser.add_argument("--agent-type", choices=["advisor", "executor", "other"])
    parser.add_argument("--session-ref")
    parser.add_argument("--skill-version")
    parser.add_argument("--no-op", action="store_true", default=False)
    parser.add_argument("--finalize", metavar="PATH",
                        help="Validate a filled review against the schema and flip _draft:false")
    args = parser.parse_args(argv)

    if args.finalize:
        return _finalize(Path(args.finalize))

    # Scaffold mode — the four creation args are required here (not at the parser
    # level, so --finalize can run standalone).
    missing = [name for name in ("agent", "agent_type", "session_ref", "skill_version")
               if getattr(args, name) is None]
    if missing:
        parser.error("the following arguments are required: "
                     + ", ".join("--" + m.replace("_", "-") for m in missing))

    now = datetime.now(tz=UTC)
    today = now.date().isoformat()
    feedback_id = _make_feedback_id(args.agent, args.session_ref, now)

    out_dir = review_dir(today)

    # Slugify session_ref: take last path component, replace / with -
    session_slug = args.session_ref.replace("/", "-").replace("_", "-")
    filename = f"{args.agent}-{session_slug}.md"
    out_path = out_dir / filename

    # If a file with this name already exists, append full 6-char suffix to avoid collision
    if out_path.exists():
        suffix = feedback_id[-6:]
        filename = f"{args.agent}-{session_slug}-{suffix}.md"
        out_path = out_dir / filename
        if out_path.exists():
            raise RuntimeError(f"collision: {out_path} already exists")

    iso = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    body = """\
## Review items

Fill in `items` in the frontmatter above. Each item needs:
- id, category, layer, location
- observation, suggested_fix
- severity, frequency, evidence
- (optional) interpretation

Field-type rules — a mismatch rejects the WHOLE review at finalize:
- id: a STRING (quote it: `id: "i1"`), not a bare int — YAML `id: 1` is an int and fails.
- location.skill: a skill-path slug matching `team.*` / `exec.*` / `workflow.*` / `util.*`
  (e.g. `team.sage-cto`), NOT a bare agent name like `sage-cto`.

Closed enums — any other value is rejected at finalize:
- category: script-defect · doc-contradiction · naming-inconsistency · skill-inaccuracy · skill-gap · process-friction · data-access · idea
- layer: infra · skill · contract · memory · workflow
- severity: low · medium · high · critical
- frequency: first-time · occasional · every-dispatch
- location: typed object — {file: "path"} | {skill: "team.x"} | {section: "heading"} (≥1 of file/skill/section)

When done, do NOT hand-edit `_draft`. Finalize via:
  uv run --project engine/scripts \\
    python engine/scripts/feedback/feedback_emit.py --finalize <this-file>
It validates the schema and flips `_draft: false` only if valid.
"""

    meta: dict = {
        "feedback_id": feedback_id,
        "agent": args.agent,
        "agent_type": args.agent_type,
        "session_ref": args.session_ref,
        "skill_version": args.skill_version,
        "created": iso,
        "updated_at": iso,
        "_draft": True,
        "summary": "TODO: one-sentence summary of this session",
        "items": [],
        "below_threshold_count": 0,
        "trace_ref": os.environ.get("CLAUDE_SESSION_ID") or None,
        "parent_session_ref": os.environ.get("CLAUDE_PARENT_SESSION") or None,
    }
    if args.no_op:
        meta["no_op"] = True

    out_dir.mkdir(parents=True, exist_ok=True)
    # Single atomic write — header prepended inside snapshot_write (no truncation window).
    write(out_path, meta, body, header=_DATA_CLASSIFICATION_HEADER)

    print(str(out_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())

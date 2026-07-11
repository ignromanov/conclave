"""scans/closeability.py — section: Closeability hints (#13).

For each open issue labelled `agent-infra`, probe whether the relevant
file exists in the repo and whether it is within the 20-line hard cap.

One-line probe per issue — not a replacement for the full queue section.
Surfaced as a short advisory block so the advisor can close stale issues
before the session starts.

Exposes: build(ctx: ScanCtx) -> str
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from briefing.scans import ScanCtx

_PLACEHOLDER = "_(no agent-infra closeability hints)_"

# Must match _gh_cache.py — reuse the same fence regex.
_JSON_FENCE_RE = re.compile(r"^```json\s*\n(.*?)\n```", re.DOTALL | re.MULTILINE)

# Soft/hard line-cap thresholds (spec 084 A5, same as validate.py).
_LINE_CAP_WARN = 10
_LINE_CAP_HARD = 20

# Labels that mark agent-infra issues.
_AGENT_INFRA_LABEL = "agent-infra"


def _read_items(cache_path: Path, advisor: str) -> list[dict]:
    """Return raw JSON items from the gh-cache snapshot, or [] on any failure."""
    if not cache_path.is_file():
        return []
    text = cache_path.read_text(encoding="utf-8")
    m = _JSON_FENCE_RE.search(text)
    if not m:
        return []
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return []


def _is_agent_infra(item: dict) -> bool:
    return any(lbl.get("name") == _AGENT_INFRA_LABEL for lbl in item.get("labels", []))


def _probe_file(repo_root: Path, issue_title: str) -> str:
    """Return a one-line hint about the most-likely file for this issue.

    Heuristic: look for any .md file under `.claude/` or `agent-memory/`
    whose stem appears in the issue title (case-insensitive, slug-normalised).
    Falls back to a generic "no file found" note.
    """
    # Normalise title to a slug-like token for matching.
    slug = re.sub(r"[^a-z0-9]+", "-", issue_title.lower()).strip("-")
    tokens = [t for t in slug.split("-") if len(t) > 3]

    # Search candidates under agent infra directories.
    search_roots = [
        repo_root / ".claude",
        repo_root / "agent-memory",
    ]
    candidates: list[Path] = []
    for root in search_roots:
        if root.is_dir():
            candidates.extend(root.rglob("*.md"))

    # Score each candidate by how many tokens from the title it contains.
    best: tuple[int, Path | None] = (0, None)
    for path in candidates:
        stem = path.stem.lower()
        score = sum(1 for t in tokens if t in stem)
        if score > best[0]:
            best = (score, path)

    matched_path, line_hint = best[1], ""
    if matched_path and best[0] > 0:
        try:
            line_count = len(matched_path.read_text(encoding="utf-8").splitlines())
        except OSError:
            line_count = -1

        rel = matched_path.relative_to(repo_root)
        if line_count < 0:
            line_hint = f"`{rel}` (unreadable)"
        elif line_count >= _LINE_CAP_HARD:
            line_hint = f"`{rel}` **OVER cap** ({line_count} lines ≥ {_LINE_CAP_HARD})"
        elif line_count >= _LINE_CAP_WARN:
            line_hint = f"`{rel}` near cap ({line_count} lines ≥ {_LINE_CAP_WARN})"
        else:
            line_hint = f"`{rel}` ok ({line_count} lines)"
    else:
        line_hint = "no matching file found → may be closeable"

    return line_hint


def build(ctx: ScanCtx) -> str:
    """Return a markdown list of closeability hints for agent-infra issues.

    For each open issue labelled `agent-infra`, one line:
        - <repo>#<num> "<title>" — <file probe result>

    Placeholder when there are no agent-infra issues.
    """
    cache_path = ctx.gh_cache_dir / f"{ctx.advisor}.md"
    items = _read_items(cache_path, ctx.advisor)

    infra_items = [it for it in items if _is_agent_infra(it)]
    if not infra_items:
        return _PLACEHOLDER

    lines: list[str] = []
    for item in infra_items:
        num = item.get("number", "?")
        title = item.get("title", "")
        repo_name = (item.get("repository") or {}).get("name", "")
        issue_ref = f"{repo_name}#{num}" if repo_name else f"#{num}"
        hint = _probe_file(ctx.repo_root, title)
        lines.append(f'- {issue_ref} "{title}" — {hint}')

    return "\n".join(lines)

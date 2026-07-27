"""render.py — load briefing.md template, substitute placeholders, atomic write.

Port of briefing-build.sh lines 335-421 (render section).

Placeholder format: {{key}}
Multi-line-safe: values may contain newlines.
Atomic write: tmp file + os.replace().

hot.md is NOT embedded in the briefing (AC8 — de-dup). The briefing body
references hot.md by path; team.start loads it once separately so it is
never duplicated across all 5 advisor briefings.
"""
from __future__ import annotations

import os
import re
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from briefing.paths import hot_md_path, templates_dir
from briefing.scans import (
    ScanCtx,
    closeability,
    code_repo,
    current_work,
    decisions,
    drift,
    identity,
    interrupted,
    mentions,
    owed,
    p0,
    project_digest,
    project_state,
    queue,
    roadmap,
    sessions,
    spec_progress,
)

# Regex for {{key}} placeholders — key is alphanumeric + underscore.
_PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")

# hot.md sections to include (matches briefing-build.sh awk filter).
_HOT_INCLUDE_SECTIONS = {"Now", "Recent decisions", "Watch"}


def _generated_at() -> str:
    """Return current timestamp in ISO-8601 with offset, matching `date +%Y-%m-%dT%H:%M:%S%z`."""
    now = datetime.now(tz=UTC).astimezone()
    return now.strftime("%Y-%m-%dT%H:%M:%S%z")


def _substitute(template: str, values: dict[str, str]) -> str:
    """Replace all {{key}} occurrences with their values.

    Multi-line-safe: re.sub with a function replaces each match individually,
    so newlines in values are preserved verbatim.
    """

    def replacer(m: re.Match) -> str:
        key = m.group(1)
        return values.get(key, m.group(0))

    return _PLACEHOLDER_RE.sub(replacer, template)


def _hot_section(hot_path: Path) -> str:
    """Extract actionable sections from hot.md.

    Mirrors bash awk:
      /^## / { include = ($0 ~ /^## (Now|Recent decisions|Watch)$/) ? 1 : 0 }
      include { print }

    Returns the section content (may be empty if hot.md is absent/empty).
    """
    if not hot_path.is_file():
        return "(hot.md not initialized — run engine memory hot-init)"

    text = hot_path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=False)

    include = False
    out: list[str] = []
    for line in lines:
        if line.startswith("## "):
            section_name = line[3:].strip()
            include = section_name in _HOT_INCLUDE_SECTIONS
        if include:
            out.append(line)

    return "\n".join(out)


def build(ctx: ScanCtx, out_path: Path) -> None:
    """Render briefing and write atomically to out_path, only if it changed.

    Steps:
    1. Run all scans.
    2. Load template.
    3. Substitute placeholders + append the hot.md footer.
    4. Write to tmp file + os.replace() — skipped if content is unchanged
       from what's already on disk (#14 — build-and-compare).

    hot.md content is NOT embedded (AC8). The briefing references it by path;
    team.start loads it separately.
    """
    values: dict[str, str] = {
        "advisor": ctx.advisor,
        "generated_at": _generated_at(),
        "who_i_am": identity.build(ctx),
        "project_state": project_state.build(ctx),
        "recent_decisions": decisions.build(ctx),
        "my_queue": queue.build(ctx),
        "p0_blockers": p0.build(ctx),
        "last_sessions": sessions.build(ctx),
        "mentions": mentions.build(ctx),
        "current_work": current_work.build(ctx),
        "spec_progress": spec_progress.build(ctx),
        "owed": owed.build(ctx),
        "roadmap": roadmap.build(ctx),
        "drift": drift.build(ctx),
        "interrupted": interrupted.build(ctx),
        "project_digest": project_digest.build(ctx),
        "closeability": closeability.build(ctx),
        "code_repo": code_repo.build(ctx),
    }

    content = render_content(values)
    write_if_changed(content, out_path)


def render_content(values: dict[str, str]) -> str:
    """Substitute placeholders from *values* and append the hot.md footer.

    Returns the exact text a write would produce — body + footer combined —
    without touching disk, so callers can compare it against what's already
    there before deciding whether a write is needed (#14 — build-and-compare).

    ``values`` must include ``advisor`` and ``generated_at``; callers that
    build the dict themselves (e.g. the CLI) call this directly so that scan
    timing can be measured per-step before the render step begins.
    """
    tpl_path = templates_dir() / "briefing.md"
    if not tpl_path.is_file():
        raise FileNotFoundError(f"render: template not found: {tpl_path}")

    if "generated_at" not in values:
        values = {**values, "generated_at": _generated_at()}

    check_token_cap(values)

    template = tpl_path.read_text(encoding="utf-8")
    rendered = _substitute(template, values)
    return rendered + _hot_footer()


def _hot_footer() -> str:
    """The hot.md reference footer appended after the rendered body (AC8 — no
    content embedded, path reference only)."""
    hot_path = hot_md_path()
    return f"\n> **Live context**: see `{hot_path}` (loaded by team.start)\n"


# generated_at is stamped as `<!-- generated_at: <value> -->` (render.py:_generated_at,
# briefing.md template line 3). Matched by prefix rather than a fixed line index, so
# comparison stays correct even if the template reflows and the stamp moves.
_GENERATED_AT_PREFIX = "<!-- generated_at:"


def _normalize_for_compare(content: str) -> str:
    """Blank the generated_at stamp's value so two renders with identical inputs
    compare equal despite the timestamp always differing."""
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith(_GENERATED_AT_PREFIX):
            lines[i] = _GENERATED_AT_PREFIX + " -->"
            break
    return "\n".join(lines)


def write_if_changed(content: str, out_path: Path) -> bool:
    """Atomically write *content* to *out_path* unless it's unchanged from disk.

    Comparison ignores the generated_at stamp (see _normalize_for_compare), so a
    rebuild with identical inputs is a true no-op — it neither touches the file
    nor its mtime. Returns True if written, False if left alone.
    """
    if out_path.is_file():
        existing = out_path.read_text(encoding="utf-8")
        if _normalize_for_compare(existing) == _normalize_for_compare(content):
            return False

    # Atomic write: tmp in same dir so os.replace() is a rename. Body and footer are
    # already combined into one `content` string, so there is no window where the
    # file on disk has the body but not the footer.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=out_path.parent, prefix=".briefing-tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp_path, out_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
    return True


# Token-cap constants — one token ≈ 4 chars (GPT/Claude approximation).
# Cap set at 6000: real briefings peak at ~4,800 tokens (kai-cto); 6000 gives
# ~25% growth headroom so the warning fires only on genuine bloat, not routine use.
_CHARS_PER_TOKEN = 4
_TOKEN_CAP = 6_000


def check_token_cap(values: dict[str, str]) -> None:
    """Warn to stderr if the briefing body exceeds _TOKEN_CAP tokens.

    Counts tokens for all placeholder values except 'generated_at' and
    'advisor' (metadata, not content). hot.md is excluded per spec AC7
    (cap applies to the static briefing body only).
    """
    _EXCLUDE = {"generated_at", "advisor"}
    total_chars = sum(
        len(v) for k, v in values.items() if k not in _EXCLUDE
    )
    total_tokens = total_chars // _CHARS_PER_TOKEN
    if total_tokens > _TOKEN_CAP:
        import sys
        print(
            f"[briefing] WARNING: briefing body ~{total_tokens} tokens "
            f"(cap={_TOKEN_CAP}, excl. hot.md). "
            "Consider trimming personality-eager.md or scan outputs.",
            file=sys.stderr,
        )

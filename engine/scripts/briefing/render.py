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
    """Render briefing and write atomically to out_path.

    Steps:
    1. Run all scans.
    2. Load template.
    3. Substitute placeholders.
    4. Write to tmp file + os.replace().

    hot.md is NOT appended (AC8). The briefing references it by path;
    team.start loads it separately.
    """
    tpl_path = templates_dir() / "briefing.md"
    if not tpl_path.is_file():
        raise FileNotFoundError(f"render: template not found: {tpl_path}")

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

    write_body(values, out_path)
    append_hot(out_path)


def write_body(values: dict[str, str], out_path: Path) -> None:
    """Substitute placeholders from *values* and atomically write *out_path*.

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

    # Atomic write: tmp in same dir so os.replace() is a rename.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=out_path.parent, prefix=".briefing-tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(rendered)
        os.replace(tmp_path, out_path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def append_hot(out_path: Path) -> None:
    """Append a hot.md reference footer to *out_path* (AC8 — no content embedded).

    The briefing no longer embeds hot.md sections. Instead it records the path
    so team.start can load hot.md once (not once per advisor briefing).
    """
    hot_path = hot_md_path()
    with out_path.open("a", encoding="utf-8") as fh:
        fh.write(f"\n> **Live context**: see `{hot_path}` (loaded by team.start)\n")


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

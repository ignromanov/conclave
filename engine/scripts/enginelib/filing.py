"""filing.py — file advisor decision/handoff/session documents.

Ports of file-decision.sh, file-handoff.sh, close-session.sh, emission-gate.sh.

I/O-free of stdout/argparse/sys.exit. File I/O and briefing import are permitted.
Briefing regen stdout is suppressed at the fd level (mirrors mention.create).

Contracts:
    file_decision(opts: DecisionOpts) -> str
    file_handoff(opts: HandoffOpts) -> str
    close_session(opts: CloseSessionOpts) -> str
    emission_gate(ai_root, advisor, session_id, today) -> str | None
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from enginelib import advisors, paths, template
from enginelib.snapshot import snapshot_write

_log = logging.getLogger(__name__)


def _dedupe_slug(who: str, slug: str) -> str:
    """Strip a leading '<who>-' from slug so '{date}-{who}-{slug}' filenames don't
    stutter (#52): by=sage-cto + slug=sage-cto-first-launch → 'sage-cto-first-launch',
    not '…-sage-cto-sage-cto-first-launch.md'. No-op when slug doesn't repeat who."""
    prefix = f"{who}-"
    return slug[len(prefix):] if who and slug.startswith(prefix) else slug


@dataclass
class DecisionOpts:
    slug: str
    by: str
    date: str
    body_file: str
    meeting: str = ""
    session: str = ""
    supersedes: str = ""
    tags: str = ""
    status: str = "active"
    cross_cutting: bool = False


def file_decision(opts: DecisionOpts) -> str:
    """File an advisor decision document and return its path."""
    # 1. Validate required args
    missing = [
        label
        for label, val in (
            ("--slug", opts.slug),
            ("--by", opts.by),
            ("--date", opts.date),
            ("--body-file", opts.body_file),
        )
        if not val
    ]
    if missing:
        raise ValueError(f"required argument(s) missing: {' '.join(missing)}")

    body_path = Path(opts.body_file)
    if not body_path.is_file():
        raise ValueError(f"--body-file not found: {opts.body_file}")

    # 2. Validate canonical advisor
    if not advisors.is_canonical_advisor(opts.by):
        known = ", ".join(advisors.canonical_advisors())
        raise ValueError(
            f"--by \"{opts.by}\" is not a canonical advisor.\n"
            f"Known advisors: {known}"
        )

    # 3. Resolve output path (dedupe a stuttering advisor-prefixed slug — #52)
    opts.slug = _dedupe_slug(opts.by, opts.slug)
    dec_dir = paths.decisions_dir()
    paths.ensure_dir(dec_dir)
    out_file = dec_dir / f"{opts.date}-{opts.by}-{opts.slug}.md"

    # 4. Load template and body
    tpl = paths.templates_dir() / "decision.md"
    if not tpl.exists():
        raise ValueError(f"template not found: {tpl}")
    body_text = body_path.read_text(encoding="utf-8")

    # 5. Render (dict-form: "from" is not a key here but kept consistent with mention)
    rendered = template.render(tpl, {
        "slug": opts.slug,
        "date": opts.date,
        "by": opts.by,
        "meeting": opts.meeting,
        "session": opts.session,
        "supersedes": opts.supersedes,
        "status": opts.status,
        "tags": opts.tags,
        "body": body_text,
    })

    # 6. Atomic write with exactly one trailing newline (idempotent: overwrites same date+by+slug)
    if not rendered.endswith("\n"):
        rendered += "\n"
    snapshot_write(out_file, rendered)

    # 7. Hot append (guarded, deferred — enginelib.memory.hot built in 3D.3;
    #    import fails silently until then, faithful to bash best-effort/non-fatal contract)
    try:
        from enginelib.memory import hot  # noqa: F401
        hot.append(
            "recent-decisions",
            opts.by,
            f"{opts.slug} → decisions/{opts.date}-{opts.by}-{opts.slug}.md",
        )
    except (ImportError, OSError):
        _log.debug("hot.append recent-decisions skipped (expected)", exc_info=True)
    except Exception:
        _log.warning("hot.append recent-decisions failed unexpectedly", exc_info=True)

    # 8. Cross-ref appenders (idempotent)
    _append_xref(
        paths.repo_root() / "ops" / "meetings" / f"{opts.meeting}.md",
        f"../agent-memory/advisors/decisions/{opts.date}-{opts.by}-{opts.slug}.md",
        opts.date, opts.by, opts.slug,
    ) if opts.meeting else None

    _append_xref(
        paths.sessions_dir() / f"{opts.session}.md",
        f"../decisions/{opts.date}-{opts.by}-{opts.slug}.md",
        opts.date, opts.by, opts.slug,
    ) if opts.session else None

    # 9. --cross-cutting: copy to ops/decisions/{date}-{slug}.md (WITHOUT by)
    if opts.cross_cutting:
        ops_dec = paths.repo_root() / "ops" / "decisions"
        paths.ensure_dir(ops_dec)
        ops_out = ops_dec / f"{opts.date}-{opts.slug}.md"
        ops_rendered = rendered if rendered.endswith("\n") else rendered + "\n"
        snapshot_write(ops_out, ops_rendered)

    # 10. Briefing regen (best-effort, non-fatal, stdout-suppressed at fd level)
    try:
        import os as _os
        import sys as _sys

        from briefing.regen import regen_advisor
        _sys.stdout.flush()
        _devnull = _os.open(_os.devnull, _os.O_WRONLY)
        _saved = _os.dup(1)
        _os.dup2(_devnull, 1)
        _os.close(_devnull)
        try:
            regen_advisor(opts.by)
        finally:
            _sys.stdout.flush()
            _os.dup2(_saved, 1)
            _os.close(_saved)
    except (ImportError, OSError):
        _log.debug("briefing regen for decision author skipped (expected)", exc_info=True)
    except Exception:
        _log.warning("briefing regen for decision author failed unexpectedly", exc_info=True)

    return str(out_file)


@dataclass
class HandoffOpts:
    frm: str
    to: str
    date: str
    priority: str
    title: str
    slug: str
    body_file: str
    policy: str = ""
    gh_issue: str = ""


def file_handoff(opts: HandoffOpts) -> str:
    """File a narrative handoff document (Pattern A, no YAML) and return its path."""
    # 1. Validate required args
    missing = [
        label
        for label, val in (
            ("--from", opts.frm),
            ("--to", opts.to),
            ("--date", opts.date),
            ("--priority", opts.priority),
            ("--title", opts.title),
            ("--slug", opts.slug),
            ("--body-file", opts.body_file),
        )
        if not val
    ]
    if missing:
        raise ValueError(f"required argument(s) missing: {' '.join(missing)}")

    body_path = Path(opts.body_file)
    if not body_path.is_file():
        raise ValueError(f"--body-file not found: {opts.body_file}")

    # 2. Validate canonical advisor names for both from and to
    for arg_name, arg_val in (("--from", opts.frm), ("--to", opts.to)):
        if not advisors.is_canonical_advisor(arg_val):
            known = ", ".join(advisors.canonical_advisors())
            raise ValueError(
                f"{arg_name} \"{arg_val}\" is not a canonical advisor.\n"
                f"Known advisors: {known}"
            )

    # 3. Conditional meta lines
    policy_line = f"> **Policy**: `{opts.policy}`" if opts.policy else ""
    gh_issue_line = f"> **GH Issue**: {opts.gh_issue}" if opts.gh_issue else ""

    # 4. Resolve output path (dedupe a stuttering advisor-prefixed slug — #52)
    opts.slug = _dedupe_slug(opts.frm, opts.slug)
    dest = paths.handoffs_dir()
    paths.ensure_dir(dest)
    out_file = dest / f"{opts.date}-{opts.frm}-{opts.slug}.md"

    # 5. Load template and body
    tpl = paths.templates_dir() / "handoff.md"
    if not tpl.exists():
        raise ValueError(f"template not found: {tpl}")
    body_text = body_path.read_text(encoding="utf-8")

    # 6. Render via dict-form ("from" is a dict key)
    rendered = template.render(tpl, {
        "title": opts.title,
        "from": opts.frm,
        "to": opts.to,
        "date": opts.date,
        "priority": opts.priority,
        "policy_line": policy_line,
        "gh_issue_line": gh_issue_line,
        "body": body_text,
    })

    # 7. Atomic write with exactly one trailing newline
    if not rendered.endswith("\n"):
        rendered += "\n"
    snapshot_write(out_file, rendered)

    return str(out_file)


@dataclass
class CloseSessionOpts:
    advisor: str
    slug: str
    date: str
    body_file: str
    goal: str = ""
    followups_file: str = ""
    decisions_csv: str = ""
    issues_csv: str = ""
    mentions_csv: str = ""
    handoff_file: str = ""
    handoff_to: str = ""
    handoff_priority: str = ""
    handoff_title: str = ""
    handoff_slug: str = ""
    duration_estimate: str = ""
    reflexion: str = ""


def close_session(opts: CloseSessionOpts) -> str:
    """Close an advisor session: write session doc, resolve mentions, file handoff.

    Port of close-session.sh. Steps follow the bash script order exactly.
    """
    # 1. Validate required args
    missing = [
        label
        for label, val in (
            ("--advisor", opts.advisor),
            ("--slug", opts.slug),
            ("--date", opts.date),
            ("--body-file", opts.body_file),
        )
        if not val
    ]
    if missing:
        raise ValueError(f"required argument(s) missing: {' '.join(missing)}")

    # 2. Validate body_file exists
    body_path = Path(opts.body_file)
    if not body_path.is_file():
        raise ValueError(f"--body-file not found: {opts.body_file}")

    # 3. Validate canonical advisor
    if not advisors.is_canonical_advisor(opts.advisor):
        known = ", ".join(advisors.canonical_advisors())
        raise ValueError(
            f'--advisor "{opts.advisor}" is not canonical.\n'
            f"Known advisors: {known}"
        )

    # Dedupe a stuttering advisor-prefixed slug before it feeds both the
    # frontmatter slug and the filename (#52).
    opts.slug = _dedupe_slug(opts.advisor, opts.slug)

    # 4. Validate handoff_to if set (independent of handoff_file)
    if opts.handoff_to and not advisors.is_canonical_advisor(opts.handoff_to):
        known = ", ".join(advisors.canonical_advisors())
        raise ValueError(
            f'--handoff-to "{opts.handoff_to}" is not canonical.\n'
            f"Known advisors: {known}"
        )

    # 5. Validate followups_file exists if set
    if opts.followups_file and not Path(opts.followups_file).is_file():
        raise ValueError(f"--followups-file not found: {opts.followups_file}")

    # 6. Validate handoff_file and its 4 companions if set
    if opts.handoff_file:
        if not Path(opts.handoff_file).is_file():
            raise ValueError(f"--handoff-file not found: {opts.handoff_file}")
        handoff_missing = [
            label
            for label, val in (
                ("--handoff-to", opts.handoff_to),
                ("--handoff-priority", opts.handoff_priority),
                ("--handoff-title", opts.handoff_title),
                ("--handoff-slug", opts.handoff_slug),
            )
            if not val
        ]
        if handoff_missing:
            raise ValueError(
                f"handoff required argument(s) missing: {' '.join(handoff_missing)}"
            )

    # 7. Pre-validate decision slugs: {date}-{advisor}-{slug}.md must exist
    if opts.decisions_csv:
        dec_dir = paths.decisions_dir()
        for d in opts.decisions_csv.split(","):
            d = d.strip()
            if not d:
                continue
            expected = dec_dir / f"{opts.date}-{opts.advisor}-{d}.md"
            if not expected.is_file():
                raise ValueError(f"decision not found: {d} (expected {expected})")

    # 8. Resolve mentions in-process (let exceptions propagate)
    resolved_ids: list[str] = []
    if opts.mentions_csv:
        from enginelib import mention as _mention_mod
        for mid in opts.mentions_csv.split(","):
            mid = mid.strip()
            if not mid:
                continue
            _mention_mod.resolve(mid, by=opts.advisor)
            resolved_ids.append(mid)

    # 9. Read body and followups text
    body_text = body_path.read_text(encoding="utf-8")
    followups_text = ""
    if opts.followups_file:
        followups_text = Path(opts.followups_file).read_text(encoding="utf-8")

    # 10. Build list values: empty csv → "[]", else → "[<csv>]"
    def _as_list(csv: str) -> str:
        return "[]" if not csv else f"[{csv}]"

    decisions_val = _as_list(opts.decisions_csv)
    issues_val = _as_list(opts.issues_csv)
    resolved_ids_csv = ",".join(resolved_ids)
    mentions_val = _as_list(resolved_ids_csv)

    # 11. handoff_val = handoff_slug if handoff_file set, else ""
    handoff_val = opts.handoff_slug if opts.handoff_file else ""

    # 12. reflexion_val: default to EM DASH (U+2014) if not provided
    reflexion_val = opts.reflexion or "—"

    # 13. Load template and render
    tpl = paths.templates_dir() / "session.md"
    if not tpl.exists():
        raise ValueError(f"template not found: {tpl}")
    rendered = template.render(tpl, {
        "advisor": opts.advisor,
        "date": opts.date,
        "slug": opts.slug,
        "decisions": decisions_val,
        "issues": issues_val,
        "handoff": handoff_val,
        "mentions_resolved": mentions_val,
        "duration_estimate": opts.duration_estimate,
        "reflexion": reflexion_val,
        "goal": opts.goal,
        "body": body_text,
        "followups": followups_text,
    })

    # 14. Atomic write: sessions_dir()/{date}-{advisor}-{slug}.md
    sess_dir = paths.sessions_dir()
    paths.ensure_dir(sess_dir)
    out_file = sess_dir / f"{opts.date}-{opts.advisor}-{opts.slug}.md"
    if not rendered.endswith("\n"):
        rendered += "\n"
    snapshot_write(out_file, rendered)

    # 15. Hot append (best-effort, guarded)
    try:
        from enginelib.memory import hot
        goal_line = opts.goal or "(no goal stated)"
        hot.append("open-threads", opts.advisor, f"closed session {opts.slug}: {goal_line}")
    except (ImportError, OSError):
        _log.debug("hot.append open-threads skipped (expected)", exc_info=True)
    except Exception:
        _log.warning("hot.append open-threads failed unexpectedly", exc_info=True)

    # 16. File handoff in-process if requested
    if opts.handoff_file:
        file_handoff(HandoffOpts(
            frm=opts.advisor,
            to=opts.handoff_to,
            date=opts.date,
            priority=opts.handoff_priority,
            title=opts.handoff_title,
            slug=opts.handoff_slug,
            body_file=opts.handoff_file,
        ))

    # 17. Briefing regen (best-effort, stdout-suppressed at fd level)
    try:
        import os as _os
        import sys as _sys

        from briefing.regen import regen_advisor
        _sys.stdout.flush()
        _devnull = _os.open(_os.devnull, _os.O_WRONLY)
        _saved = _os.dup(1)
        _os.dup2(_devnull, 1)
        _os.close(_devnull)
        try:
            regen_advisor(opts.advisor)
        finally:
            _sys.stdout.flush()
            _os.dup2(_saved, 1)
            _os.close(_saved)
    except (ImportError, OSError):
        _log.debug("briefing regen for session advisor skipped (expected)", exc_info=True)
    except Exception:
        _log.warning("briefing regen for session advisor failed unexpectedly", exc_info=True)

    # 18. Return session file path
    return str(out_file)


def emission_gate(ai_root, advisor: str, session_id: str, today: str) -> str | None:
    """Check mandatory emission for /team.done (spec 086 AC12/G1).

    Port of emission-gate.sh. Pure check — no stdout, no exit.

    Returns:
        str  — the expected emission path when the gate BLOCKS (file missing or still draft).
        None — when the gate PASSES (file present and _draft: false).
    """
    emission_path = Path(ai_root) / "ops" / "feedback" / today / f"{advisor}-{session_id}.md"
    if not emission_path.is_file():
        return str(emission_path)
    text = emission_path.read_text(encoding="utf-8")
    if not re.search(r"^_draft: false", text, re.M):
        return str(emission_path)
    return None


def _append_xref(target: Path, rel_path: str, date: str, by: str, slug: str) -> None:
    """Append a decision cross-reference line to target (idempotent)."""
    id_ = f"{date}-{by}-{slug}"
    line = f"- Decision: [{id_}]({rel_path})"

    if not target.is_file():
        return
    content = target.read_text(encoding="utf-8")
    if id_ in content:
        return  # already present

    # Ensure trailing newline before appending
    if content and not content.endswith("\n"):
        content += "\n"
    snapshot_write(target, content + line + "\n")

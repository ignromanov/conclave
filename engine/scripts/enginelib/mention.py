"""mention.py — create a cross-advisor mention. Port of mention.sh.

I/O-free of stdout/argparse/sys.exit. File I/O and briefing import are permitted.

Contract:
    create(opts: MentionOpts) -> str
        Validates, writes mentions/<to>/open/<id>.md atomically,
        triggers best-effort briefing regen, and returns the mention id.
    Raises:
        ValueError      — validation failure (missing/bad args, missing template)
        FileExistsError — id collision in open/ or archive/
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from enginelib import advisors, frontmatter, paths, slug, template
from enginelib.snapshot import snapshot_write

_log = logging.getLogger(__name__)


@dataclass
class MentionOpts:
    frm: str
    to: str
    body_file: str
    priority: str = "p2"
    now: str = ""
    ref_session: str = ""
    ref_decision: str = ""
    ref_issue: str = ""


def create(opts: MentionOpts) -> str:
    """File a cross-advisor mention and return its id."""
    # 1. Validate required args
    missing = [
        label
        for label, val in (("--from", opts.frm), ("--to", opts.to), ("--body-file", opts.body_file))
        if not val
    ]
    if missing:
        raise ValueError(f"required argument(s) missing: {' '.join(missing)}")

    body_path = Path(opts.body_file)
    if not body_path.is_file():
        raise ValueError(f"--body-file not found: {opts.body_file}")

    # 2. Validate canonical advisors
    for arg_name, arg_val in (("--from", opts.frm), ("--to", opts.to)):
        if not advisors.is_canonical_advisor(arg_val):
            known = "\n".join(f"  - {a}" for a in advisors.canonical_advisors())
            raise ValueError(
                f"{arg_name} \"{arg_val}\" is not a canonical advisor.\n"
                f"Known advisors:\n{known}"
            )

    # 3. Default now = local-offset ISO-8601 with colon in zone
    now = opts.now
    if not now:
        raw = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        now = raw[:-2] + ":" + raw[-2:]

    # 4. Body text and slug source (first non-empty line)
    body_text = body_path.read_text(encoding="utf-8")
    first_line = next((ln for ln in body_text.splitlines() if ln.strip()), body_text)

    # 5. Compute mention id
    mid = slug.mention_id(opts.frm, opts.to, first_line, now)

    # 6. Resolve paths
    mroot = paths.mentions_dir()
    open_file = mroot / opts.to / "open" / f"{mid}.md"
    archive_file = mroot / opts.to / "archive" / f"{mid}.md"
    paths.ensure_dir(open_file.parent)

    # 7. Collision guard (open/ then archive/)
    if open_file.exists():
        raise FileExistsError(f"id collision in open/: {mid} (use a distinct body/time)")
    if archive_file.exists():
        raise FileExistsError(
            f"id collision in archive/: {mid} (mention was resolved; pick a distinct slug)"
        )

    # 8. Render template (NOTE: "from" is a dict key — template.render takes a dict
    #    precisely because `from` is a Python keyword)
    tpl = paths.templates_dir() / "mention.md"
    if not tpl.exists():
        raise ValueError(f"template not found: {tpl}")
    rendered = template.render(tpl, {
        "id": mid,
        "from": opts.frm,
        "to": opts.to,
        "priority": opts.priority,
        "ref_session": opts.ref_session,
        "ref_decision": opts.ref_decision,
        "ref_issue": opts.ref_issue,
        "status": "open",
        "created": now,
        "resolved": "",
        "resolved_by": "",
        "resolved_note": "",
        "body": body_text,
    })

    # 9. Atomic write with exactly one trailing newline
    if not rendered.endswith("\n"):
        rendered += "\n"
    snapshot_write(open_file, rendered)

    # 10. Hot append for p0/p1 (guarded, deferred — enginelib.memory.hot built in 3D.3;
    #     import fails silently until then, faithful to bash best-effort/non-fatal contract)
    if opts.priority in ("p0", "p1"):
        try:
            from enginelib.memory import hot  # noqa: F401
            hot.append(
                "watch",
                opts.frm,
                f"[{opts.frm}→{opts.to}] {first_line} (priority: {opts.priority})",
            )
        except (ImportError, OSError):
            _log.debug("hot.append watch skipped (expected)", exc_info=True)
        except Exception:
            _log.warning("hot.append watch failed unexpectedly", exc_info=True)

    # 11. Briefing regen for recipient (best-effort, non-fatal).
    # Suppress stdout AND stderr at the fd level: briefing regen runs in-process and
    # prints step lines to stdout plus scan diagnostics to stderr (e.g. "gh-cache miss"
    # for a recipient with no/stale board — expected, esp. for meta-advisors like forge).
    # Neither is the sender's concern; the only stdout create()'s caller emits is the
    # mention id (I/O-free contract). Genuine failures still surface via _log below.
    try:
        import os as _os
        import sys as _sys

        from briefing.regen import regen_advisor
        _sys.stdout.flush()
        _sys.stderr.flush()
        _devnull = _os.open(_os.devnull, _os.O_WRONLY)
        _saved_out = _os.dup(1)
        _saved_err = _os.dup(2)
        _os.dup2(_devnull, 1)
        _os.dup2(_devnull, 2)
        _os.close(_devnull)
        try:
            regen_advisor(opts.to)
        finally:
            _sys.stdout.flush()
            _sys.stderr.flush()
            _os.dup2(_saved_out, 1)
            _os.dup2(_saved_err, 2)
            _os.close(_saved_out)
            _os.close(_saved_err)
    except (ImportError, OSError):
        _log.debug("briefing regen for recipient skipped (expected)", exc_info=True)
    except Exception:
        _log.warning("briefing regen for recipient failed unexpectedly", exc_info=True)

    return mid


def resolve(mention_id: str, by: str, note: str = "", now: str = "") -> str:
    """Resolve an open mention: mutate frontmatter in place, move open→archive.

    Port of resolve-mention.sh. I/O-free of stdout/argparse/sys.exit; file I/O OK.

    Returns mention_id.
    Raises:
        ValueError — validation failure, id not found, or ambiguous id.
    """
    # 1. Validate required args
    missing = [label for label, val in (("--id", mention_id), ("--by", by)) if not val]
    if missing:
        raise ValueError(f"required argument(s) missing: {' '.join(missing)}")

    # 2. Default now = local-offset ISO-8601 with colon in zone (same helper as create)
    if not now:
        raw = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
        now = raw[:-2] + ":" + raw[-2:]

    # 3. Locate open mention file via glob
    matches = sorted(paths.mentions_dir().glob(f"*/open/{mention_id}.md"))
    if len(matches) == 0:
        raise ValueError(f"id not found in any open/ directory: {mention_id}")
    if len(matches) > 1:
        raise ValueError(f"ambiguous id — matches {len(matches)} open files")

    # 4. Derive to_name from path: <mroot>/<to>/open/<id>.md
    open_file = matches[0]
    to_name = open_file.parent.parent.name

    # 5. Archive path
    archive_file = paths.mentions_dir() / to_name / "archive" / f"{mention_id}.md"
    paths.ensure_dir(archive_file.parent)

    # 6. Mutate frontmatter in place (before move — same file)
    frontmatter.fm_set(open_file, "status", "resolved")
    frontmatter.fm_set(open_file, "resolved", now)
    frontmatter.fm_set(open_file, "resolved_by", by)
    frontmatter.fm_set(open_file, "resolved_note", note)

    # 7. Move open_file → archive_file (faithful to mv -f; body preserved)
    open_file.replace(archive_file)

    return mention_id

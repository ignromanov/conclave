"""rename.py — change an advisor's id across an instance without losing its memory.

An advisor id is written down in four kinds of place, and each kind wants a
different treatment:

  config      live wiring (agent-def, router skill dir, roster surfaces, hot.md).
              Path renamed AND every whole-token occurrence in the text rewritten
              — these files describe the advisor as it is NOW.
  history     the record (sessions, decisions, mentions, feedback, handoffs).
              Path renamed and STRUCTURAL FRONTMATTER FIELDS rewritten, prose left
              alone: an old session that says "I was called X" stays true.
  regen       derived caches (briefings, gh-cache, git-cache). Deleted, never
              carried forward — a renamed stale briefing is a lie with a fresh
              mtime; the next session rebuilds it.
  protected   dated evidence (ops/archive/, ops/proof/). Untouched by construction.
              These name the id that existed at the time, and that is the point.

Anything else that mentions the id is reported as `unclassified` and left alone.
That bucket is the completeness assertion: a class nobody thought of shows up in
the plan instead of silently failing to move.

I/O-free core: reads and writes files; no print, no argparse, no process exit.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from enginelib import advisors, paths

# Classes, in report order.
CONFIG = "config"
HISTORY = "history"
REGEN = "regen"
PROTECTED = "protected"
UNCLASSIFIED = "unclassified"

_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# Frontmatter keys whose ENTIRE value is one advisor id. Rewritten in history files.
_ID_FIELDS = ("advisor", "by", "from", "to", "agent", "resolved_by", "resolved-by",
              "hired-by", "owner", "requested_by")

# Frontmatter keys that EMBED an id inside a derived identifier. Left as-is by
# policy (they are the record's own past identity), but reported so the operator
# sees what will no longer match its filename.
_DERIVED_FIELDS = ("id", "ref_session", "ref_handoff", "session_ref", "ref_decision")

_SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", ".pytest_cache"})


def token_re(word: str) -> re.Pattern[str]:
    """Match *word* only as a whole slug token.

    `-` must count as a boundary or `2026-08-06-<id>-slug.md` would never match;
    the cost is that a shorter id matches inside a longer one sharing a hyphen
    boundary (`growth` inside `growth-monetization`). `_check_ambiguous` refuses
    the rename in exactly that case rather than letting it corrupt filenames.
    """
    return re.compile(rf"(?<![a-z0-9]){re.escape(word)}(?![a-z0-9])")


# A history filename is not a bag of tokens — it has POSITIONS. The shapes:
#   <date>-<owner>-<slug>.md              sessions, decisions, handoffs
#   <date>-<time>-<from>-to-<to>-<slug>.md  mentions
#   <owner>-<slug>.md                     feedback records
# Only the owner / sender / recipient segments are an identity. Everything after
# them is prose that happens to be hyphenated, and a whole-token replace rewrites
# it too: on this instance `2026-07-06-sage-cto-sage-forge-discovery-…` (owner
# `sage-cto`, topic `forge`) and `…-advisor-to-forge-forge-it-3-…` (recipient,
# then the same word as slug text) were both corrupted by it. The defect was
# invisible for a whole round because the first migration renamed
# `engineering-data` — long enough never to occur inside a slug.
_DATE_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-")
_DATE_TIME_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{4}-")
_WORD_CHAR = re.compile(r"[a-z0-9]")


def _id_positions(part: str, old: str, *, is_name: bool) -> list[int]:
    """Offsets in *part* where *old* stands in an identity position.

    A directory is an identity only when it IS the id (`mentions/<id>/`), so a
    topic directory never moves.
    """
    if not is_name:
        return [0] if part == old else []
    starts = {0}
    for rx in (_DATE_PREFIX, _DATE_TIME_PREFIX):
        m = rx.match(part)
        if m:
            starts.add(m.end())
    starts.update(m.end() for m in re.finditer("-to-", part))
    return sorted(
        i for i in starts
        if part.startswith(old, i) and not _WORD_CHAR.match(part, i + len(old))
    )


def _rewrite_positions(part: str, old: str, new: str, *, is_name: bool) -> str:
    out = part
    for i in reversed(_id_positions(part, old, is_name=is_name)):
        out = out[:i] + new + out[i + len(old):]
    return out


@dataclass(frozen=True)
class Move:
    src: Path
    dst: Path
    cls: str


@dataclass(frozen=True)
class Edit:
    path: Path          # the path AFTER its move, i.e. where the edit lands
    cls: str
    kind: str           # "token" | "field" | "jsonl"
    detail: str


@dataclass(frozen=True)
class Drop:
    path: Path
    reason: str


@dataclass(frozen=True)
class Note:
    path: Path
    detail: str


@dataclass
class RenamePlan:
    old: str
    new: str
    data_root: Path
    moves: list[Move] = field(default_factory=list)
    edits: list[Edit] = field(default_factory=list)
    drops: list[Drop] = field(default_factory=list)
    skipped: list[tuple[str, Path]] = field(default_factory=list)   # (class, path)
    inert: list[Path] = field(default_factory=list)   # matched, no action earned
    notes: list[Note] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "moves": len(self.moves),
            "edits": len(self.edits),
            "deletes": len(self.drops),
            "protected": sum(1 for c, _ in self.skipped if c == PROTECTED),
            "unclassified": sum(1 for c, _ in self.skipped if c == UNCLASSIFIED),
            "prose-only": len(self.inert),
        }


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def _rel(path: Path, root: Path) -> Path | None:
    try:
        return path.relative_to(root)
    except ValueError:
        return None


def _classify(path: Path, data_root: Path, claude_dirs: list[Path]) -> str:
    """Return the handling class for *path*.

    `.claude/` is probed FIRST: in the in-repo layout it sits INSIDE the DATA root,
    and the data rules would otherwise swallow it as unclassified.

    There are TWO of them and both matter. The consumer project's `.claude/` holds
    the agent-defs and router skills; the DATA root has its own `.claude/CLAUDE.md`
    carrying the roster table. Probing only the first left that table — the file
    that tells the harness which agent to route to — reported as unclassified.
    """
    for claude_dir in claude_dirs:
        rel = _rel(path, claude_dir)
        if rel is None:
            continue
        head = rel.parts[0] if rel.parts else ""
        if head in ("agents", "skills") or rel.name == "CLAUDE.md":
            return CONFIG
        return UNCLASSIFIED

    rel = _rel(path, data_root)
    if rel is None:
        return UNCLASSIFIED
    parts = rel.parts

    if parts[:2] in (("ops", "archive"), ("ops", "proof")):
        return PROTECTED
    if parts[:3] == ("agent-memory", "advisors", "briefings"):
        return REGEN
    if parts[:2] in (("agent-memory", "gh-cache"), ("agent-memory", "git-cache")):
        return REGEN
    if parts[:3] in (
        ("agent-memory", "advisors", "sessions"),
        ("agent-memory", "advisors", "decisions"),
        ("agent-memory", "advisors", "mentions"),
        ("agent-memory", "advisors", "audits"),
    ):
        return HISTORY
    # ops/decisions/ holds cross-cutting Y-statements keyed by `by:`, which the
    # briefing reads beside the advisor's own decisions (briefing/scans/decisions.py).
    # Knowing only agent-memory/advisors/decisions/ left them pointing at the retired
    # id. Found by the `unclassified` bucket on a real instance, not by design.
    if parts[:2] in (("ops", "feedback"), ("ops", "handoffs"), ("ops", "decisions")):
        return HISTORY
    if rel.as_posix() == "agent-memory/hot.md" or rel.name in (
        "role-manifest.yaml", "roster.yaml",
    ):
        return CONFIG
    return UNCLASSIFIED


def _iter_files(root: Path, exclude: frozenset[Path] = frozenset()):
    if not root.is_dir():
        return
    stack = [root]
    while stack:
        d = stack.pop()
        if d.resolve() in exclude:
            continue
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_symlink():
                continue
            if e.is_dir():
                if e.name not in _SKIP_DIRS:
                    stack.append(e)
            elif e.is_file():
                yield e


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


# ---------------------------------------------------------------------------
# Content rewriting
# ---------------------------------------------------------------------------

def _frontmatter_span(lines: list[str]) -> tuple[int, int] | None:
    """(start, end) exclusive indices of the frontmatter body, or None.

    Finds the FIRST `---` fence anywhere — feedback files open with an HTML
    data-classification comment before their frontmatter.
    """
    start = None
    for i, ln in enumerate(lines):
        if ln.strip() == "---":
            if start is None:
                start = i
            else:
                return (start + 1, i)
    return None


def _rewrite_fields(text: str, old: str, new: str) -> tuple[str, list[str]]:
    """Rewrite structural id fields in frontmatter only. Returns (text, details)."""
    lines = text.splitlines(keepends=True)
    span = _frontmatter_span([ln.rstrip("\r\n") for ln in lines])
    if span is None:
        return text, []
    details: list[str] = []
    for i in range(span[0], span[1]):
        raw = lines[i]
        stripped = raw.rstrip("\r\n")
        for key in _ID_FIELDS:
            prefix = f"{key}:"
            if not stripped.startswith(prefix):
                continue
            if stripped[len(prefix):].strip() != old:
                continue
            eol = raw[len(stripped):]
            lines[i] = f"{key}: {new}{eol}"
            details.append(f"{key}: {old} → {new}")
            break
    return "".join(lines), details


def _derived_notes(text: str, old: str) -> list[str]:
    """Frontmatter values that embed the old id in a derived identifier."""
    lines = [ln.rstrip("\r\n") for ln in text.splitlines()]
    span = _frontmatter_span(lines)
    if span is None:
        return []
    rx = token_re(old)
    out: list[str] = []
    for i in range(span[0], span[1]):
        for key in _DERIVED_FIELDS:
            if lines[i].startswith(f"{key}:") and rx.search(lines[i][len(key) + 1:]):
                out.append(lines[i].strip())
                break
    return out


def _rewrite_jsonl(text: str, old: str, new: str) -> tuple[str, list[str]]:
    """Rewrite top-level id fields in a JSONL index. Non-JSON lines pass through."""
    out: list[str] = []
    details: list[str] = []
    changed = 0
    for line in text.splitlines():
        if not line.strip():
            out.append(line)
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            out.append(line)
            continue
        if isinstance(row, dict):
            hit = False
            for key in _ID_FIELDS:
                if row.get(key) == old:
                    row[key] = new
                    hit = True
            if hit:
                changed += 1
                out.append(json.dumps(row))
                continue
        out.append(line)
    if changed:
        details.append(f"agent: {old} → {new} in {changed} row(s)")
    return "\n".join(out) + "\n", details


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------

def _check_ambiguous(old: str, new: str, roster: list[str]) -> None:
    others = [a for a in roster if a not in (old, new)]
    for word in (old, new):
        rx = token_re(word)
        for other in others:
            if rx.search(other):
                raise ValueError(
                    f"ambiguous rename: {word!r} matches as a token inside the live advisor id "
                    f"{other!r}. A whole-token rewrite cannot tell the two apart in a filename "
                    f"like 2026-01-01-{other}-slug.md. Rename {other!r} first, or pick a "
                    f"non-overlapping id."
                )


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------

def plan(old: str, new: str) -> RenamePlan:
    """Build the complete rename plan. Writes nothing.

    Raises ValueError on a guard failure the operator must fix (adapter → exit 1)
    and FileExistsError on a collision (adapter → exit 2).
    """
    if not old or not _SLUG_RE.fullmatch(old):
        raise ValueError(f"invalid --from: must match ^[a-z0-9]+(-[a-z0-9]+)*$ (got: {old!r})")
    # --to must conform to the naming standard; --from deliberately does NOT, because
    # the ids that most need renaming are precisely the ones that never conformed.
    try:
        advisors.validate_advisor_id(new)
    except ValueError as e:
        raise ValueError(f"invalid --to: {e}") from e
    if old == new:
        raise ValueError("invalid --to: --from and --to are the same id")

    roster = advisors.canonical_advisors()
    # `old` is verified below, AFTER the scan, not here. The guard's purpose is to
    # catch a typo, and roster membership is the wrong proxy for that: a CODE-side
    # identity change retires the old id from the roster BEFORE its data catches up
    # (forge → forge-chro left 130 artifacts naming an id the roster no longer knew),
    # so a membership test refuses precisely the migration this command exists for.
    # An id that owns artifacts on disk is not a typo, whether or not it is still hired.
    #
    # `--to` is judged the same way, and for the mirror-image reason: a CODE-side
    # rename creates the NEW agent-def before the data moves, so the target is
    # already in the roster while owning nothing. Refusing on roster membership
    # blocks the completion of the very rename that created it. What must never
    # happen is folding two identities together, so occupancy is judged by MEMORY.
    # Config clashes are caught precisely by `_check_collisions`, which names the
    # two paths rather than the id.
    data_root = paths.repo_root()
    if _owns_memory(new, data_root):
        raise FileExistsError(
            f'--to "{new}" already exists and owns memory of its own — renaming onto it '
            f"would merge two advisors' histories, which cannot be undone."
        )

    _check_ambiguous(old, new, roster)

    claude_dirs = [paths.project_claude_dir(), data_root / ".claude"]
    p = RenamePlan(old=old, new=new, data_root=data_root)

    rx = token_re(old)
    roots = [data_root]
    roots += [d for d in claude_dirs if _rel(d, data_root) is None]

    # The run-log is engine observability, not instance data — and this very
    # invocation appends to it. Scanning it would make the plan a function of the
    # planning, so a dry-run and the apply that follows would report different
    # totals. Excluded, never counted, never rewritten.
    #
    # BOTH the canonical location and the CONCLAVE_RUN_LOG_DIR override are
    # excluded. Pinning only the override is how this protection disabled itself:
    # a run with the override set left the instance's real run-log unguarded, and
    # it duly turned up in the plan as unclassified.
    exclude = frozenset({
        paths.run_log_dir().resolve(),
        (paths.agent_memory_dir() / "run-log").resolve(),
    })

    seen: set[Path] = set()
    for root in roots:
        for f in _iter_files(root, exclude):
            if f in seen:
                continue
            seen.add(f)
            text = _read(f)
            path_hit = bool(rx.search(f.as_posix()))
            if not path_hit and (text is None or not rx.search(text)):
                continue
            cls = _classify(f, data_root, claude_dirs)
            if cls in (PROTECTED, UNCLASSIFIED):
                p.skipped.append((cls, f))
                continue
            dst = _renamed_path(f, root, rx, new, cls, old)
            if cls == REGEN:
                p.drops.append(Drop(f, "auto-generated — regenerated on next session"))
                continue
            if dst != f:
                p.moves.append(Move(f, dst, cls))
            if text is None:
                continue
            acted = dst != f
            if cls == CONFIG:
                n = len(rx.findall(text))
                if n:
                    p.edits.append(Edit(dst, cls, "token", f"{old} → {new} ×{n}"))
                    acted = True
            elif f.name.endswith(".jsonl"):
                _, details = _rewrite_jsonl(text, old, new)
                for d in details:
                    p.edits.append(Edit(dst, cls, "jsonl", d))
                acted = acted or bool(details)
            else:
                _, details = _rewrite_fields(text, old, new)
                for d in details:
                    p.edits.append(Edit(dst, cls, "field", d))
                acted = acted or bool(details)
                for d in _derived_notes(text, old):
                    p.notes.append(Note(dst, d))
            if not acted:
                # Matched the old id but earned no move, edit or delete — a history
                # record that names the advisor only in its prose. Left alone by
                # policy, and SAID so: a file that vanishes from the report is
                # indistinguishable from one the planner never saw.
                p.inert.append(f)

    if old not in roster and not (p.moves or p.edits or p.drops or p.skipped or p.inert):
        raise ValueError(
            f'--from "{old}" is not a canonical advisor, and nothing on disk names it.\n'
            f"Known advisors: {', '.join(roster)}"
        )

    _check_collisions(p)
    return p


def _owns_memory(advisor_id: str, data_root: Path) -> bool:
    """Does *advisor_id* already hold a record of its own?

    Only the HISTORY tree is consulted — sessions, decisions, mentions, feedback,
    handoffs. Live config (an agent-def, a router, a briefing stub) is what a
    freshly-created-or-renamed identity has and nothing more, so counting it would
    make every target look occupied. Memory is what cannot be merged.
    """
    roots = [
        data_root / "agent-memory" / "advisors" / d
        for d in ("sessions", "decisions", "mentions", "audits")
    ] + [data_root / "ops" / "feedback", data_root / "ops" / "handoffs"]
    for root in roots:
        for f in _iter_files(root):
            # Positional, for the same reason the rename is: a record whose TOPIC
            # is the target id does not make that id an owner of memory, and
            # reading it as one would refuse a legitimate migration.
            if _renamed_path(f, root, token_re(advisor_id), "", HISTORY, advisor_id) != f:
                return True
            text = _read(f)
            if text is None:
                continue
            if any(d.endswith(f"{advisor_id}") for d in _field_values(text)):
                return True
    return False


def _field_values(text: str) -> list[str]:
    """Values of the structural id fields in *text*'s frontmatter."""
    lines = [ln.rstrip("\r\n") for ln in text.splitlines()]
    span = _frontmatter_span(lines)
    if span is None:
        return []
    out = []
    for i in range(span[0], span[1]):
        for key in _ID_FIELDS:
            if lines[i].startswith(f"{key}:"):
                out.append(lines[i][len(key) + 1:].strip())
                break
    return out


def _renamed_path(f: Path, root: Path, rx: re.Pattern[str], new: str, cls: str, old: str) -> Path:
    """Where *f* lands after the rename.

    CONFIG keeps the whole-token replace: it names the advisor mid-token on
    purpose (`conclave-<id>/`, `exec-<id>.md`), and there every occurrence IS the
    identity. HISTORY is position-aware — see `_id_positions`.
    """
    rel = f.relative_to(root)
    if cls != HISTORY:
        return root.joinpath(*(rx.sub(new, part) for part in rel.parts))
    last = len(rel.parts) - 1
    return root.joinpath(*(
        _rewrite_positions(part, old, new, is_name=(i == last))
        for i, part in enumerate(rel.parts)
    ))


def _check_collisions(p: RenamePlan) -> None:
    sources = {m.src for m in p.moves}
    clashes = [m for m in p.moves if m.dst.exists() and m.dst not in sources]
    dsts: dict[Path, Move] = {}
    for m in p.moves:
        if m.dst in dsts:
            clashes.append(m)
        dsts[m.dst] = m
    if clashes:
        lines = "\n".join(f"  {m.src} → {m.dst}" for m in clashes)
        raise FileExistsError(
            f"collision: {len(clashes)} planned move(s) would overwrite an existing path.\n"
            f"Nothing was written.\n{lines}"
        )


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------

def apply(p: RenamePlan) -> dict[str, int]:
    """Execute *p*. Validation already happened in `plan`; this only writes."""
    for drop in p.drops:
        drop.path.unlink(missing_ok=True)

    pruned: set[Path] = set()
    for m in p.moves:
        m.dst.parent.mkdir(parents=True, exist_ok=True)
        m.src.rename(m.dst)
        pruned.add(m.src.parent)

    for path in {e.path for e in p.edits}:
        text = _read(path)
        if text is None:
            continue
        if path.name.endswith(".jsonl"):
            new_text, _ = _rewrite_jsonl(text, p.old, p.new)
        elif any(e.kind == "token" for e in p.edits if e.path == path):
            new_text = token_re(p.old).sub(p.new, text)
        else:
            new_text, _ = _rewrite_fields(text, p.old, p.new)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")

    _prune_empty(pruned, p.data_root)
    return p.counts()


def _prune_empty(dirs: set[Path], data_root: Path) -> None:
    """Remove directories emptied by the moves, walking up to (never past) the root."""
    for d in sorted(dirs, key=lambda x: len(x.parts), reverse=True):
        cur = d
        while cur != data_root and cur != cur.parent:
            try:
                next(cur.iterdir())
                break
            except StopIteration:
                pass
            except OSError:
                break
            parent = cur.parent
            try:
                cur.rmdir()
            except OSError:
                break
            cur = parent


# ---------------------------------------------------------------------------
# Rendering (pure — returns lines, prints nothing)
# ---------------------------------------------------------------------------

def render(p: RenamePlan, *, applied: bool) -> list[str]:
    def show(path: Path) -> str:
        rel = _rel(path, p.data_root)
        return rel.as_posix() if rel is not None else path.as_posix()

    mode = "APPLIED" if applied else "dry-run — nothing written"
    out = [f"PLAN {p.old} → {p.new}   ({mode})", ""]

    for cls in (CONFIG, HISTORY, REGEN):
        moves = [m for m in p.moves if m.cls == cls]
        edits = [e for e in p.edits if e.cls == cls]
        drops = p.drops if cls == REGEN else []
        if not (moves or edits or drops):
            continue
        out.append(f"{cls} ({len(moves) + len(edits) + len(drops)})")
        for m in moves:
            out.append(f"  MOVE   {show(m.src)} → {show(m.dst)}")
        for e in edits:
            out.append(f"  EDIT   {show(e.path)}  [{e.kind}] {e.detail}")
        for d in drops:
            out.append(f"  DELETE {show(d.path)}  ({d.reason})")
        out.append("")

    for cls, label in ((PROTECTED, "protected — dated evidence, untouched"),
                       (UNCLASSIFIED, "unclassified — untouched, review by hand")):
        rows = [path for c, path in p.skipped if c == cls]
        if not rows:
            continue
        out.append(f"{label} ({len(rows)})")
        out += [f"  SKIP   {show(r)}" for r in rows]
        out.append("")

    if p.inert:
        out.append(f"prose-only ({len(p.inert)}) — names the id in body text, untouched")
        out += [f"  KEEP   {show(i)}" for i in p.inert]
        out.append("")

    if p.notes:
        out.append(f"stale-after-rename ({len(p.notes)}) — derived ids kept by policy")
        out += [f"  NOTE   {show(n.path)}  {n.detail}" for n in p.notes]
        out.append("")

    out.append(f"SUMMARY {json.dumps(p.counts(), sort_keys=True)}")
    return out

"""enginelib.lifecycle.archive_handoff — give an exhausted handoff a terminal state.

Contract: no stdout, no argparse, no sys.exit. File moves are allowed.

A handoff is a resume-prompt: session_init's resume-scan surfaces every handoff in
`ops/handoffs/` addressed to the advisor starting the session. That scan is non-recursive,
so `ops/handoffs/archive/` is already invisible to it — the carrier for a terminal state
existed, but nothing ever moved a consumed handoff into it. Handoffs for
long-shipped work therefore resurfaced at every session forever (#55).

Terminal state is the file's LOCATION, and the transition is a move. Never a delete, and
never an overwrite: an archived handoff is evidence, so a name collision is an error the
operator resolves, not something this module silently resolves for them.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

ARCHIVE_DIRNAME = "archive"


def resolve(handoffs_dir: Path, name: str) -> Path:
    """Resolve a bare handoff filename inside handoffs_dir.

    A handoff is identified by NAME, never by path: accepting a path would let
    `../../something.md` move a file that is not a handoff at all. Anything carrying a
    directory component is rejected rather than normalized.
    """
    if not name or name != Path(name).name or name in {".", ".."}:
        raise ValueError(f"handoff must be a bare filename, not a path: {name!r}")
    return handoffs_dir / name


def plan(handoffs_dir: Path, names: Iterable[str]) -> list[tuple[Path, Path]]:
    """Validate every name and return the (src, dest) moves, touching nothing.

    Validation is total and happens before any move, so a bad name in position 3 cannot
    leave positions 1 and 2 already archived — a partial batch is a state the operator
    would have to reconstruct by hand.
    """
    archive = handoffs_dir / ARCHIVE_DIRNAME
    moves: list[tuple[Path, Path]] = []
    seen: set[str] = set()
    for name in names:
        src = resolve(handoffs_dir, name)
        if not src.is_file():
            raise ValueError(f"handoff not found: {name}")
        if name in seen:
            raise ValueError(f"named twice in one batch: {name}")
        dest = archive / name
        if dest.exists():
            raise ValueError(f"already archived — refusing to overwrite: {name}")
        seen.add(name)
        moves.append((src, dest))
    return moves


def run(
    handoffs_dir: Path, names: Iterable[str], dry_run: bool = False
) -> list[tuple[Path, Path]]:
    """Archive the named handoffs; return the (src, dest) pairs planned or moved."""
    moves = plan(handoffs_dir, list(names))
    if dry_run:
        return moves
    (handoffs_dir / ARCHIVE_DIRNAME).mkdir(parents=True, exist_ok=True)
    for src, dest in moves:
        src.rename(dest)
    return moves

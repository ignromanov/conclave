"""enginelib/doctor.py — First-Launch preflight checks (#49c).

I/O-free of stdout/argparse/sys.exit (file reads + an optional --fix seed are OK).
The CLI adapter (engine/cmd/doctor.py) formats Checks and maps exit_code().

Asserts the preconditions that silently broke a real First Launch: a resolvable
data root, a well-formed hot.md (so `engine file decision` can't crash on a
missing section header), and — when an advisor is given — that it is discoverable
in the instance registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

_HOT_SECTIONS = ("## Now", "## Open threads", "## Recent decisions", "## Watch")


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _hot_check(root: Path, fix: bool) -> Check:
    hot = root / "agent-memory" / "hot.md"
    if hot.is_file():
        text = hot.read_text(encoding="utf-8")
        missing = [s for s in _HOT_SECTIONS if s not in text]
        if not missing:
            return Check("hot.md", True, "well-formed")
        # Malformed: never silently clobber — a raw file may hold real content.
        return Check("hot.md", False, f"missing sections: {', '.join(missing)} (manual repair)")
    if fix:
        from enginelib.memory import hot as hotmod
        hotmod.init(hot_path=hot)
        return Check("hot.md", True, f"seeded skeleton at {hot}")
    return Check("hot.md", False, f"missing ({hot}) — run `engine doctor --fix` to seed")


def _advisor_check(root: Path, advisor: str) -> Check:
    from enginelib.advisors import _META_ADVISORS, known_advisors
    known = known_advisors(root)
    ok = advisor in known or advisor in _META_ADVISORS
    if ok:
        return Check(f"advisor:{advisor}", True, "in instance registry")
    listing = ", ".join(sorted(known)) or "(none hired)"
    return Check(f"advisor:{advisor}", False, f"not in registry — known: {listing}")


def run_checks(root: Path, advisor: str | None = None, fix: bool = False) -> list[Check]:
    """Return the preflight Checks for a data root.

    - data-root: the root exists as a directory.
    - hot.md: exists and carries all canonical sections (seeded when fix=True).
    - advisor:<id>: discoverable via known_advisors (forge accepted as META).
    """
    checks: list[Check] = [
        Check("data-root", root.is_dir(), str(root)),
        _hot_check(root, fix),
    ]
    if advisor:
        checks.append(_advisor_check(root, advisor))
    return checks


def exit_code(checks: list[Check]) -> int:
    """0 when every check passed, 1 otherwise."""
    return 0 if all(c.ok for c in checks) else 1

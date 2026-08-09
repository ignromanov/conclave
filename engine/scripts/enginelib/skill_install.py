"""enginelib/skill_install.py — decide whether a skill package may be installed.

Spec 112 §2.2. `skills add` fetches third-party code from GitHub into the operator's global
agent directory, so installation is allow-listed. The allowlist is enforced *here*, by code,
rather than by an instruction in the executor's prompt: an allowlist an agent is trusted to
honour is enforced by the same attention the whole design exists because it cannot rely on.

I/O-free core: no stdout, no argparse, no sys.exit, no subprocess. This module answers "may
this be installed?" and builds the argv; the CLI adapter in engine/cmd/skill.py runs it.
"""
from __future__ import annotations

import re
from collections.abc import Sequence

_ALLOWED_SOURCES_HEADING = "## Allowed sources"

# `owner/repo` or `owner/repo@skill`. Deliberately narrow: no path separators beyond the single
# slash, no whitespace, no shell metacharacters. Anything that fails this cannot be matched
# against the allowlist at all, so shape-checking is the first line of the injection guard.
_PACKAGE = re.compile(r"^([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+)(?:@([A-Za-z0-9._-]+))?$")


def parse_allowlist(text: str) -> list[str]:
    """Bulleted entries under the `## Allowed sources` heading, backticks stripped.

    Only that section counts. Prose and other sections may say anything; a source becomes
    allowed by appearing in one specific list, never by being mentioned.
    """
    entries: list[str] = []
    in_section = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_section = line.strip() == _ALLOWED_SOURCES_HEADING
            continue
        if in_section and line.startswith("- "):
            entries.append(line[2:].strip().strip("`").strip())
    return [e for e in entries if e]


def package_source(pkg: str) -> str | None:
    """`owner/repo` for a well-formed package spec, else None."""
    m = _PACKAGE.match(pkg.strip()) if pkg else None
    return f"{m.group(1)}/{m.group(2)}" if m else None


def is_allowed(pkg: str, allowlist: Sequence[str]) -> bool:
    """True only if the package parses AND its source matches an allowlist entry.

    An entry is either an exact `owner/repo` or `owner/*`, which covers every repo of that
    owner and nothing else — prefix matching on the raw string would let `anthropics-evil/x`
    through on an `anthropics` entry.
    """
    source = package_source(pkg)
    if source is None:
        return False
    owner, _, _repo = source.partition("/")
    for entry in allowlist:
        if entry == source:
            return True
        entry_owner, sep, entry_repo = entry.partition("/")
        if sep and entry_repo == "*" and entry_owner == owner:
            return True
    return False


def install_command(pkg: str) -> list[str]:
    """argv for the installer — a list, never a shell string."""
    return ["skills", "add", pkg, "-g", "-y"]


def refusal_message(pkg: str, allowlist_path: str) -> str:
    """What the caller is told when a package is refused.

    Names the manual command on purpose: a refusal is a decision handed back to the operator,
    not a dead end, and it must never read as "nothing was needed here".
    """
    return (
        f"refused: {pkg} is not from an allow-listed source\n"
        f"  allowlist: {allowlist_path}\n"
        f"  to install it yourself: skills add {pkg} -g -y\n"
        f"  to allow it permanently: add its owner/repo to the allowlist"
    )

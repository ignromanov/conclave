"""tests/enginelib/test_skill_install.py — the allow-list decision (spec 112 T2).

The decision is tested here; the download is not. `skills add` fetches third-party code from
GitHub, so the subprocess lives in the CLI adapter and these tests exercise only what may be
installed. A test that reached the network would be testing the registry, not the policy.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from enginelib.skill_install import (
    install_command,
    is_allowed,
    package_source,
    parse_allowlist,
)

# tests/enginelib/test_skill_install.py → parents[4] = repo root (one deeper than tests/*.py)
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ALLOWLIST = (
    _REPO_ROOT / "skills" / "forge-operations" / "references" / "skill-sources.md"
)


# ── parsing ───────────────────────────────────────────────────────────────────


def test_parse_allowlist_reads_the_bulleted_entries():
    text = (
        "# Allowed skill sources\n\nprose that is not an entry\n\n"
        "## Allowed sources\n"
        "- `anthropics/*`\n"
        "- `vercel-labs/agent-skills`\n\n"
        "## Notes\n- this heading's bullets are not entries\n"
    )
    assert parse_allowlist(text) == ["anthropics/*", "vercel-labs/agent-skills"]


def test_parse_allowlist_of_an_empty_section_is_empty():
    assert parse_allowlist("## Allowed sources\n\n## Notes\n- nope\n") == []


# ── the decision ──────────────────────────────────────────────────────────────


def test_empty_allowlist_refuses_everything():
    """Fail closed. An allowlist nobody has filled in must not be a pass-through."""
    assert not is_allowed("vercel-labs/agent-skills@react", [])


def test_exact_source_is_allowed():
    assert is_allowed("obra/superpowers@brainstorming", ["obra/superpowers"])


def test_owner_wildcard_covers_any_repo_of_that_owner():
    assert is_allowed("anthropics/whatever@x", ["anthropics/*"])


def test_owner_wildcard_does_not_leak_to_other_owners():
    assert not is_allowed("anthropics-evil/x@y", ["anthropics/*"])
    assert not is_allowed("notanthropics/x@y", ["anthropics/*"])


def test_unlisted_source_is_refused():
    assert not is_allowed("stranger/repo@skill", ["anthropics/*", "obra/superpowers"])


@pytest.mark.parametrize(
    "pkg",
    [
        "",
        "noslash",
        "too/many/slashes",
        "owner/",
        "/repo",
        "owner/repo@",
        "owner/repo@skill@extra",
        "../../etc/passwd",
        "owner/repo; rm -rf /",
        "owner/repo@skill with space",
    ],
)
def test_malformed_package_is_never_allowed(pkg):
    """Shape is checked before membership: a package that does not parse cannot match.

    This is also the injection guard — `install_command` builds an argv list rather than a
    shell string, and anything carrying shell syntax fails the shape check first.
    """
    assert package_source(pkg) is None
    assert not is_allowed(pkg, ["owner/*", "owner/repo"])


def test_install_command_is_argv_not_a_shell_string():
    cmd = install_command("obra/superpowers@brainstorming")
    assert cmd[0] == "skills" and "add" in cmd
    assert "obra/superpowers@brainstorming" in cmd
    assert all(isinstance(part, str) for part in cmd)
    assert not any(" " in part for part in cmd if part != "obra/superpowers@brainstorming")


# ── the shipped file ──────────────────────────────────────────────────────────


def test_shipped_allowlist_entries_are_well_formed():
    """Every entry is `owner/repo` or `owner/*` — nothing else can be matched against."""
    entries = parse_allowlist(_ALLOWLIST.read_text(encoding="utf-8"))
    assert entries, "the shipped allowlist is empty — refuse-everything is a choice, state it"
    for entry in entries:
        owner, _, repo = entry.partition("/")
        assert owner and repo, f"malformed allowlist entry: {entry!r}"
        assert "/" not in repo, f"allowlist entry has too many segments: {entry!r}"

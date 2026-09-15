"""A hired advisor's files land in DATA, with CODE holding symlinks to them (#134).

Spec 103 §4 puts hired advisors in the DATA repo. The CODE checkout's `.gitignore`
states the same layout as settled fact:

    # hired advisors are DATA (spec 103 §4): the real files live in .conclave/.claude/,
    # and .claude/{agents,skills} hold per-item symlinks back to them.
    .claude/agents/
    .claude/skills/

`engine advisor create` wrote REAL files into those two gitignored CODE directories,
while the briefing stub it writes in the same call went to DATA. So a freshly hired
advisor was tracked by neither repository — present on the operator's disk, absent from
both histories, and recoverable from nothing. The first hire after the split had to be
moved by hand.

## The root cause is not that create() stopped making symlinks

Nothing ever made them. Searched across the whole checkout, the only code that has ever
called `symlink_to` or `os.symlink` is TEST code. Every symlink in the live instance was
created by an operator at a shell prompt, while three separate surfaces documented the
layer as if the engine produced it: the `.gitignore` comment above, spec 103 §4, and
`audit/agent_configs.py`, whose scanner was taught to descend through these links
precisely because they are expected to exist.

A layer every reader depends on and no writer creates is invisible on exactly one kind
of machine — the one where somebody already made it by hand. That is this instance, and
it is why the audits stayed green.

#30 owns scaffolding and REPAIRING the whole two-root layout at `:init`. It names this
half explicitly: `.claude/agents/<id>.md` is "created per hired advisor, i.e. by `hire`,
not only by `init`". That half is here. #30's stated blocker — the secret scanner must
follow symlinks before any symlink is created — was closed 2026-07-10, and the scanner's
descent is itself under test.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.cmd.helpers import run_engine

ADVISOR = "vera-cto"
SKILL = f"conclave-{ADVISOR}"


def _create(project: Path, data: Path):
    return run_engine(
        "advisor", "create",
        "--id", ADVISOR, "--role", "QA", "--color", "blue", "--emoji", "🛰️",
        env={"CONCLAVE_AI_ROOT": str(data), "CLAUDE_PROJECT_DIR": str(project)},
    )


@pytest.fixture
def split(tmp_path):
    """The real topology: a CODE checkout with a `.conclave` DATA root inside it.

    The dogfooding instance is the only place this defect could be SEEN and the last
    place it could be reproduced by accident — its symlinks predate the bug report.
    Building the split by hand is the only way to watch create() choose.
    """
    project = tmp_path / "proj"
    data = project / ".conclave"
    (project / ".claude").mkdir(parents=True)
    data.mkdir(parents=True)
    r = _create(project, data)
    assert r.returncode == 0, r.stderr
    return project, data


def test_the_agent_def_is_a_real_file_in_data(split):
    project, data = split
    real = data / ".claude" / "agents" / f"{ADVISOR}.md"
    assert real.is_file() and not real.is_symlink(), (
        f"the agent-def is not a real file in DATA at {real}. "
        f"DATA holds: {sorted(p.name for p in (data / '.claude').rglob('*'))}"
    )
    assert "name: vera-cto" in real.read_text(encoding="utf-8")


def test_code_holds_a_symlink_not_a_copy(split):
    project, data = split
    link = project / ".claude" / "agents" / f"{ADVISOR}.md"
    assert link.is_symlink(), (
        f"{link} is not a symlink — a real file here is tracked by neither repo, "
        "because .gitignore excludes .claude/agents/ and the file is not in DATA (#134)"
    )
    assert link.resolve() == (data / ".claude" / "agents" / f"{ADVISOR}.md").resolve()


def test_the_skill_dir_is_a_symlink_to_data(split):
    project, data = split
    link = project / ".claude" / "skills" / SKILL
    assert link.is_symlink(), f"{link} is not a symlink"
    assert (link / "SKILL.md").is_file(), "the link does not reach a real SKILL.md"
    assert (data / ".claude" / "skills" / SKILL / "SKILL.md").is_file(), (
        "the SKILL.md is not in DATA"
    )


def test_link_targets_are_relative(split):
    """An absolute target embeds the operator's home directory (#83) and breaks the
    moment the checkout is cloned, moved, or opened in a worktree."""
    project, _ = split
    for link in (project / ".claude" / "agents" / f"{ADVISOR}.md",
                 project / ".claude" / "skills" / SKILL):
        target = os.readlink(link)
        assert not os.path.isabs(target), f"{link} points at an absolute path: {target}"


def test_nothing_is_left_only_in_the_code_tree(split):
    """The whole point, stated as the operator would: every scaffolded byte is in DATA.

    Each assertion above can be satisfied one file at a time; this one fails if any
    future addition to create() lands a real file in the gitignored CODE dirs again.
    """
    project, _ = split
    strays = [
        p for p in (project / ".claude").rglob("*")
        if p.is_file() and not any(part.is_symlink() for part in [p, *p.parents])
    ]
    assert not strays, (
        f"real files under the gitignored CODE .claude/: {strays}. "
        "Tracked by neither repository (#134)."
    )


def test_a_real_file_where_the_link_belongs_is_reported_and_nothing_is_written(tmp_path):
    """The pre-#134 shape, met head-on: a real agent-def already in the CODE tree.

    It is gitignored in CODE and absent from DATA, so it is the ONLY copy of whatever
    the operator enriched there — the rule against quiet removal binds hardest exactly
    where the file looks like leftover junk.

    Refusing is not enough: the refusal has to come BEFORE anything is written, or the
    operator is told "move it into DATA and re-run" while DATA already holds a fresh
    scaffold, and the re-run dies on the collision guard instead. So this asserts the
    DATA side is untouched too. That is what the surviving mutation found — the guard
    was real, and it sat one step too late.
    """
    project = tmp_path / "proj"
    data = project / ".conclave"
    squatter = project / ".claude" / "agents" / f"{ADVISOR}.md"
    squatter.parent.mkdir(parents=True)
    data.mkdir(parents=True)
    squatter.write_text("---\nname: vera-cto\n---\nHAND-ENRICHED, IRREPLACEABLE\n")

    r = _create(project, data)

    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "HAND-ENRICHED" in squatter.read_text(), "the only copy was overwritten"
    assert not (data / ".claude" / "agents" / f"{ADVISOR}.md").exists(), (
        "DATA was written before the refusal — the operator is now told to move the "
        "CODE file into a DATA path that is already occupied, and the re-run they are "
        "asked for dies on the collision guard"
    )


def test_a_colocated_instance_gets_real_files_and_no_self_link(tmp_path):
    """When DATA and CODE are the same root there is no second place to point at.

    This is not a rare fallback: every hermetic test in this suite runs it, and so does
    a dev checkout with no `.conclave`. A symlink here would point at itself.
    """
    root = tmp_path / "solo"
    root.mkdir()
    r = _create(root, root)
    assert r.returncode == 0, r.stderr
    agent = root / ".claude" / "agents" / f"{ADVISOR}.md"
    assert agent.is_file() and not agent.is_symlink(), (
        "a colocated layout must get a real file — there is nowhere else to put it"
    )
    skill = root / ".claude" / "skills" / SKILL
    assert skill.is_dir() and not skill.is_symlink()

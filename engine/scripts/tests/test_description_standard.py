"""Every shipped description states a capability, not a routing mechanism.

Scope note: this pins what CODE ships — `agents/*.md`, `commands/*.md`,
`skills/*/SKILL.md` and the two identity templates. Advisor routers live in
DATA and are instance data; no engine test can pin them. They are held by the
generator instead (`advisor.create` → `router.scaffold_router`, one identity
string projected onto both surfaces) and by `engine doctor`.

The three failures this exists to catch, each observed on a real file:
  1. the plumbing stub — a description that describes the lifecycle it enters
     rather than what the agent is for ("Routes into the mandatory Conclave
     session lifecycle"), which is what every minted router carried;
  2. the derived stub — `{emoji} {role} advisor — {tone}`, which cannot answer
     "what will this help me with" because role and tone do not contain it;
  3. a ScannerError — an unquoted "Not for: ..." makes the whole frontmatter
     unparseable, so the description does not merely read badly, it vanishes.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]

# The Agent Skills spec validates the field itself at 1,024 chars. The 1,536
# figure quoted on the Claude Code skills page is a different thing — truncation
# of combined description + when_to_use inside the model's listing. The field
# limit is the one a file can actually violate.
DESCRIPTION_CAP = 1024

# The CLI's own frontmatter schema calls description a "one-line summary shown
# in listings and the Skill tool". Skills and commands render in the human `/`
# menu, so later lines are not designed to be seen there; agent-defs are read by
# the model in full and may run long.
HUMAN_MENU_SURFACES = ("commands", "skills")

PLUMBING_MARKERS = (
    "routes into the mandatory",
    "routes into the conclave",
)


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def _described(pattern: str) -> list[Path]:
    return sorted(p for p in REPO.glob(pattern) if p.is_file())


AGENT_DEFS = _described("agents/*.md")
COMMANDS = _described("commands/*.md")
SKILLS = _described("skills/*/SKILL.md")
ALL_SHIPPED = AGENT_DEFS + COMMANDS + SKILLS


def test_the_corpus_is_not_empty():
    """A glob that matches nothing passes every assertion below silently."""
    assert len(AGENT_DEFS) >= 7, AGENT_DEFS
    assert len(COMMANDS) >= 10, COMMANDS
    assert len(SKILLS) >= 3, SKILLS


@pytest.mark.parametrize("path", ALL_SHIPPED, ids=lambda p: p.name)
def test_frontmatter_parses_as_yaml(path: Path):
    """An unquoted ': ' inside a description takes the whole file down."""
    try:
        fm = _frontmatter(path)
    except yaml.YAMLError as e:  # pragma: no cover - the message is the point
        pytest.fail(f"{path.relative_to(REPO)}: frontmatter does not parse — {e}")
    assert fm, f"{path.relative_to(REPO)}: no frontmatter"


@pytest.mark.parametrize("path", ALL_SHIPPED, ids=lambda p: p.name)
def test_description_is_present_and_within_cap(path: Path):
    desc = (_frontmatter(path).get("description") or "").strip()
    assert desc, f"{path.relative_to(REPO)}: empty description"
    assert len(desc) <= DESCRIPTION_CAP, (
        f"{path.relative_to(REPO)}: {len(desc)} chars exceeds the {DESCRIPTION_CAP} cap"
    )


@pytest.mark.parametrize("path", ALL_SHIPPED, ids=lambda p: p.name)
def test_description_states_capability_not_routing(path: Path):
    desc = (_frontmatter(path).get("description") or "").lower()
    hit = next((m for m in PLUMBING_MARKERS if m in desc), None)
    assert hit is None, (
        f"{path.relative_to(REPO)}: description describes the mechanism it enters "
        f"({hit!r}), not what it is for"
    )


@pytest.mark.parametrize("path", AGENT_DEFS, ids=lambda p: p.name)
def test_agent_description_is_not_the_derived_stub(path: Path):
    """`{emoji} {role} advisor — {tone}` is the shape create() emits with no identity."""
    desc = (_frontmatter(path).get("description") or "").strip()
    assert not desc.endswith(" advisor — pragmatic"), (
        f"{path.relative_to(REPO)}: still carries the minted stub description"
    )


@pytest.mark.parametrize("path", COMMANDS + SKILLS, ids=lambda p: p.parent.name + "/" + p.name)
def test_human_menu_description_is_one_line(path: Path):
    """These render in the `/` picker, where only the first line is designed to show."""
    desc = (_frontmatter(path).get("description") or "").strip()
    assert "\n" not in desc, (
        f"{path.relative_to(REPO)}: multi-line description on a `/`-menu surface — "
        f"front-load it into one line ({len(desc.splitlines())} lines today)"
    )


@pytest.mark.parametrize("path", ALL_SHIPPED, ids=lambda p: p.name)
def test_description_is_third_person(path: Path):
    """Official style rule: first/second person breaks skill discovery."""
    desc = (_frontmatter(path).get("description") or "").lower()
    for banned in ("i can help", "i will ", "you can use this"):
        assert banned not in desc, (
            f"{path.relative_to(REPO)}: {banned!r} — descriptions are written in third person"
        )


def test_identity_templates_take_a_description_placeholder():
    """Both surfaces must render one supplied identity, not compose their own."""
    tpl_dir = REPO / "skills" / "forge-operations" / "references" / "templates"
    for name in ("agent-frontmatter.md", "advisor-router.md"):
        text = (tpl_dir / name).read_text(encoding="utf-8")
        assert "${DESCRIPTION}" in text, f"{name}: no ${{DESCRIPTION}} placeholder"
        assert not any(m in text.lower() for m in PLUMBING_MARKERS), (
            f"{name}: still hard-codes a routing description"
        )

"""The regression net that makes `collect()` extraction safe (plan 057 §4, T4).

Extraction has exactly one invariant: **the rendered briefing does not change.** Every
remaining task in plan 057 rewrites a `build()` into a formatter over a new `collect()`,
and until this file existed there was no instrument that would notice a row going
missing. The suite ran 2401 green with any such error in it.

WHY IT RENDERS THROUGH `render.build`, WHICH HAS NO PRODUCTION CALLER

Production is `engine/cmd/briefing.py` -> `briefing/__main__.py:main` -> `render_content`.
`render.build` is a second, test-only composition of the same 15 scans, and hanging a
golden on it would protect a path nothing ships through — except that
`test_dispatch_parity.py` holds the two dispatch literals byte-identical in keys and
order. The division is deliberate: parity keeps the two compositions equal, this file
keeps the scan outputs stable, and together they cover production. Delete the parity
gate and this net silently narrows to a path nobody runs.

WHY THE GOLDENS' PROVENANCE IS NOT THIS BRANCH

Captured by rendering the frozen instance against a worktree pinned at `e395235` —
master, before any of plan 057's commits. Capturing from the tree being edited verifies
nothing (session 2026-08-18), and this instance has shipped that mistake. The current
branch reproduces both files byte-for-byte, which is how the five 057 commits were shown
to be additive rather than merely believed to be.

REGENERATING: `CONCLAVE_UPDATE_GOLDEN=1 pytest <this file>` rewrites both files. Read the
diff before committing it — a golden regenerated to make a red test green is a deleted
test with extra steps.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from briefing import render
from briefing.scans import ScanCtx
from tests.briefing.synthetic_instance import ALPHA, BETA
from tests.briefing.synthetic_instance import build as build_instance

_GOLDEN_DIR = Path(__file__).resolve().parent / "golden"
_INSTANCE_TOKEN = "<INSTANCE>"


@pytest.fixture
def frozen_instance(tmp_path, monkeypatch):
    """The frozen tree, with every resolver the render reaches pinned to it.

    All three env vars are set explicitly rather than inherited. `CONCLAVE_ENGINE_ROOT`
    decides where the briefing template is found (CODE); `CONCLAVE_AI_ROOT` decides the
    absolute `hot.md` path that `render._hot_footer` interpolates into the body (DATA);
    `CLAUDE_PROJECT_DIR` is popped because `_agents_dir_for` consults it first and an
    ambient export would point a roster walk at the operator's live tree.

    The chdir is load-bearing, not tidiness: `code_repo` runs `git rev-parse` against the
    PROCESS cwd, and `current_work` runs `git log` against `repo_root`. Left alone, both
    would shell into the real checkout and the golden would carry its commit log.
    """
    instance = build_instance(tmp_path / "instance")
    # parents: [0]=tests/briefing [1]=tests [2]=scripts [3]=engine. The var names the
    # engine/ DIR; one segment too high resolves shipped assets into a sibling of the
    # checkout, and enginelib.paths raises EngineRootMismatchWarning saying so (GH#232).
    engine_root = Path(__file__).resolve().parents[3]
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine_root))
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(instance))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(instance)
    return instance


def _ctx(instance: Path, advisor: str) -> ScanCtx:
    """A ScanCtx over the frozen instance.

    Assembled here rather than via `briefing.paths` because the fixture's tree is not
    laid out as a `.conclave` sibling pair; the fields are the same ones
    `briefing/__main__.py:120-138` fills, in the same roles.
    """
    return ScanCtx(
        advisor=advisor,
        short_name=advisor.split("-")[0],
        repo_root=instance,
        decisions_dir=instance / "agent-memory" / "advisors" / "decisions",
        sessions_dir=instance / "agent-memory" / "advisors" / "sessions",
        mentions_dir=instance / "agent-memory" / "advisors" / "mentions",
        gh_cache_dir=instance / "agent-memory" / "gh-cache",
        personality_path=instance / ".claude" / "skills" / f"team.{advisor}" / "memory"
        / "personality.md",
        project_root=instance,
        plans_dir=instance / ".claude" / "plans",
    )


def _normalise(text: str, instance: Path) -> str:
    """Blank the wall-clock stamp and tokenise the instance path.

    BOTH spellings of the path are replaced, resolved first. On macOS `/tmp` is a
    symlink to `/private/tmp`, and `render._hot_footer` interpolates
    `hot_md_path()`, which resolves it — so a fixture rooted under `/tmp` renders
    `/private/tmp/...` while `str(tmp_path)` says `/tmp/...`. Replacing only the
    unresolved form leaves a one-line diff that looks like a real divergence and is
    not; that is exactly how this comparison first failed.
    """
    text = render._normalize_for_compare(text)  # noqa: SLF001
    for spelling in (str(instance.resolve()), str(instance)):
        text = text.replace(spelling, _INSTANCE_TOKEN)
    return text


def _render(instance: Path, advisor: str, tmp_path: Path) -> str:
    """Render one briefing and normalise the two parts that cannot be frozen.

    `generated_at` is a wall-clock stamp; the hot.md footer carries the instance's
    ABSOLUTE path. Both are normalised rather than removed — a golden that drops them
    would stop noticing if the stamp or the footer disappeared entirely.
    """
    out = tmp_path / f"{advisor}.rendered"
    render.build(_ctx(instance, advisor), out)
    return _normalise(out.read_text(encoding="utf-8"), instance)


@pytest.mark.parametrize("advisor", [ALPHA, BETA])
def test_the_rendered_briefing_is_unchanged(frozen_instance, tmp_path, advisor):
    rendered = _render(frozen_instance, advisor, tmp_path)
    golden_path = _GOLDEN_DIR / f"{advisor}.md"

    if os.environ.get("CONCLAVE_UPDATE_GOLDEN") == "1":
        golden_path.write_text(rendered, encoding="utf-8")
        pytest.skip(f"golden regenerated: {golden_path.name}")

    assert golden_path.is_file(), (
        f"{golden_path} is missing — regenerate with CONCLAVE_UPDATE_GOLDEN=1 and READ "
        "the diff; a golden created to make a red test green is a deleted test"
    )
    assert rendered == golden_path.read_text(encoding="utf-8"), (
        f"the rendered briefing for {advisor} differs from its golden. If the change is "
        "intended, regenerate with CONCLAVE_UPDATE_GOLDEN=1 and put the diff in the commit."
    )


# ---------------------------------------------------------------------------
# The net's intent, asserted separately from the byte comparison
# ---------------------------------------------------------------------------
#
# A golden file records WHAT the output is and says nothing about WHY that output is
# correct. Regenerated carelessly it happily records a defect. These three tests are
# the properties the fixture was built to expose, stated so they survive a regeneration.


def test_a_p0_on_one_advisor_is_invisible_to_the_other(frozen_instance, tmp_path):
    """The executed defect of plan 057 §2, captured as output.

    `p0.py`'s section is titled "Global p0 blockers" and reads exactly one advisor's
    cache. In this tree the only p0 sits on beta, so the same instance at the same
    moment answers the question two different ways. Asserted as the CURRENT behaviour,
    not the desired one — when the scan is fixed this test is what must be edited, in
    the same commit, on purpose.
    """
    alpha = _render(frozen_instance, ALPHA, tmp_path)
    beta = _render(frozen_instance, BETA, tmp_path)
    assert "#202" in beta, "beta's own p0 vanished from beta's briefing"
    assert "#202" not in alpha, (
        "alpha now sees beta's p0 — if this was fixed deliberately, update this test and "
        "the goldens together; if not, an advisor filter was widened by accident"
    )


def test_one_handoff_appears_in_every_advisors_briefing(frozen_instance, tmp_path):
    """`interrupted.py` reads no advisor field, and that is deliberate (its docstring).

    The handoff is addressed to alpha and written by beta, yet must appear in both —
    which is the only way a net can tell an instance-wide section from an
    advisor-scoped one. A single-advisor fixture cannot see this at all.
    """
    handoff = "2026-01-05-beta-coo-to-alpha-cto-resume.md"
    for advisor in (ALPHA, BETA):
        assert handoff in _render(frozen_instance, advisor, tmp_path), (
            f"the instance-wide handoff is missing from {advisor}'s briefing"
        )


def test_a_retired_owner_id_lands_on_neither_advisor(frozen_instance, tmp_path):
    """GH#253: three predicates answer "does this spec belong to advisor X" and disagree.

    Spec 013 is owned by `forge`, a retired id that `_specfm` maps to `forge-chro` —
    who is on neither advisor's roster here. It must therefore appear in neither
    briefing. If a predicate change makes it appear in one, that is the disagreement
    GH#253 describes, arriving as a diff instead of as a surprise.
    """
    for advisor in (ALPHA, BETA):
        rendered = _render(frozen_instance, advisor, tmp_path)
        assert "013" not in rendered, f"spec 013 (owner: forge) surfaced under {advisor}"


@pytest.mark.parametrize("advisor", [ALPHA, BETA])
def test_the_production_entrypoint_renders_the_same_briefing(frozen_instance, advisor):
    """`briefing/__main__.py:main` — what `engine briefing build` actually runs.

    The parity gate holds the two dispatch DICTS equal, statically. It says nothing
    about the rest of the divergence: production builds its own `ScanCtx` from
    `briefing.paths` + `enginelib.advisors.personality_path` (__main__.py:120-138),
    gates the advisor against the on-disk registry, and resolves its own output path,
    while `render.build` is handed a ctx it never constructs. A resolver drifting
    inside that construction would leave the parity gate green, the golden above
    green, and production broken — so the claim "this net covers production" is
    asserted here directly rather than inferred from composition.

    Measured 2026-09-09 on this fixture: byte-identical to the `render.build` render.
    """
    from briefing.__main__ import main as briefing_main

    assert briefing_main([advisor]) == 0, "the production entry point refused the advisor"
    written = (
        frozen_instance / "agent-memory" / "advisors" / "briefings" / f"{advisor}.md"
    )
    assert written.is_file(), f"{written} was not written"
    rendered = _normalise(written.read_text(encoding="utf-8"), frozen_instance)
    assert rendered == (_GOLDEN_DIR / f"{advisor}.md").read_text(encoding="utf-8"), (
        f"the production path renders {advisor}'s briefing differently from the golden"
    )

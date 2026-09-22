"""GH#269 — the section titled "Global p0 blockers" must be global, and must be p0.

Two defects live in one `build()`, and they are joined at the hip:

1. **Scope.** The section read exactly one path, `gh_cache_dir / f"{advisor}.md"`, so a
   p0 on another advisor rendered as `_(no global p0 blockers)_`. The same instance at
   the same moment answered the question differently per reader.
2. **Predicate.** It matched ``"p0" in row`` over the joined ``#num | title | labels``
   string, so an issue whose TITLE contains "p0" was rendered as a p0 blocker.

The second is why the first could not be fixed alone. `p0.py`'s docstring deferred the
predicate on a measurement — "Measured on this instance 2026-09-09: substring 0, label 0,
so the two definitions are indistinguishable here today". Re-measured 2026-09-20 across
all five live caches: substring **1**, label **0**. The one row the section rendered on
this instance was GH#269 itself — labelled `p1`, matched on the "p0" in its title.
Widening the scope without fixing the predicate would have broadcast that false positive
from one briefing to every briefing in the instance.

WHY THE ROSTER IS NOT DERIVED FROM THE CACHE DIRECTORY

The tempting discovery — ``gh_cache_dir.glob("*.md")`` — is the wrong instrument for
exactly the reason #104 names: a roster read off the caches can only ever enumerate
caches that exist, so "this advisor was never snapshotted" becomes unrepresentable. The
union would silently shrink to whoever happened to have run gh-fetch and still call
itself instance-wide, which is the §2 defect wearing a wider hat. The roster comes from
`lifecycle_advisors`; a member with no snapshot is reported as a gap, not as a zero.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from briefing.scans import ScanCtx, p0, queue
from tests.briefing.synthetic_instance import (
    ALPHA,
    BETA,
    _gh_cache,  # noqa: PLC2701
)
from tests.briefing.synthetic_instance import build as build_instance

# `_gh_cache` is imported rather than re-written here on purpose: the snapshot's
# frontmatter shape (`captured_at`, the json fence) is read by `captured_at()` and
# `read_items()`, and a second hand-written copy of it in this file would drift
# from the producer the day either changes.

FORGE = "forge-chro"  # META, on every lifecycle roster, with no cache in this fixture


@pytest.fixture
def instance(tmp_path, monkeypatch):
    """The frozen synthetic tree with every roster resolver pinned to it.

    `CLAUDE_PROJECT_DIR` is popped because `_agents_dir_for` consults it first; left
    ambient, the roster walk would enumerate the operator's live advisors and this file
    would pass or fail depending on who is hired today.
    """
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    return build_instance(tmp_path / "instance")


def _ctx(root: Path, advisor: str | None) -> ScanCtx:
    """A ScanCtx over the frozen tree; `advisor=None` builds the instance-scope shape.

    `scope` is derived rather than passed: ScanCtx's own __post_init__ refuses the two
    contradictory constructions (a named advisor under instance scope, a nameless one
    under advisor scope), so a helper that let a caller set them independently would
    just move the error one frame out.
    """
    return ScanCtx(
        advisor=advisor,
        scope="advisor" if advisor else "instance",
        short_name=advisor.split("-")[0] if advisor else "",
        repo_root=root,
        decisions_dir=root / "agent-memory" / "advisors" / "decisions",
        sessions_dir=root / "agent-memory" / "advisors" / "sessions",
        mentions_dir=root / "agent-memory" / "advisors" / "mentions",
        gh_cache_dir=root / "agent-memory" / "gh-cache",
        personality_path=root / ".claude" / "skills" / f"team.{advisor}" / "memory"
        / "personality.md",
        project_root=root,
        plans_dir=root / ".claude" / "plans",
    )


def _cache(root: Path, advisor: str) -> Path:
    return root / "agent-memory" / "gh-cache" / f"{advisor}.md"


def _issue(number: int, title: str, labels: list[str], repo: str = "synthetic") -> dict:
    return {
        "number": number,
        "title": title,
        "labels": [{"name": name} for name in labels],
        "repository": {"name": repo},
    }


# ---------------------------------------------------------------------------
# Anti-vacuity: the fixture must actually carry the shape these tests measure
# ---------------------------------------------------------------------------


def test_the_fixture_puts_the_only_p0_on_the_other_advisor(instance):
    """Without this, every assertion below is true of an empty tree.

    `synthetic_instance` states this pairing in prose ("beta holds the p0; alpha must
    not show it"). Prose in a fixture is a comment; this is the same claim executed, so
    a future edit that moves the p0 onto alpha reddens here instead of quietly turning
    the whole file into a tautology.
    """
    alpha_items = queue.collect(_ctx(instance, ALPHA))
    beta_items = queue.collect(_ctx(instance, BETA))
    assert alpha_items, "alpha's cache is empty — the fixture stopped carrying a queue"
    assert beta_items, "beta's cache is empty — the fixture stopped carrying a queue"
    assert p0.select(alpha_items) == [], "the fixture's p0 moved onto alpha"
    assert len(p0.select(beta_items)) == 1, "beta no longer holds exactly one p0"


def test_the_meta_advisor_is_on_the_roster_and_has_no_cache(instance):
    """The gap path needs a member of the roster with no snapshot, or it covers nothing.

    `lifecycle_advisors` is `known_advisors | META_ADVISORS`, so forge-chro is on every
    instance's roster whether or not it was ever hired — and this fixture writes no
    cache for it. That pairing is what makes the "snapshot not taken" branch reachable
    here at all; if either half stops holding, the gap assertions below go vacuous.
    """
    from enginelib.advisors import lifecycle_advisors

    roster = lifecycle_advisors(instance)
    assert roster == {ALPHA, BETA, FORGE}, f"roster changed shape: {sorted(roster)}"
    assert not _cache(instance, FORGE).exists(), "the fixture grew a forge-chro cache"


# ---------------------------------------------------------------------------
# Defect 1 — scope
# ---------------------------------------------------------------------------


def test_a_p0_on_one_advisor_is_visible_to_every_advisor(instance):
    """The inversion of the §2 defect: one instance, one answer.

    The old behaviour is the interesting control here — alpha's briefing said
    `_(no global p0 blockers)_` while beta's, from the same tree at the same instant,
    said "Delivery is on fire".
    """
    alpha = p0.build(_ctx(instance, ALPHA))
    beta = p0.build(_ctx(instance, BETA))
    assert "#202" in alpha, "alpha still cannot see beta's p0 — the section is not global"
    assert "#202" in beta, "beta lost its own p0"


def test_the_section_is_not_a_filtered_copy_of_the_queue_above_it(instance):
    """Why the fix is "make it global" and not "rename it to what it measures".

    Advisor-scoped, this section read the same file as `## My open queue` two sections
    higher and printed a subset of the very rows already printed there — it could not
    carry a single line the briefing did not already have. Renaming it would have been
    honest and empty. The section earns its place only by naming a fire the reader's own
    queue does not.
    """
    ctx = _ctx(instance, ALPHA)
    own_queue = queue.build(ctx)
    blockers = p0.build(ctx)
    assert "#202" in blockers and "#202" not in own_queue, (
        "the p0 section carries nothing the advisor's own queue does not — "
        "in that state it is a filtered duplicate, not a section"
    )


def test_the_rows_and_the_shared_predicate_cannot_disagree(instance):
    """One definition of "p0", two printers over it.

    `select()` was split out of `collect()` so the status projection and this section
    would share a predicate. A gate that only checks the rendering lets the two drift
    back apart silently — which is exactly how the substring/label divergence came to
    exist. This asserts the rendered set IS the union of `select()` over the roster.
    """
    from enginelib.advisors import lifecycle_advisors

    expected = set()
    for advisor in lifecycle_advisors(instance):
        if not _cache(instance, advisor).exists():
            continue
        for item in p0.select(queue.collect(_ctx(instance, advisor))):
            expected.add(queue.issue_identity(item))

    rendered = p0.build(_ctx(instance, ALPHA))
    for identity in expected:
        assert identity in rendered, f"{identity} passed select() but was not rendered"
    assert len(expected) == sum(
        1 for line in rendered.splitlines() if line.startswith("- synthetic#")
    ), "the rendering holds rows that no select() produced"


def test_a_p0_row_names_its_repo(instance):
    """`#57` is not an identity on an instance that runs two repos.

    `queue.issue_identity`'s own docstring says so — conclave#57 and conclave-ai#57 are
    different issues. The advisor-scoped section rendered a bare `#202` while the queue
    section two lines above rendered `synthetic#202`, for the same issue, in the same
    briefing. Instance-wide the ambiguity stops being cosmetic: the rows now come from
    five caches and nothing else on the line says which repo is on fire.
    """
    assert "synthetic#202" in p0.build(_ctx(instance, ALPHA))


def test_the_same_issue_in_two_caches_is_listed_once(instance):
    """Dedup on identity, not on number.

    Cache membership is an `advisor:` label query and a label set is not exclusive, so
    one issue can legitimately sit in two caches. Measured on this instance 2026-09-20:
    164 rows, 164 distinct identities, zero overlap — so live data cannot exercise this
    and a hermetic pair is the only way to hold the property.
    """
    shared = _issue(303, "Both of us own this fire", ["p0", f"advisor:{ALPHA}", f"advisor:{BETA}"])
    _gh_cache(_cache(instance, ALPHA), ALPHA, [shared])
    _gh_cache(_cache(instance, BETA), BETA, [shared])

    rendered = p0.build(_ctx(instance, ALPHA))
    assert rendered.count("#303") == 1, f"issue #303 rendered twice:\n{rendered}"


# ---------------------------------------------------------------------------
# Defect 2 — predicate
# ---------------------------------------------------------------------------


def test_the_label_decides_not_the_letters_in_a_title(instance):
    """The live false positive, reproduced with the shape that produced it.

    GH#269's own title — "'Global p0 blockers' reads one advisor's cache and calls it
    global" — contains the characters "p0" and the issue is labelled `p1`. Under the
    substring predicate it was the ONLY row this section rendered on the live instance.
    """
    _gh_cache(
        _cache(instance, ALPHA),
        ALPHA,
        [
            _issue(269, "'Global p0 blockers' reads one cache and calls it global",
                   ["p1", f"advisor:{ALPHA}"]),
            _issue(270, "Production is down", ["p0", f"advisor:{ALPHA}"]),
        ],
    )
    rendered = p0.build(_ctx(instance, ALPHA))
    assert "#270" in rendered, "a p0-labelled issue went missing"
    assert "#269" not in rendered, (
        "a p1 issue is rendered as a p0 blocker because its TITLE contains 'p0'"
    )


def test_a_p0_whose_title_says_nothing_is_still_a_p0(instance):
    """The other half of the substring predicate, which no live row exercises.

    Every p0-labelled row the substring matched, it matched through the LABELS segment
    of the joined string, so the two predicates agreed by accident on every true
    positive. That accident is not a property — it holds only while the label is
    rendered into the same string the predicate reads.
    """
    _gh_cache(
        _cache(instance, ALPHA), ALPHA,
        [_issue(404, "Everything is quietly on fire", ["bug", f"advisor:{ALPHA}"])],
    )
    _gh_cache(
        _cache(instance, BETA), BETA,
        [_issue(405, "Silent blocker", ["p0", f"advisor:{BETA}"])],
    )
    rendered = p0.build(_ctx(instance, ALPHA))
    assert "#405" in rendered
    assert "#404" not in rendered


# ---------------------------------------------------------------------------
# The gap — a cache that was never taken is not an empty cache
# ---------------------------------------------------------------------------


def test_an_advisor_with_no_snapshot_is_named_not_counted_as_zero(instance):
    """#104, in the one place where widening the read makes it worse.

    Advisor-scoped, a missing cache mis-reported one advisor's own queue and the reader
    was the person best placed to notice. Instance-wide, the same silence becomes a
    claim about four other people's fires made by an instrument that did not look at
    them — and the reader has no way to tell it from a real all-clear.
    """
    _cache(instance, BETA).unlink()
    rendered = p0.build(_ctx(instance, ALPHA))
    assert BETA in rendered, f"beta's missing snapshot is not named:\n{rendered}"
    assert rendered != "_(no global p0 blockers)_", (
        "a roster the scan could not read renders as a clean instance-wide all-clear"
    )


def test_the_all_clear_is_reserved_for_a_roster_that_was_fully_read(instance):
    """The placeholder is a claim, and it needs every shard to be entitled to it.

    The fixture always has a gap (forge-chro is on the roster with no cache), so the
    unqualified all-clear must NOT appear here — and must appear once the gap is closed
    with a real, empty snapshot. Both directions are asserted: a placeholder that never
    fires and one that always fires are indistinguishable from a single-sided test.
    """
    _gh_cache(_cache(instance, BETA), BETA, [])  # beta's p0 gone, snapshot still taken
    with_gap = p0.build(_ctx(instance, ALPHA))
    assert with_gap != "_(no global p0 blockers)_", "the forge-chro gap went unreported"
    assert FORGE in with_gap

    _gh_cache(_cache(instance, FORGE), FORGE, [])  # roster now fully snapshotted
    _gh_cache(_cache(instance, ALPHA), ALPHA, [])
    assert p0.build(_ctx(instance, ALPHA)) == "_(no global p0 blockers)_"


def test_the_roster_is_not_read_off_the_cache_directory(instance):
    """The gap must survive the discovery that would define it away.

    `gh_cache_dir.glob("*.md")` is the obvious way to find "whose caches exist", and it
    is unfalsifiable by construction: it cannot produce a member it failed to find. This
    holds the distinction as behaviour — an advisor that IS on the roster and has NO
    file must appear in the output, which no glob-derived roster can do.
    """
    present = {p.stem for p in (instance / "agent-memory" / "gh-cache").glob("*.md")}
    assert FORGE not in present, "the fixture grew the file this test needs absent"
    assert FORGE in p0.build(_ctx(instance, ALPHA)), (
        "an advisor with no cache file is invisible — the roster is being derived from "
        "the caches, so a missing snapshot can never be reported"
    )


def test_a_roster_that_lost_the_reader_is_reported_not_rendered(instance):
    """The mis-resolved root, which degrades to a confident all-clear over one cache.

    `known_advisors` is empty-safe by design — a missing `.claude/agents/` yields an
    empty set rather than raising — so `lifecycle_advisors` on a wrong root returns
    `{forge-chro}` alone. Without this guard the section would then walk one cache, find
    nothing, and print the unqualified all-clear: the §2 defect restored through a
    different door, narrower than before and completely silent.

    The reading advisor is the one roster member guaranteed to exist, which makes them a
    free check on the resolution. This is the `self-confirming root marker` lesson
    (2026-08-18) applied in reverse: there the marker matched both trees and proved
    nothing; here the reader's own absence is what cannot be faked.
    """
    for agent_file in (instance / ".claude" / "agents").glob("*.md"):
        agent_file.unlink()

    rendered = p0.build(_ctx(instance, ALPHA))
    assert rendered != p0.NO_BLOCKERS, (
        "an unresolvable roster renders as a clean instance-wide all-clear"
    )
    assert ALPHA in rendered and "not resolvable" in rendered


def test_the_guard_does_not_fire_on_a_roster_that_holds_the_reader(instance):
    """The other side, or the guard above is satisfied by a function that always fires.

    A check that reddens on every input is not a check. This pins that the normal path —
    reader on the roster — reaches the walk and renders rows.
    """
    rendered = p0.build(_ctx(instance, ALPHA))
    assert "not resolvable" not in rendered
    assert "synthetic#202" in rendered


def test_every_reader_of_one_instance_gets_the_same_answer(instance):
    """The invariant the heading promises, stated as an equality rather than a sample.

    `test_a_p0_on_one_advisor_is_visible_to_every_advisor` checks that one known issue
    crosses; this checks that NOTHING is reader-dependent — including the gap lines and
    the ordering. A section that is global for the rows and advisor-scoped for the
    caveats would pass the first test and fail this one.

    The reader-less (instance-scope) rendering is in the comparison on purpose: it is
    the shape `engine status` would reach, and if it differed the two surfaces would
    disagree about the same instance at the same instant.
    """
    answers = {
        label: p0.build(_ctx(instance, reader))
        for label, reader in ((ALPHA, ALPHA), (BETA, BETA), ("instance", None))
    }
    assert len(set(answers.values())) == 1, (
        "one instance, more than one answer:\n"
        + "\n".join(f"--- {k} ---\n{v}" for k, v in answers.items())
    )

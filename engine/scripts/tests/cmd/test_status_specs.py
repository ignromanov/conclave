"""`engine status` — the specs slot (plan 057 T10), and the partition under it.

Every test here is named by the mutation it must redden under, because the defect
class this slot exists to retire is an instrument that passes while not looking. The
one that matters most is the last: strip the scan's call site and the row must say `—`
with a reason, never the `0` that reads like an empty corpus.
"""
from __future__ import annotations

import pytest

from briefing.scans import ScanCtx, spec_progress
from engine.cmd import status as status_cmd
from enginelib.status.model import Absent, Count
from enginelib.status.render_terminal import glance, quantity, work
from enginelib.status.specs import SpecAcceptance, SpecTally, classify, tally

# --- the pure partition -----------------------------------------------------------


def test_classify_is_total_over_the_four_states_the_corpus_holds():
    """Mutation: drop any branch of `classify` and one of these four reddens."""
    assert classify(owner_field=None, has_acceptance_block=True, total=3) == "unowned"
    assert classify(owner_field="owner", has_acceptance_block=False, total=0) == "no_acceptance"
    assert classify(owner_field="owner", has_acceptance_block=True, total=0) == "no_checkboxes"
    assert classify(owner_field="owner", has_acceptance_block=True, total=3) == "measured"


def test_ownership_is_reported_before_acceptance_because_it_ran_first():
    """A spec that is both unowned and blockless is `unowned`, not `no_acceptance`.

    Mutation: swap the first two branches of `classify` and this reddens. Naming the
    later cause would report a check that never ran — the ownership filter drops the
    file before the acceptance parse is reached.
    """
    assert classify(owner_field=None, has_acceptance_block=False, total=0) == "unowned"


def test_a_measured_spec_cannot_be_built_without_its_counts():
    """Mutation: delete the `measured` guard in `__post_init__` and this reddens.

    `done=None` on a measured spec is the absence/zero collapse one layer below the
    printer — the type refuses it so no printer has to remember.
    """
    with pytest.raises(ValueError, match="carries its counts"):
        SpecAcceptance(spec_id="042", title="t", klass="measured")


def test_an_uncomputable_spec_cannot_smuggle_a_zero_in_its_counts():
    """`no_checkboxes` with `total=0` would render identically to ten unticked boxes."""
    with pytest.raises(ValueError, match="carries no counts"):
        SpecAcceptance(spec_id="042", title="t", klass="no_checkboxes", done=0, total=0)


def test_a_spec_in_no_class_is_refused_rather_than_lost():
    """The partition invariant. Mutation: delete the sum check and a lost spec is silent.

    This is the whole defect in one assertion — a spec counted in the total and in no
    class is exactly how twelve of this instance's thirty-one became invisible.
    """
    with pytest.raises(ValueError, match="lost 1 spec"):
        SpecTally(total=3, by_class={"measured": 2}, boxes_done=1, boxes_total=4)


def test_the_proof_breakdown_renders_zero_classes_rather_than_omitting_them():
    """Rule 3 on an inventory surface: `0 без блока приёмки` is the answer, not silence.

    Mutation: filter the zero classes out of `proof_breakdown` and this reddens.
    """
    counted = tally([
        SpecAcceptance(spec_id="1", title="a", klass="measured",
                       owner_field="owner", done=1, total=2),
    ])
    breakdown = counted.proof_breakdown()
    assert "1 вычислимо" in breakdown
    assert "0 без блока приёмки" in breakdown
    assert "0 без поля владельца" in breakdown


def test_only_measured_specs_contribute_checkboxes():
    counted = tally([
        SpecAcceptance(spec_id="1", title="a", klass="measured",
                       owner_field="owner", done=1, total=4),
        SpecAcceptance(spec_id="2", title="b", klass="no_checkboxes", owner_field="owner"),
        SpecAcceptance(spec_id="3", title="c", klass="unowned"),
    ])
    assert (counted.total, counted.measured, counted.uncomputable) == (3, 1, 2)
    assert (counted.boxes_done, counted.boxes_total) == (1, 4)


# --- the scan ---------------------------------------------------------------------


def _ctx(root, advisor):
    return ScanCtx(
        advisor=advisor,
        short_name=advisor.split("-")[0] if advisor else "",
        scope="advisor" if advisor else "instance",
        repo_root=root,
        decisions_dir=root / "d", sessions_dir=root / "s", mentions_dir=root / "m",
        gh_cache_dir=root / "g", personality_path=root / "p",
        project_root=root, plans_dir=root / "pl",
    )


def _spec(root, slug, frontmatter, body=""):
    d = root / "ops" / "specs" / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "spec.md").write_text(f"---\n{frontmatter}\n---\n\n{body}", encoding="utf-8")


@pytest.fixture
def corpus(tmp_path):
    """One spec of each class, so every assertion below has something to lose."""
    _spec(tmp_path, "001-measured", 'id: "001"\ntitle: "M"\nowner: "sage-cto"',
          "## Acceptance\n\n- [x] one\n- [ ] two\n")
    _spec(tmp_path, "002-no-boxes", 'id: "002"\ntitle: "N"\nowner: "sage-cto"',
          "## 4. Acceptance criteria\n\nprose, no boxes\n")
    _spec(tmp_path, "003-no-block", 'id: "003"\ntitle: "B"\nowner: "sage-cto"',
          "## Design\n\nno acceptance heading at all\n")
    _spec(tmp_path, "004-unowned", 'id: "004"\ntitle: "U"\nstatus: "proposed"',
          "## Acceptance\n\n- [ ] one\n")
    return tmp_path


def test_instance_scope_keeps_the_specs_nobody_claimed(corpus):
    """Mutation: drop the `advisor is not None` guard in `_read_spec` and 004 vanishes.

    An instance total that silently excludes unowned specs is a total over an unstated
    subset. Measured on this instance 2026-09-15: three such specs, one of them 086,
    which the whole feedback notebook rests on.
    """
    by_id = {r.spec_id: r for r in spec_progress.collect(_ctx(corpus, None))}
    assert set(by_id) == {"001", "002", "003", "004"}
    assert by_id["004"].klass == "unowned"
    assert by_id["003"].klass == "no_acceptance"
    assert by_id["002"].klass == "no_checkboxes"
    assert (by_id["001"].done, by_id["001"].total) == (1, 2)


def test_advisor_scope_drops_what_is_not_this_advisors(corpus):
    """The asymmetry is the point: `owns()` answers None for 'someone else's' and
    'nobody's' alike, so only instance scope may tell them apart."""
    ids = {r.spec_id for r in spec_progress.collect(_ctx(corpus, "sage-cto"))}
    assert ids == {"001", "002", "003"}
    assert not spec_progress.collect(_ctx(corpus, "kosmos-cxo"))


def test_build_renders_only_the_classes_it_can_speak_a_sentence_about(corpus):
    """The extraction changed no output. Mutation: render `no_acceptance` here and the
    golden briefing net reddens — which is the only instrument covering this split."""
    rendered = spec_progress.build(_ctx(corpus, "sage-cto"))
    assert "**001**" in rendered and "1/2 ✓" in rendered
    assert "unverifiable — **002**" in rendered
    assert "**003**" not in rendered
    assert "**004**" not in rendered


# --- the section ------------------------------------------------------------------


def test_the_row_reports_reach_not_completion(corpus):
    """The glance number is how much the instrument can read, with the classes one hop
    away. Mutation: make `value` the count of DONE specs and both halves redden."""
    section = status_cmd._specs_section(corpus)
    m = section.measurement
    assert isinstance(m, Count)
    assert (m.value, m.of) == (1, 4)
    assert "1 вычислимо" in m.proof
    assert "1 без чекбоксов" in m.proof
    assert "1 без блока приёмки" in m.proof
    assert "1 без поля владельца" in m.proof


def test_an_uncomputable_spec_makes_the_verdict_unknown(corpus):
    """Rule 2 — uncertainty outranks known-bad. Mutation: return `fresh` unconditionally."""
    assert status_cmd._specs_section(corpus).verdict == "unknown"


def test_a_corpus_the_instrument_reads_whole_is_not_marked(tmp_path):
    """The mirror of the test above: without it, a verdict hardcoded to `unknown`
    would pass every other assertion in this file."""
    _spec(tmp_path, "001-ok", 'id: "001"\ntitle: "M"\nowner: "sage-cto"',
          "## Acceptance\n\n- [x] one\n")
    section = status_cmd._specs_section(tmp_path)
    assert section.verdict == "fresh"
    assert isinstance(section.measurement, Count)


def _assert_reads_as_absent(section):
    """The row renders as `— <reason>`, never as a count.

    Asserted on the rendered QUANTITY rather than by grepping the block for a zero.
    A substring search over the whole render cannot tell the row's value from prose
    inside the reason — "сканер вернул 0 из 4" legitimately contains a zero, and the
    grep version of this check failed on a correct render. An instrument that reddens
    on the sentence explaining the gap is not measuring the gap.
    """
    assert isinstance(section.measurement, Absent), "the slot rendered a number"
    assert section.measurement.reason.strip()
    assert section.verdict == "unknown"
    rendered = quantity(section.measurement)
    assert rendered.startswith("— "), rendered
    assert "спек с вычислимой приёмкой" not in rendered, "a Count's noun reached an Absent row"
    assert f"**{section.name}**  {rendered}" in glance(
        "engine", "🦉", "состояние", "15.09", [section]
    )


def test_a_missing_specs_tree_is_absent_with_a_reason_never_zero(tmp_path):
    _assert_reads_as_absent(status_cmd._specs_section(tmp_path))


def test_an_empty_specs_tree_is_a_measured_zero_not_an_absence(tmp_path):
    """The pair to the test above. A directory that exists and holds nothing was
    LOOKED AT, and rule 6 gives that a `0`. Collapsing the two is the SQL-NULL trap."""
    (tmp_path / "ops" / "specs").mkdir(parents=True)
    section = status_cmd._specs_section(tmp_path)
    m = section.measurement
    assert isinstance(m, Count)
    assert (m.value, m.of) == (0, 0)


def test_a_scan_that_reaches_fewer_specs_than_the_disk_holds_refuses_to_report_a_ratio(
    corpus, monkeypatch
):
    """**The acceptance criterion, as a mutation.**

    Delete the scan's call site — here, make it return nothing — and the row must
    render `—` with a reason naming the gap. A `0` would be indistinguishable from an
    empty corpus, which is the sentence rule 6 forbids and the exact shape spec 109
    spent 37 days inside.

    The denominator comes from `glob` on disk, a source independent of the scan it
    checks, which is what makes this reachable at all.
    """
    monkeypatch.setattr(spec_progress, "collect", lambda ctx: [])
    section = status_cmd._specs_section(corpus)
    _assert_reads_as_absent(section)
    assert "0 из 4" in section.measurement.reason, "the reason must name the gap it found"


def test_a_partial_scan_is_refused_too_not_silently_scaled(corpus, monkeypatch):
    """One spec short is still a ratio over an unstated subset. Mutation: compare with
    `>` instead of `!=` and a scan losing specs reports a confident 1 of 3."""
    real = spec_progress.collect
    monkeypatch.setattr(spec_progress, "collect", lambda ctx: real(ctx)[:3])
    section = status_cmd._specs_section(corpus)
    assert isinstance(section.measurement, Absent)
    assert "3 из 4" in section.measurement.reason


def test_the_wired_specs_slot_left_the_unwired_map():
    """A slot cannot be both wired and declared unwired; the pair would drift."""
    assert "спеки" not in status_cmd._NOT_YET_WIRED


def test_the_work_layer_carries_the_partition_one_hop_from_the_glance(corpus):
    """Rule 5: every count names the file or command that reproduces it."""
    section = status_cmd._specs_section(corpus)
    body = work([section])
    assert "## спеки" in body
    assert "ops/specs/*/spec.md" in body
    assert "без поля владельца" in body

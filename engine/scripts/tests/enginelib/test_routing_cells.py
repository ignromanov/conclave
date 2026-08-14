"""Bare-kebab routing cells are visible to the gate (GH#123, plan-p1.md D-6).

The dropped prototype measured 44 findings of which ~10 were real — 77% noise — because it
recognised routing tables by HEADER VOCABULARY, matching every schema and prose table whose
header happened to contain "skill" or "chain". The discriminator is the header ROW, not the
words in it: `| Task Type | Skill Chain |` is an invocation table; a sentence saying "the skill
chain is carried from start" is description. Measured on this tree: the row form occurs once,
the prose form sixteen times.

The second discriminator already exists in the file. P1 introduced `†` to mark cells that are
unprefixed on purpose — user-level skills in the operator's private `~/.claude/skills`, shipped
by no plugin and unverifiable from the distribution. So the rule closes: a cell is prefixed, or
marked, or prose.
"""
from enginelib.audit import routing_targets as rt

_HEADER = "| Task Type | Skill Chain |\n|-----------|-------------|\n"


def test_a_plugin_prefixed_cell_is_classified_prefixed():
    cells = rt.find_routing_cells(_HEADER + "| Bug fix | superpowers:systematic-debugging |\n")

    assert cells == [(3, "superpowers:systematic-debugging", "prefixed")]


def test_a_dagger_marked_bare_cell_is_exempt():
    """Unprefixed on purpose: user-level, absent on a fresh install, and start.md says so."""
    cells = rt.find_routing_cells(_HEADER + "| Security | senior-security † |\n")

    assert cells == [(3, "senior-security", "exempt")]


def test_an_unmarked_bare_cell_is_bare():
    """`doc-coauthoring` lived in start.md exactly like this and was found by hand, not by any
    instrument. Nothing prevented a successor until this test."""
    cells = rt.find_routing_cells(_HEADER + "| Grant | doc-coauthoring |\n")

    assert cells == [(3, "doc-coauthoring", "bare")]


def test_every_element_of_a_chain_is_classified_separately():
    cells = rt.find_routing_cells(
        _HEADER + "| New feature | superpowers:brainstorming → doc-coauthoring |\n"
    )

    assert cells == [
        (3, "superpowers:brainstorming", "prefixed"),
        (3, "doc-coauthoring", "bare"),
    ]


def test_a_prose_cell_yields_nothing():
    cells = rt.find_routing_cells(
        _HEADER + "| Meeting | the instance's facilitator slot, if one was hired |\n"
    )

    assert cells == []


def test_prose_outside_a_table_is_not_a_routing_cell():
    """The 77% noise, in one assertion. Without the header-row anchor this text alone would
    have produced a finding in the dropped prototype."""
    cells = rt.find_routing_cells(
        "Detect task type → load the required skill chain.\n"
        "The skill chain is carried from start, not re-detected.\n"
    )

    assert cells == []


def test_the_table_ends_where_the_table_ends(tmp_path):
    """A paragraph after the table must not be parsed as more rows."""
    cells = rt.find_routing_cells(
        _HEADER
        + "| Bug fix | superpowers:systematic-debugging |\n"
        + "\n"
        + "If no matching skill exists, search with find-skills.\n"
    )

    assert [c[1] for c in cells] == ["superpowers:systematic-debugging"]


def test_run_flags_a_bare_cell_and_leaves_the_others_alone(tmp_path):
    surface = tmp_path / "start.md"
    surface.write_text(
        _HEADER
        + "| Bug fix | superpowers:systematic-debugging |\n"
        + "| Security | senior-security † |\n"
        + "| Grant | doc-coauthoring |\n",
        encoding="utf-8",
    )

    findings = rt.run([surface], [], frozenset())

    bare = [c for c in findings.crit if "doc-coauthoring" in c]
    assert len(bare) == 1, findings.crit
    assert "start.md:5" in bare[0]
    assert not [c for c in findings.crit if "senior-security" in c]
    assert not [c for c in findings.crit if "systematic-debugging" in c]

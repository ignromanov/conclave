"""Which blocks of an auto-loaded file are closed, for whoever rotates it (spec 110, GH#369)."""
from __future__ import annotations

from enginelib.knowledge import rotation

DOC = """# Progress
preamble text
## Open work
### 0. Wizard — GH#102 closed 2026-09-04; PR 1.5 is the only remainder
see #150
### 3b. GH#224 — the whole section closed 2026-09-09
⛔ corrected twice
### 4. Live thing
tracks #300
### 5. Plain notes
nothing cited
"""


def test_blocks_split_on_h2_and_h3_with_line_and_bytes():
    bs = rotation.blocks(DOC)
    assert [b.heading for b in bs] == [
        "(preamble)", "Open work", "0. Wizard — GH#102 closed 2026-09-04; PR 1.5 is the only remainder",
        "3b. GH#224 — the whole section closed 2026-09-09", "4. Live thing", "5. Plain notes"]
    assert bs[3].refs == (224,) and bs[3].corrections == 2
    assert bs[2].line == 4
    assert sum(b.size for b in bs) == len(DOC.encode())


def test_open_ref_overrides_a_closed_heading():
    row = rotation.classify(rotation.blocks(DOC)[2], {102: "CLOSED", 150: "OPEN"})
    assert row.verdict == "keep" and "#150 OPEN" in row.reason


def test_self_declared_closed_block_is_a_candidate_that_must_not_be_deleted():
    row = rotation.classify(rotation.blocks(DOC)[3], {224: "CLOSED"})
    assert row.verdict == "candidate"
    assert "never delete" in row.reason


def test_unreachable_github_is_unknown_not_keep():
    row = rotation.classify(rotation.blocks(DOC)[4], None)
    assert row.verdict == "unknown"


def test_all_refs_closed_is_a_candidate_without_a_heading_word():
    b = rotation.blocks("## x\n### Thing\nsee #7 and PR #8\n")[1]
    assert rotation.classify(b, {7: "CLOSED", 8: "MERGED"}).verdict == "candidate"


def test_worklist_orders_candidates_first_and_never_offers_the_preamble():
    rows = rotation.worklist(DOC, {102: "CLOSED", 150: "OPEN", 224: "CLOSED", 300: "OPEN"})
    assert rows[0].verdict == "candidate"
    assert all(r.block.heading != "(preamble)" or r.verdict == "no-signal" for r in rows)


def test_a_closed_heading_with_an_unreadable_ref_is_unknown_not_candidate():
    # Review finding I1: the remainder (#150) may be open; a reading that did not happen
    # must not let the heading's own claim send it to the archive.
    b = rotation.blocks("## x\n### 5. Wizard — GH#102 closed; remainder tracked in #150\n")[1]
    offline = rotation.classify(b, None)
    partial = rotation.classify(b, {102: "CLOSED"})
    assert offline.verdict == "unknown" and "heading says closed" in offline.reason
    assert partial.verdict == "unknown"

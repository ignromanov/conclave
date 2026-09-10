"""#255 — repairing 38 session records whose frontmatter does not parse.

A session record is written once and never revised, and the reflexion is the only copy
of a lesson, so every test here is about what the migration must NOT do as much as
what it must.
"""
from __future__ import annotations

import textwrap

import yaml

from enginelib.lifecycle import migrate_session_yaml as m


def _write(root, name, text):
    p = root / name
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


def _parses(path):
    try:
        return isinstance(yaml.safe_load(path.read_text().split("---")[1]), dict)
    except yaml.YAMLError:
        return False


BROKEN_COLON = """\
    ---
    advisor: forge-chro
    date: 2026-07-05
    slug: a-slug
    decisions: []
    issues: [12]
    reflexion: The gate passed: the mutation did not.
    ---

    ## What happened

    body text that must not move
    """

BROKEN_HASH = """\
    ---
    advisor: forge-chro
    date: 2026-07-07
    slug: b-slug
    decisions: []
    issues: [#17,#18]
    mentions_resolved: []
    reflexion: a harmless reflexion
    ---

    body
    """


class TestRepairs:
    def test_a_colon_in_the_reflexion_is_repaired(self, tmp_path):
        p = _write(tmp_path, "a.md", BROKEN_COLON)
        assert not _parses(p)
        res = m.run(tmp_path)
        assert res.updated == 1, res
        assert _parses(p)
        meta = yaml.safe_load(p.read_text().split("---")[1])
        assert meta["reflexion"] == "The gate passed: the mutation did not."

    def test_hash_prefixed_ids_are_repaired(self, tmp_path):
        p = _write(tmp_path, "b.md", BROKEN_HASH)
        assert not _parses(p)
        res = m.run(tmp_path)
        assert res.updated == 1, res
        meta = yaml.safe_load(p.read_text().split("---")[1])
        assert len(meta["issues"]) == 2, meta["issues"]
        # The key the parser blamed is two lines below the real fault; pin it survives.
        assert meta["mentions_resolved"] == []

    def test_the_body_is_never_touched(self, tmp_path):
        p = _write(tmp_path, "a.md", BROKEN_COLON)
        body_before = p.read_text().split("\n---\n", 1)[1]
        m.run(tmp_path)
        assert p.read_text().split("\n---\n", 1)[1] == body_before

    def test_untouched_fields_stay_byte_identical(self, tmp_path):
        p = _write(tmp_path, "a.md", BROKEN_COLON)
        m.run(tmp_path)
        text = p.read_text()
        for line in ("advisor: forge-chro", "date: 2026-07-05", "slug: a-slug",
                     "decisions: []", "issues: [12]"):
            assert line in text, f"{line!r} was rewritten by a migration that had no business with it"


class TestRefusals:
    def test_a_record_that_already_parses_is_skipped(self, tmp_path):
        p = _write(tmp_path, "ok.md", """\
            ---
            advisor: forge-chro
            reflexion: nothing wrong here
            ---
            body
            """)
        before = p.read_text()
        res = m.run(tmp_path)
        assert res.updated == 0 and res.skipped == 1
        assert p.read_text() == before

    def test_a_folded_block_scalar_is_left_folded(self, tmp_path):
        """A `>-` reflexion joins its lines with spaces; re-emitting it as `|-` joins
        them with newlines. The record parses either way, so GATE-1 cannot see the
        difference -- which is why the rule is per-field, not per-file: only a field
        that fails ON ITS OWN is rewritten."""
        p = _write(tmp_path, "folded.md", """\
            ---
            advisor: forge-chro
            issues: [#17]
            reflexion: >-
              first line
              second line
            ---
            body
            """)
        assert not _parses(p)
        res = m.run(tmp_path)
        assert res.updated == 1
        assert _parses(p)
        assert "reflexion: >-" in p.read_text(), "the folded indicator was rewritten"
        meta = yaml.safe_load(p.read_text().split("---")[1])
        assert meta["reflexion"] == "first line second line"

    def test_a_file_without_frontmatter_is_skipped(self, tmp_path):
        p = _write(tmp_path, "plain.md", "just a note\n")
        res = m.run(tmp_path)
        assert res.updated == 0 and res.skipped == 1
        assert p.read_text() == "just a note\n"

    def test_a_repair_that_would_change_a_value_is_refused(self, tmp_path, monkeypatch):
        """The gate is the point. If the rewrite alters any field the line reader can
        see, the file is left broken and reported -- a corrupted lesson is worse than
        an unparseable one, because it looks fine."""
        p = _write(tmp_path, "a.md", BROKEN_COLON)
        monkeypatch.setattr(m.frontmatter, "as_block",
                            lambda value, indent=2, chomp=False: "|-\n  something else")
        before = p.read_text()
        res = m.run(tmp_path)
        assert res.updated == 0
        assert len(res.failed) == 1, res
        assert "changed" in res.failed[0][1]
        assert p.read_text() == before, "a refused repair must not write"


class TestOperationalContract:
    def test_dry_run_writes_nothing_and_names_every_file(self, tmp_path):
        a = _write(tmp_path, "a.md", BROKEN_COLON)
        b = _write(tmp_path, "b.md", BROKEN_HASH)
        snap = {p.name: p.read_text() for p in (a, b)}
        res = m.run(tmp_path, dry_run=True)
        assert res.updated == 0
        assert len(res.would_update) == 2, res.would_update
        for p in (a, b):
            assert p.read_text() == snap[p.name], f"{p.name} was written during a dry run"

    def test_running_twice_changes_nothing_the_second_time(self, tmp_path):
        _write(tmp_path, "a.md", BROKEN_COLON)
        _write(tmp_path, "b.md", BROKEN_HASH)
        first = m.run(tmp_path)
        assert first.updated == 2
        snap = {p.name: p.read_text() for p in tmp_path.glob("*.md")}
        second = m.run(tmp_path)
        assert second.updated == 0 and second.skipped == 2
        for p in tmp_path.glob("*.md"):
            assert p.read_text() == snap[p.name]


class TestRepairChunkDirectly:
    """`migrate_text` protects a folded reflexion three times over -- `chunk_parses`
    skips it, `repair_chunk` refuses it, and the equality gate rejects the result --
    so no single-line mutation of any one of them reddens the file-level tests.
    Measured: disabling both guards is what finally trips the gate, with
    "field 'reflexion' changed: 'first line\\nsecond line' -> '>-\\nfirst line\\nsecond line'".

    Defence in depth is right for records that are written once and never revised,
    but it leaves each guard individually untested. These exercise repair_chunk on its own.
    """

    def test_a_block_scalar_chunk_is_refused_not_flattened(self):
        chunk = ["reflexion: >-", "  first line", "  second line"]
        assert m.repair_chunk(chunk) is None, (
            "a block scalar must be handed back untouched; rewriting it as |- turns "
            "space-joining into newline-joining, which parses and is still corruption")

    def test_a_flow_list_chunk_is_quoted(self):
        assert m.repair_chunk(["issues: [#17,#18]"]) == ["issues: ['#17','#18']"]

    def test_a_plain_scalar_chunk_becomes_a_block(self):
        got = m.repair_chunk(["reflexion: The gate passed: the mutation did not."])
        assert got[0] == "reflexion: |-"
        assert got[1] == "  The gate passed: the mutation did not."

    def test_a_line_that_is_not_a_key_is_refused(self):
        assert m.repair_chunk(["  stray continuation"]) is None

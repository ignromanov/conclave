"""#255 — repairing 38 session records whose frontmatter does not parse.

A session record is written once and never revised, and the reflexion is the only copy
of a lesson, so every test here is about what the migration must NOT do as much as
what it must.
"""
from __future__ import annotations

import textwrap

import yaml

from enginelib.audit import Findings
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


# --- #262: the record that PARSES and still lost its value -------------------------

TRUNCATED = """\
    ---
    advisor: sage-cto
    date: 2026-07-08
    slug: c-slug
    decisions: []
    issues: []
    reflexion: Verifying disk state killed two false findings (register.py already fixed by #68; owner lives in the review file) — reviews go stale.
    ---

    body
    """


def _reflexion(path):
    return yaml.safe_load(path.read_text().split("---")[1])["reflexion"]


class TestValueLossNotParseFailure:
    """The migration's entry condition was `yaml.safe_load(...) is a dict`, so a record
    that parses and reads back SHORT was never examined — not merely passed, skipped
    before the first chunk. `#` opens a comment, and 71% of one lesson went with it."""

    def test_a_record_that_parses_but_reads_back_truncated_is_repaired(self, tmp_path):
        p = _write(tmp_path, "t.md", TRUNCATED)
        assert _parses(p), "precondition: this record PARSES — that is the whole point"
        assert _reflexion(p).endswith("fixed by"), "precondition: and reads back truncated"

        m.run(tmp_path)
        assert "#68" in _reflexion(p)
        assert _reflexion(p).endswith("reviews go stale.")

    def test_the_repaired_value_equals_what_the_writer_was_given(self, tmp_path):
        p = _write(tmp_path, "t.md", TRUNCATED)
        written = TRUNCATED.split("reflexion: ", 1)[1].split("\n")[0]
        m.run(tmp_path)
        assert _reflexion(p) == written.strip()

    def test_a_truncated_record_is_counted_as_updated_not_skipped(self, tmp_path):
        _write(tmp_path, "t.md", TRUNCATED)
        res = m.run(tmp_path, dry_run=True)
        assert res.would_update, "a lossy record must be offered for repair"
        assert res.skipped == 0

    def test_a_record_that_parses_AND_loses_nothing_is_still_skipped(self, tmp_path):
        """The guard must narrow, not vanish: an intact record stays byte-identical."""
        clean = TRUNCATED.replace("by #68; owner", "by 68 -- owner")
        p = _write(tmp_path, "t.md", clean)
        before = p.read_bytes()
        res = m.run(tmp_path)
        assert res.skipped == 1 and res.updated == 0
        assert p.read_bytes() == before


BROKEN_MENTION = """\
    ---
    id: 2026-09-08-0419-a-to-b-something
    from: a
    to: b
    status: resolved
    resolved_note: Answered: the order, and one acceptance line I refuse as written.
    ---

    body
    """


class TestCorpusReach:
    """`audit records` walks sessions, decisions AND mentions; the repair globbed one
    directory, non-recursively. Five of the twelve live findings are mentions, nested
    two levels under `mentions/<advisor>/<state>/`, so the reporter could see records
    the repair could not reach — an instrument with no path out."""

    def test_a_nested_record_is_reached(self, tmp_path):
        nested = tmp_path / "mentions" / "sage-cto" / "archive"
        nested.mkdir(parents=True)
        p = _write(nested, "m.md", BROKEN_MENTION)
        assert not _parses(p), "precondition: this mention does not parse"

        m.run(tmp_path)
        assert _parses(p)
        doc = yaml.safe_load(p.read_text().split("---")[1])
        assert doc["resolved_note"].startswith("Answered: the order")
        assert doc["resolved_note"].endswith("refuse as written.")

    def test_the_repair_defaults_to_every_corpus_the_audit_reports_on(
            self, ai_root, monkeypatch):
        """Behavioural, not an inspection of the source: a test that greps a function
        body for `rglob` passes on a function that recurses into the wrong tree. This
        one compares the two adapters' corpus lists, which is the claim."""
        from engine.cmd import audit as audit_cmd
        from engine.cmd import lifecycle as lifecycle_cmd

        walked: list = []
        monkeypatch.setattr(
            "enginelib.audit.records.run", lambda dirs: walked.extend(dirs) or Findings())
        monkeypatch.setattr("engine.cmd.audit._emit", lambda f: 0)
        audit_cmd._AUDITS["records"](None)

        assert walked, "precondition: the audit names its corpora"
        assert set(lifecycle_cmd.repair_roots()) == set(walked)


BLOCK_SEQUENCE = """\
    ---
    advisor: sage-cto
    date: 2026-07-08
    slug: d-slug
    decisions:
      - first-decision
      - second-decision
    issues: []
    reflexion: lost the tail at #68 here
    ---

    body
    """


class TestWhatTheChunkGuardProtects:
    """Both of these were found by a mutation that SURVIVED the suite as first written.

    `if chunk_parses(chunk)` looked like an optimisation — skip the chunks that are
    already fine. It is not: `repair_chunk` joins a chunk's lines and hands them to
    `as_block`, which turns a block SEQUENCE into a block STRING. Nothing in the
    corpus fixtures had one, so removing the guard stayed green while silently
    converting `decisions: [first, second]` into a two-line string."""

    def test_a_block_sequence_beside_a_broken_field_survives_as_a_list(self, tmp_path):
        p = _write(tmp_path, "d.md", BLOCK_SEQUENCE)
        m.run(tmp_path)
        doc = yaml.safe_load(p.read_text().split("---")[1])
        assert doc["decisions"] == ["first-decision", "second-decision"], (
            "a list must not come back as a string")
        assert "#68" in doc["reflexion"], "and the lossy field beside it is still repaired"

    def test_a_rewrite_that_moved_the_body_is_refused(self, tmp_path, monkeypatch):
        """The body gate is the last one standing between a reassembly bug and a
        record's prose. Correct code never trips it, which is exactly why it needs a
        forced failure rather than a fixture."""
        p = _write(tmp_path, "a.md", BROKEN_COLON)
        real = m.split_frontmatter
        calls = {"n": 0}

        def _drop_the_body_on_reassembly(text):
            # Only the SECOND call — the one that re-reads the candidate. Corrupting
            # both would leave the gate comparing two equally-damaged values and
            # passing, which is how the first version of this test lied to me.
            out = real(text)
            calls["n"] += 1
            if out is None or calls["n"] == 1:
                return out
            opening, lines, remainder = out
            return opening, lines, remainder.replace("body text that must not move", "")

        monkeypatch.setattr(m, "split_frontmatter", _drop_the_body_on_reassembly)
        before = p.read_text()
        res = m.run(tmp_path)
        assert res.updated == 0
        assert len(res.failed) == 1 and "body changed" in res.failed[0][1]
        assert p.read_text() == before

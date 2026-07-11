"""Test obsidian-parse.sh port — 26 cases (1:1 with tests/lib/obsidian-parse.bats).

Fixture files live in tests/fixtures/obsidian-parse/ (read-only).
Inline fixtures use tmp_path (mirrors bats mktemp cases).
"""

import re
from pathlib import Path

from enginelib import obsidian

FIXTURES = Path(__file__).parent.parent / "fixtures" / "obsidian-parse"


# ===========================================================================
# parse_wikilinks — 8 tests
# ===========================================================================

def test_wikilinks_simple_file_returns_target():
    """simple [[file]] returns target."""
    result = obsidian.parse_wikilinks(FIXTURES / "simple-links.md")
    assert "simple-file" in result


def test_wikilinks_alias_stripped():
    """[[file|alias]] strips alias, returns target only."""
    result = obsidian.parse_wikilinks(FIXTURES / "simple-links.md")
    assert "file-with-alias" in result
    assert not any("Display Name" in item for item in result)


def test_wikilinks_section_preserved():
    """[[file#section]] returns target#section."""
    result = obsidian.parse_wikilinks(FIXTURES / "simple-links.md")
    assert "file-with-section#Introduction" in result


def test_wikilinks_block_id_preserved():
    """[[file#^block-id]] returns target#^block-id."""
    result = obsidian.parse_wikilinks(FIXTURES / "simple-links.md")
    assert "file-with-block#^block-abc" in result


def test_wikilinks_escaped_pipe_is_literal():
    """escaped pipe [[file\\|literal]] treated as literal, not alias."""
    result = obsidian.parse_wikilinks(FIXTURES / "escaped-pipe.md")
    # The escaped pipe is literal; "with-pipe" must appear in output
    assert any("with-pipe" in item for item in result)


def test_wikilinks_embeds_excluded():
    """embeds ![[file]] NOT returned by parse_wikilinks."""
    result = obsidian.parse_wikilinks(FIXTURES / "embeds.md")
    assert "plain-link" in result
    assert "image.png" not in result
    assert "attachment.pdf" not in result


def test_wikilinks_no_frontmatter_body():
    """no frontmatter file returns body wikilinks."""
    result = obsidian.parse_wikilinks(FIXTURES / "no-frontmatter.md")
    assert "a-wikilink" in result


def test_wikilinks_empty_file_returns_empty(tmp_path):
    """exits 0 with no output when no links present."""
    f = tmp_path / "no-links.md"
    f.write_text("# No links here\nJust plain text.\n")
    assert obsidian.parse_wikilinks(f) == []


# ===========================================================================
# parse_embeds — 4 tests
# ===========================================================================

def test_embeds_returns_embed_targets():
    """![[file]] returns embed target."""
    result = obsidian.parse_embeds(FIXTURES / "embeds.md")
    assert "image.png" in result
    assert "attachment.pdf" in result


def test_embeds_section_preserved():
    """![[note#Section]] returns target#section."""
    result = obsidian.parse_embeds(FIXTURES / "embeds.md")
    assert "note#Section" in result


def test_embeds_wikilink_excluded():
    """plain [[wikilink]] NOT returned by parse_embeds."""
    result = obsidian.parse_embeds(FIXTURES / "embeds.md")
    assert "plain-link" not in result


def test_embeds_empty_file_returns_empty(tmp_path):
    """exits 0 with no output when no embeds present."""
    f = tmp_path / "no-embeds.md"
    f.write_text("# No embeds\n[[wikilink-only]]\n")
    assert obsidian.parse_embeds(f) == []


# ===========================================================================
# parse_tags — 5 tests
# ===========================================================================

def test_tags_frontmatter_list_entries():
    """frontmatter tags list entries returned."""
    result = obsidian.parse_tags(FIXTURES / "simple-links.md")
    assert "project" in result
    assert "alpha" in result


def test_tags_body_subtag_references():
    """body #tag/subtag references returned."""
    result = obsidian.parse_tags(FIXTURES / "simple-links.md")
    assert "work/active" in result
    assert "status" in result


def test_tags_duplicates_deduplicated():
    """duplicates de-duplicated (alpha in frontmatter + body)."""
    result = obsidian.parse_tags(FIXTURES / "tags-mixed.md")
    assert result.count("alpha") == 1


def test_tags_frontmatter_subtag():
    """frontmatter tag with subtag (beta/sub) returned."""
    result = obsidian.parse_tags(FIXTURES / "tags-mixed.md")
    assert "beta/sub" in result


def test_tags_empty_file_returns_empty(tmp_path):
    """exits 0 with no output when no tags."""
    f = tmp_path / "no-tags.md"
    f.write_text("# No tags\nJust text.\n")
    assert obsidian.parse_tags(f) == []


# ===========================================================================
# parse_block_ids — 5 tests
# ===========================================================================

def test_block_ids_eol_returned():
    """^block-id at EOL returned as <line>:<id>."""
    result = obsidian.parse_block_ids(FIXTURES / "block-ids.md")
    assert any(":first-block" in item for item in result)
    assert any(":second-block" in item for item in result)


def test_block_ids_standalone_line():
    """standalone ^block-id line returned."""
    result = obsidian.parse_block_ids(FIXTURES / "block-ids.md")
    assert any(":orphan-block" in item for item in result)


def test_block_ids_mid_line_not_matched():
    """block id in middle of line NOT matched."""
    result = obsidian.parse_block_ids(FIXTURES / "block-ids.md")
    assert not any("not-eol-block" in item for item in result)


def test_block_ids_format_linenum_colon_id():
    """format is <linenum>:<id> (numeric prefix)."""
    result = obsidian.parse_block_ids(FIXTURES / "block-ids.md")
    fmt = re.compile(r'^[0-9]+:[a-z0-9_-]+$')
    for item in result:
        assert fmt.match(item), f"Bad format: {item!r}"


def test_block_ids_empty_file_returns_empty(tmp_path):
    """exits 0 with no output when no block ids."""
    f = tmp_path / "no-blocks.md"
    f.write_text("# No block ids\nJust text.\n")
    assert obsidian.parse_block_ids(f) == []


# ===========================================================================
# parse_yaml_relations — 4 tests
# ===========================================================================

def test_yaml_relations_list_all_entries():
    """related: [foo, bar, baz] returns all entries."""
    result = obsidian.parse_yaml_relations(FIXTURES / "yaml-relations.md")
    assert "foo-note" in result
    assert "bar-note" in result
    assert "baz-note" in result


def test_yaml_relations_singleton():
    """related: singleton (no brackets) returns single entry."""
    result = obsidian.parse_yaml_relations(FIXTURES / "yaml-relations-singleton.md")
    assert "solo-note" in result


def test_yaml_relations_missing_key_empty(tmp_path):
    """missing related key returns empty output, exit 0."""
    f = tmp_path / "no-related.md"
    f.write_text("---\ntags: [x]\n---\nNo relations.\n")
    assert obsidian.parse_yaml_relations(f) == []


def test_yaml_relations_no_frontmatter_empty():
    """no frontmatter returns empty output, exit 0."""
    result = obsidian.parse_yaml_relations(FIXTURES / "no-frontmatter.md")
    assert result == []

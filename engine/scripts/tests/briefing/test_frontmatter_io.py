"""Tests for briefing.frontmatter_io — read + ruamel round-trip write."""
import textwrap
from pathlib import Path

import pytest

from briefing.frontmatter_io import read, read_commented, write


@pytest.fixture()
def md_with_comments(tmp_path: Path) -> Path:
    """A markdown file with frontmatter that has inline comments."""
    p = tmp_path / "test.md"
    p.write_text(
        textwrap.dedent("""\
        ---
        type: decision
        # This comment must survive a round-trip
        status: proposed
        owner: kai-cto
        created: 2026-05-20
        schema_version: 1
        ---

        Body text here.
        """),
        encoding="utf-8",
    )
    return p


@pytest.fixture()
def md_simple(tmp_path: Path) -> Path:
    """A plain frontmatter file with no comments."""
    p = tmp_path / "simple.md"
    p.write_text(
        textwrap.dedent("""\
        ---
        type: spec
        status: proposed
        id: "084"
        schema_version: 1
        ---

        Body.
        """),
        encoding="utf-8",
    )
    return p


# ---------------------------------------------------------------------------
# read()
# ---------------------------------------------------------------------------

class TestRead:
    def test_returns_meta_and_body(self, md_simple: Path):
        meta, body = read(md_simple)
        assert isinstance(meta, dict)
        assert "type" in meta
        assert "Body." in body

    def test_meta_values(self, md_simple: Path):
        meta, _ = read(md_simple)
        assert meta["type"] == "spec"
        assert meta["status"] == "proposed"
        assert meta["schema_version"] == 1

    def test_body_stripped(self, md_simple: Path):
        _, body = read(md_simple)
        # Body should not contain frontmatter delimiters
        assert "---" not in body
        assert "Body." in body

    def test_file_without_frontmatter(self, tmp_path: Path):
        p = tmp_path / "no_fm.md"
        p.write_text("Just prose.\n", encoding="utf-8")
        meta, body = read(p)
        assert meta == {}
        assert "Just prose." in body


# ---------------------------------------------------------------------------
# write() — ruamel round-trip
# ---------------------------------------------------------------------------

class TestWrite:
    def test_round_trip_preserves_comment(self, md_with_comments: Path):
        """THE regression test: comments must survive read_commented → write."""
        meta, body = read_commented(md_with_comments)
        # Modify a field — mutation on the CommentedMap preserves comment annotations.
        meta["status"] = "approved"
        write(md_with_comments, meta, body)

        result = md_with_comments.read_text(encoding="utf-8")
        assert "# This comment must survive a round-trip" in result, (
            "ruamel round-trip dropped the YAML comment"
        )

    def test_round_trip_preserves_key_order(self, md_with_comments: Path):
        meta, body = read_commented(md_with_comments)
        write(md_with_comments, meta, body)

        result = md_with_comments.read_text(encoding="utf-8")
        lines = [ln.strip() for ln in result.splitlines() if ln.strip() and not ln.startswith("#") and ln.strip() != "---"]
        # type must come before status in the output
        type_idx = next(i for i, ln in enumerate(lines) if ln.startswith("type:"))
        status_idx = next(i for i, ln in enumerate(lines) if ln.startswith("status:"))
        assert type_idx < status_idx, "Key order not preserved after round-trip"

    def test_write_adds_new_field(self, md_simple: Path):
        meta, body = read(md_simple)
        meta["updated"] = "2026-05-21"
        write(md_simple, meta, body)

        meta2, body2 = read(md_simple)
        assert meta2["updated"] == "2026-05-21"
        assert "Body." in body2

    def test_write_preserves_body(self, md_with_comments: Path):
        meta, body = read(md_with_comments)
        write(md_with_comments, meta, body)

        _, body2 = read(md_with_comments)
        assert "Body text here." in body2

    def test_write_is_valid_frontmatter(self, md_simple: Path):
        meta, body = read(md_simple)
        meta["schema_version"] = 2
        write(md_simple, meta, body)

        meta2, _ = read(md_simple)
        assert meta2["schema_version"] == 2

    def test_write_produces_yaml_delimiters(self, md_simple: Path):
        meta, body = read(md_simple)
        write(md_simple, meta, body)

        text = md_simple.read_text(encoding="utf-8")
        assert text.startswith("---\n"), "File must start with YAML delimiter"
        # There must be a closing ---
        assert text.count("---") >= 2

    def test_write_atomic_no_tmp_leftover(self, md_simple: Path):
        """Audit B1 regression test: write() round-trips the durable feedback
        notebook (feedback_emit --finalize / feedback_triage --set) and must be
        atomic — no *.tmp.* sibling left behind, full content intact."""
        meta, body = read(md_simple)
        meta["status"] = "approved"
        write(md_simple, meta, body)

        result = md_simple.read_text(encoding="utf-8")
        assert "type: spec" in result
        assert "status: approved" in result
        assert "Body." in result

        leftovers = list(md_simple.parent.glob("*.tmp.*"))
        assert leftovers == [], f"tmp files left behind: {leftovers}"

    def test_write_routes_through_snapshot_write(self, md_simple: Path, monkeypatch):
        """Spy proof that write() delegates to the atomic primitive."""
        import briefing.frontmatter_io as fio_mod

        calls = []
        real_snapshot_write = fio_mod.snapshot_write

        def spy(path, body):
            calls.append((path, body))
            return real_snapshot_write(path, body)

        monkeypatch.setattr(fio_mod, "snapshot_write", spy)

        meta, body = read(md_simple)
        write(md_simple, meta, body)

        assert len(calls) == 1
        assert calls[0][0] == md_simple

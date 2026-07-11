"""Tests for enginelib.frontmatter — ported 1:1 from tests/lib-frontmatter.bats (10 cases)."""

import pytest

from enginelib.frontmatter import fm_get, fm_set, fm_write


@pytest.fixture
def tmp(tmp_path):
    return tmp_path


def test_fm_get_extracts(tmp):
    f = tmp / "file.md"
    f.write_text("---\nslug: move-to-base\nby: nexus-ceo\nstatus: active\n---\n\nBody.\n")
    assert fm_get(f, "by") == "nexus-ceo"


def test_fm_get_empty_when_missing(tmp):
    f = tmp / "file.md"
    f.write_text("---\nslug: x\n---\n")
    assert fm_get(f, "missing") is None


def test_fm_get_empty_when_file_missing(tmp):
    result = fm_get(tmp / "nonexistent.md", "slug")
    assert result is None


def test_fm_set_updates(tmp):
    f = tmp / "file.md"
    f.write_text("---\nstatus: open\nresolved: null\n---\n\nBody.\n")
    fm_set(f, "status", "resolved")
    assert fm_get(f, "status") == "resolved"


def test_fm_set_adds_when_absent(tmp):
    f = tmp / "file.md"
    f.write_text("---\nslug: x\n---\n\nBody.\n")
    fm_set(f, "new_key", "new_value")
    assert fm_get(f, "new_key") == "new_value"


def test_fm_set_preserves_body(tmp):
    f = tmp / "file.md"
    f.write_text("---\nslug: x\n---\n\nBody line 1\nBody line 2\n")
    fm_set(f, "slug", "y")
    content = f.read_text()
    assert content.count("Body line") == 2


def test_fm_set_missing_file_raises(tmp):
    with pytest.raises(FileNotFoundError, match="not found"):
        fm_set(tmp / "nonexistent.md", "k", "v")


def test_fm_write_creates_block(tmp):
    out = tmp / "new.md"
    fm_write(out, [("slug", "x"), ("by", "nexus"), ("status", "active")], ["## Body", "This is body."])
    assert fm_get(out, "slug") == "x"
    assert "## Body" in out.read_text()


def test_fm_write_preserves_key_order(tmp):
    out = tmp / "ordered.md"
    fm_write(out, [("a", "1"), ("b", "2"), ("c", "3")], [""])
    content = out.read_text()
    assert "a: 1" in content
    assert "b: 2" in content
    assert "c: 3" in content
    la = next(i for i, line in enumerate(content.splitlines()) if line.startswith("a:"))
    lb = next(i for i, line in enumerate(content.splitlines()) if line.startswith("b:"))
    lc = next(i for i, line in enumerate(content.splitlines()) if line.startswith("c:"))
    assert la < lb < lc


def test_fm_set_idempotent(tmp):
    f = tmp / "file.md"
    f.write_text("---\nk: a\n---\n\nBody.\n")
    fm_set(f, "k", "b")
    first = f.read_text()
    fm_set(f, "k", "b")
    second = f.read_text()
    assert first == second


def test_fm_set_atomic_no_tmp_leftover_and_preserves_other_keys(tmp):
    """Audit A1 regression test: fm_set must route through snapshot_write (atomic
    tmp + os.replace), not a direct truncating write_text. Assert the file stays
    COMPLETE — every untouched key and the body survive — and no *.tmp.* sibling
    remains after the call."""
    f = tmp / "open.md"
    f.write_text(
        "---\n"
        "status: open\n"
        "resolved: null\n"
        "resolved_by: null\n"
        "resolved_note: null\n"
        "---\n\n"
        "Body line 1\n"
        "Body line 2\n"
    )
    fm_set(f, "status", "resolved")

    content = f.read_text()
    assert fm_get(f, "status") == "resolved"
    # Untouched keys survive — proves the write was not a partial/truncated write.
    assert "resolved_by: null" in content
    assert "resolved_note: null" in content
    assert "Body line 1" in content
    assert "Body line 2" in content

    leftovers = list(tmp.glob("*.tmp.*"))
    assert leftovers == [], f"tmp files left behind: {leftovers}"


def test_fm_set_routes_through_snapshot_write(tmp, monkeypatch):
    """Spy proof that fm_set delegates its final write to the atomic primitive."""
    import enginelib.frontmatter as fm_mod

    calls = []
    real_snapshot_write = fm_mod.snapshot_write

    def spy(path, body):
        calls.append((path, body))
        return real_snapshot_write(path, body)

    monkeypatch.setattr(fm_mod, "snapshot_write", spy)

    f = tmp / "file.md"
    f.write_text("---\nk: a\n---\n\nBody.\n")
    fm_set(f, "k", "b")

    assert len(calls) == 1
    assert calls[0][0] == f

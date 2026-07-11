
import pytest

from enginelib import template


# ── case 1 ──────────────────────────────────────────────────────────────────
def test_single_placeholder(tmp_path):
    tpl = tmp_path / "tpl"
    tpl.write_text("Hello {{name}}!\n")
    assert template.render(tpl, {"name": "World"}) == "Hello World!\n"


# ── case 2 ──────────────────────────────────────────────────────────────────
def test_multiple_placeholders(tmp_path):
    tpl = tmp_path / "tpl"
    tpl.write_text("From: {{from}}\nTo: {{to}}\n")
    result = template.render(tpl, {"from": "alice", "to": "bob"})
    assert "From: alice" in result
    assert "To: bob" in result


# ── case 3 ──────────────────────────────────────────────────────────────────
def test_missing_key_becomes_empty(tmp_path):
    tpl = tmp_path / "tpl"
    tpl.write_text("{{a}} and {{b}}\n")
    assert template.render(tpl, {"a": "X"}) == "X and \n"


# ── case 4 ──────────────────────────────────────────────────────────────────
def test_special_chars_preserved(tmp_path):
    tpl = tmp_path / "tpl"
    tpl.write_text("Body: {{body}}\n")
    assert template.render(tpl, {"body": "value/with&chars"}) == "Body: value/with&chars\n"


# ── case 5 ──────────────────────────────────────────────────────────────────
def test_repeated_placeholder_all_replaced(tmp_path):
    tpl = tmp_path / "tpl"
    tpl.write_text("{{x}} and {{x}} again\n")
    assert template.render(tpl, {"x": "foo"}) == "foo and foo again\n"


# ── case 6 ──────────────────────────────────────────────────────────────────
def test_missing_template_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="not found"):
        template.render(tmp_path / "nonexistent", {"k": "v"})


# ── case 7 ──────────────────────────────────────────────────────────────────
def test_key_with_underscores(tmp_path):
    tpl = tmp_path / "tpl"
    tpl.write_text("{{my_key}}\n")
    assert template.render(tpl, {"my_key": "ok"}) == "ok\n"


# ── case 8 ──────────────────────────────────────────────────────────────────
def test_multiline_value(tmp_path):
    tpl = tmp_path / "tpl"
    tpl.write_text("Header\n{{body}}\nFooter\n")
    body = "- line 1\n- line 2\n- line 3"
    result = template.render(tpl, {"body": body})
    assert result.startswith("Header\n")
    assert "- line 1" in result
    assert "- line 2" in result
    assert "- line 3" in result
    assert "Footer" in result


# ── case 9 ──────────────────────────────────────────────────────────────────
def test_multiline_value_with_markdown_and_blank_lines(tmp_path):
    tpl = tmp_path / "tpl"
    tpl.write_text("# Decision: {{slug}}\n\n{{body}}\n\n-- end --\n")
    body = "**Night Shift**\n\n- context: A\n- outcome: B\n\n*notes*: includes | pipes and & ampersands"
    result = template.render(tpl, {"slug": "test", "body": body})
    assert "# Decision: test" in result
    assert "**Night Shift**" in result
    assert "- context: A" in result
    assert "includes | pipes and & ampersands" in result
    assert "-- end --" in result


# ── case 10 ─────────────────────────────────────────────────────────────────
def test_backslash_value_preserved(tmp_path):
    tpl = tmp_path / "tpl"
    tpl.write_text("{{v}}\n")
    assert template.render(tpl, {"v": "path\\to\\file"}) == "path\\to\\file\n"


# ── invalid key (ValueError path) ───────────────────────────────────────────
def test_invalid_key_raises(tmp_path):
    tpl = tmp_path / "tpl"
    tpl.write_text("{{x}}\n")
    with pytest.raises(ValueError, match="invalid key"):
        template.render(tpl, {"bad-key": "v"})

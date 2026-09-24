"""Which project files the harness loads at every session start (spec 110, GH#369)."""
from __future__ import annotations

import os
from pathlib import Path

from enginelib.knowledge import autoload


def _w(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_entry_points_and_recursive_imports(tmp_path):
    _w(tmp_path / ".claude" / "CLAUDE.md", "intro\n@product.md\n@progress.md\n")
    _w(tmp_path / ".claude" / "product.md", "p" * 10 + "\n@nested/deep.md\n")
    _w(tmp_path / ".claude" / "progress.md", "x" * 100)
    _w(tmp_path / ".claude" / "nested" / "deep.md", "d")
    got = {f.rel: (f.size, f.via) for f in autoload.autoload_set(tmp_path)}
    assert got[".claude/progress.md"] == (100, "@import from .claude/CLAUDE.md")
    assert got[".claude/nested/deep.md"][1] == "@import from .claude/product.md"
    assert got[".claude/CLAUDE.md"][1] == "entry"


def test_imports_ignore_code_and_non_files(tmp_path):
    _w(tmp_path / "real.md", "r")
    _w(tmp_path / "fenced.md", "f")
    _w(tmp_path / "CLAUDE.md",
       "ask @vera-cto first\n`@real.md` is inline code\n```\n@fenced.md\n```\n@real.md\n")
    rels = [f.rel for f in autoload.autoload_set(tmp_path)]
    assert rels.count("real.md") == 1
    assert "fenced.md" not in rels
    assert not any("vera" in r for r in rels)


def test_rules_with_paths_frontmatter_do_not_load_at_start(tmp_path):
    _w(tmp_path / ".claude" / "rules" / "always.md", "always")
    _w(tmp_path / ".claude" / "rules" / "scoped.md", "---\npaths: src/**\n---\nscoped")
    rels = {f.rel: f.via for f in autoload.autoload_set(tmp_path)}
    assert rels == {".claude/rules/always.md": "rule"}


def test_claude_dir_symlink_is_followed_and_named_as_written(tmp_path):
    real = tmp_path / ".conclave" / ".claude"
    _w(real / "CLAUDE.md", "@progress.md\n")
    _w(real / "progress.md", "y" * 7)
    os.symlink(".conclave/.claude", tmp_path / ".claude")
    got = {f.rel: f.size for f in autoload.autoload_set(tmp_path)}
    assert got == {".claude/CLAUDE.md": len("@progress.md\n"), ".claude/progress.md": 7}


def test_a_file_reached_twice_is_counted_once_and_cycles_terminate(tmp_path):
    _w(tmp_path / "CLAUDE.md", "@a.md\n@b.md\n")
    _w(tmp_path / "a.md", "@b.md\n")
    _w(tmp_path / "b.md", "@a.md\n")
    rels = [f.rel for f in autoload.autoload_set(tmp_path)]
    assert sorted(rels) == ["CLAUDE.md", "a.md", "b.md"]


def test_import_depth_stops_after_five_hops(tmp_path):
    _w(tmp_path / "CLAUDE.md", "@h1.md\n")
    for i in range(1, 8):
        _w(tmp_path / f"h{i}.md", f"@h{i + 1}.md\n")
    rels = {f.rel for f in autoload.autoload_set(tmp_path)}
    assert "h5.md" in rels and "h6.md" not in rels


def test_empty_project_loads_nothing(tmp_path):
    assert autoload.autoload_set(tmp_path) == []

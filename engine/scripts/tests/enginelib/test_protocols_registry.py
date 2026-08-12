from pathlib import Path

from enginelib.protocols.registry import homes, scan

VALID = """---
stages: [plan]
tiers: [work]
task_types: [dev]
binding: required
last_reviewed: 2026-08-07
---

Body.
"""

NO_FRONTMATTER = "Just a body, no frontmatter at all.\n"

BAD_ENUM = """---
stages: [marketing]
tiers: [work]
task_types: [dev]
binding: required
---

Body.
"""


def test_scan_finds_valid_files(tmp_path: Path):
    (tmp_path / "a.md").write_text(VALID, encoding="utf-8")
    found, errors = scan([tmp_path])
    assert [p.path.name for p in found] == ["a.md"]
    assert errors == []


def test_missing_frontmatter_is_an_error_not_a_skip(tmp_path: Path):
    (tmp_path / "b.md").write_text(NO_FRONTMATTER, encoding="utf-8")
    found, errors = scan([tmp_path])
    assert found == []
    assert len(errors) == 1
    assert "b.md" in str(errors[0].path)


def test_unknown_enum_value_is_an_error_not_a_skip(tmp_path: Path):
    (tmp_path / "c.md").write_text(BAD_ENUM, encoding="utf-8")
    found, errors = scan([tmp_path])
    assert found == []
    assert len(errors) == 1


def test_scan_is_deterministic(tmp_path: Path):
    for name in ("z.md", "a.md", "m.md"):
        (tmp_path / name).write_text(VALID, encoding="utf-8")
    first, _ = scan([tmp_path])
    second, _ = scan([tmp_path])
    assert [p.path for p in first] == [p.path for p in second]


def test_a_missing_home_is_not_fatal(tmp_path: Path):
    found, errors = scan([tmp_path / "does-not-exist"])
    assert found == []
    assert errors == []


def test_homes_returns_the_three_fixed_dirs_plus_advisor(tmp_path: Path):
    engine_root = tmp_path / "engine-root"
    advisor = tmp_path / "conclave-sage-cto" / "protocols"
    result = homes(engine_root, advisor)
    assert len(result) == 4
    assert result[-1] == advisor
    # Completeness: every fixed home is under skills/, none hardcodes a team. prefix.
    for d in result[:3]:
        assert "skills" in d.parts
        assert not any(part.startswith("team.") for part in d.parts)


def test_homes_without_an_advisor_returns_three(tmp_path: Path):
    assert len(homes(tmp_path, None)) == 3

"""test_template_schema.py — port of tests/templates/schema-validation.bats (84 cases).

Validates the 6 op-type templates + 2 envelope templates + 16 fixtures (file
existence, schema_version field, status/tag rules by op-type, frontmatter
parsability).  Reads REAL repo files — no tmp_path.

Path resolution:
  templates → enginelib.paths.forge_templates_dir()  (→ skills/team.forge/templates)
  fixtures  → <this file>/../../fixtures/templates/
"""

import re
from pathlib import Path

import pytest
import yaml

from enginelib import paths

# ---------------------------------------------------------------------------
# Type groups — mirrors bats file header
# ---------------------------------------------------------------------------
STATUS_TYPES = ["audit-finding", "reconcile-mismatch", "plan-step"]
SNAPSHOT_TYPES = ["gh-snapshot", "git-snapshot", "run-log"]
ENVELOPE_TYPES = ["query", "result"]
ALL_TYPES = ["gh-snapshot", "git-snapshot", "audit-finding", "reconcile-mismatch", "run-log", "plan-step"]

# ---------------------------------------------------------------------------
# Resolved dirs (module-level, real repo files)
# ---------------------------------------------------------------------------
TEMPLATES_DIR = paths.forge_templates_dir()
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "templates"


# ---------------------------------------------------------------------------
# Section 1: Op-type template tests — 6 types × 6 groups = 30 tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("op_type", ALL_TYPES)
def test_template_exists(op_type):
    assert (TEMPLATES_DIR / f"{op_type}.md").is_file()


@pytest.mark.parametrize("op_type", ALL_TYPES)
def test_template_schema_version(op_type):
    lines = (TEMPLATES_DIR / f"{op_type}.md").read_text().splitlines()
    assert "schema_version: 1" in lines


@pytest.mark.parametrize("op_type", ALL_TYPES)
def test_template_type_field(op_type):
    lines = (TEMPLATES_DIR / f"{op_type}.md").read_text().splitlines()
    assert f"type: {op_type}" in lines


@pytest.mark.parametrize("op_type", ALL_TYPES)
def test_template_h2_sections(op_type):
    lines = (TEMPLATES_DIR / f"{op_type}.md").read_text().splitlines()
    assert "## Schema" in lines
    assert "## Producer" in lines
    assert "## Path" in lines
    assert "## Example" in lines


@pytest.mark.parametrize("op_type", STATUS_TYPES)
def test_template_has_status_open_tag(op_type):
    lines = (TEMPLATES_DIR / f"{op_type}.md").read_text().splitlines()
    assert any(re.search(r"^tags:.*status/open", line) for line in lines)


@pytest.mark.parametrize("op_type", SNAPSHOT_TYPES)
def test_template_no_status_tag(op_type):
    lines = (TEMPLATES_DIR / f"{op_type}.md").read_text().splitlines()
    assert not any(re.search(r"^tags:.*status/", line) for line in lines)


# ---------------------------------------------------------------------------
# Section 2: Valid fixture tests — 6 types × 4 groups = 24 tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("op_type", ALL_TYPES)
def test_valid_fixture_exists(op_type):
    assert (FIXTURES_DIR / "valid" / f"{op_type}.md").is_file()


@pytest.mark.parametrize("op_type", ALL_TYPES)
def test_valid_fixture_schema_version(op_type):
    lines = (FIXTURES_DIR / "valid" / f"{op_type}.md").read_text().splitlines()
    assert "schema_version: 1" in lines


@pytest.mark.parametrize("op_type", ALL_TYPES)
def test_valid_fixture_type_field(op_type):
    lines = (FIXTURES_DIR / "valid" / f"{op_type}.md").read_text().splitlines()
    assert f"type: {op_type}" in lines


@pytest.mark.parametrize("op_type", ALL_TYPES)
def test_valid_fixture_yaml_parse(op_type):
    text = (FIXTURES_DIR / "valid" / f"{op_type}.md").read_text()
    parts = text.split("---")
    assert len(parts) >= 2, f"{op_type}: no frontmatter delimiters found"
    parsed = yaml.safe_load(parts[1])
    assert parsed is not None


# ---------------------------------------------------------------------------
# Section 3: Invalid fixture tests — 6 types × 2 groups = 12 tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("op_type", ALL_TYPES)
def test_invalid_fixture_exists(op_type):
    assert (FIXTURES_DIR / "invalid" / f"{op_type}-missing-schema-version.md").is_file()


@pytest.mark.parametrize("op_type", ALL_TYPES)
def test_invalid_fixture_no_schema_version(op_type):
    lines = (FIXTURES_DIR / "invalid" / f"{op_type}-missing-schema-version.md").read_text().splitlines()
    assert not any(line.startswith("schema_version:") for line in lines)


# ---------------------------------------------------------------------------
# Section 4: Envelope template tests — 2 types × 5 groups = 10 tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("op_type", ENVELOPE_TYPES)
def test_envelope_template_exists(op_type):
    assert (TEMPLATES_DIR / f"{op_type}.md").is_file()


@pytest.mark.parametrize("op_type", ENVELOPE_TYPES)
def test_envelope_template_schema_version(op_type):
    lines = (TEMPLATES_DIR / f"{op_type}.md").read_text().splitlines()
    assert "schema_version: 1" in lines


@pytest.mark.parametrize("op_type", ENVELOPE_TYPES)
def test_envelope_template_type_field(op_type):
    lines = (TEMPLATES_DIR / f"{op_type}.md").read_text().splitlines()
    assert f"type: {op_type}" in lines


@pytest.mark.parametrize("op_type", ENVELOPE_TYPES)
def test_envelope_template_h2_sections(op_type):
    lines = (TEMPLATES_DIR / f"{op_type}.md").read_text().splitlines()
    assert "## Schema" in lines
    assert "## Producer" in lines
    assert "## Path" in lines
    assert "## Example" in lines


@pytest.mark.parametrize("op_type", ENVELOPE_TYPES)
def test_envelope_template_no_status_tag(op_type):
    lines = (TEMPLATES_DIR / f"{op_type}.md").read_text().splitlines()
    assert not any(re.search(r"^tags:.*status/", line) for line in lines)


# ---------------------------------------------------------------------------
# Section 5: Envelope fixture tests — 2 valid + 2 invalid = 8 tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("op_type", ENVELOPE_TYPES)
def test_envelope_valid_fixture_exists(op_type):
    assert (FIXTURES_DIR / "valid" / f"{op_type}.md").is_file()


@pytest.mark.parametrize("op_type", ENVELOPE_TYPES)
def test_envelope_valid_fixture_yaml_parse(op_type):
    text = (FIXTURES_DIR / "valid" / f"{op_type}.md").read_text()
    parts = text.split("---")
    assert len(parts) >= 2, f"{op_type}: no frontmatter delimiters found"
    parsed = yaml.safe_load(parts[1])
    assert parsed is not None


@pytest.mark.parametrize("op_type", ENVELOPE_TYPES)
def test_envelope_invalid_fixture_exists(op_type):
    assert (FIXTURES_DIR / "invalid" / f"{op_type}-missing-schema-version.md").is_file()


@pytest.mark.parametrize("op_type", ENVELOPE_TYPES)
def test_envelope_invalid_fixture_no_schema_version(op_type):
    lines = (FIXTURES_DIR / "invalid" / f"{op_type}-missing-schema-version.md").read_text().splitlines()
    assert not any(line.startswith("schema_version:") for line in lines)

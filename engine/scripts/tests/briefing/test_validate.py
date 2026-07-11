"""Tests for briefing.validate — per-type required/enum/line-cap validator."""
import textwrap
from pathlib import Path

from briefing.validate import Finding, Severity, validate_file, validate_tree


def make_md(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# validate_file — good files produce no errors
# ---------------------------------------------------------------------------

class TestValidFileProducesNoErrors:
    def test_valid_spec(self, tmp_path: Path):
        p = make_md(tmp_path, "spec.md", """\
            ---
            type: spec
            status: proposed
            id: "084"
            created: 2026-05-20
            updated: 2026-05-20
            owner: kai-cto
            schema_version: 1
            ---
            Body.
            """)
        findings = validate_file(p)
        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert errors == [], f"Unexpected errors: {errors}"

    def test_valid_decision(self, tmp_path: Path):
        p = make_md(tmp_path, "decision.md", """\
            ---
            type: decision
            status: proposed
            owner: kai-cto
            created: 2026-05-20
            confidence: high
            contested: false
            schema_version: 1
            ---
            Body.
            """)
        findings = validate_file(p)
        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert errors == []

    def test_no_type_field_produces_error(self, tmp_path: Path):
        p = make_md(tmp_path, "no_type.md", """\
            ---
            status: proposed
            schema_version: 1
            ---
            Body.
            """)
        findings = validate_file(p)
        assert any(f.severity == Severity.ERROR for f in findings)

    def test_unknown_type_produces_error(self, tmp_path: Path):
        p = make_md(tmp_path, "unknown.md", """\
            ---
            type: unknown-type
            schema_version: 1
            ---
            Body.
            """)
        findings = validate_file(p)
        assert any(f.severity == Severity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# Bad enum values
# ---------------------------------------------------------------------------

class TestBadEnumValues:
    def test_bad_spec_status(self, tmp_path: Path):
        p = make_md(tmp_path, "bad_status.md", """\
            ---
            type: spec
            status: not-a-real-status
            id: "001"
            created: 2026-05-20
            updated: 2026-05-20
            owner: kai-cto
            schema_version: 1
            ---
            Body.
            """)
        findings = validate_file(p)
        assert any(f.severity == Severity.ERROR for f in findings)

    def test_bad_decision_status(self, tmp_path: Path):
        p = make_md(tmp_path, "bad_decision.md", """\
            ---
            type: decision
            status: invalid
            owner: kai-cto
            created: 2026-05-20
            confidence: high
            contested: false
            schema_version: 1
            ---
            Body.
            """)
        findings = validate_file(p)
        assert any(f.severity == Severity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# Missing required fields
# ---------------------------------------------------------------------------

class TestMissingRequiredFields:
    def test_missing_owner_in_spec(self, tmp_path: Path):
        p = make_md(tmp_path, "missing_owner.md", """\
            ---
            type: spec
            status: proposed
            id: "001"
            created: 2026-05-20
            updated: 2026-05-20
            schema_version: 1
            ---
            Body.
            """)
        findings = validate_file(p)
        assert any(f.severity == Severity.ERROR for f in findings)

    def test_missing_schema_version(self, tmp_path: Path):
        p = make_md(tmp_path, "no_schema_version.md", """\
            ---
            type: spec
            status: proposed
            id: "001"
            created: 2026-05-20
            updated: 2026-05-20
            owner: kai-cto
            ---
            Body.
            """)
        findings = validate_file(p)
        assert any(f.severity == Severity.ERROR for f in findings)


# ---------------------------------------------------------------------------
# Line-cap: warn ≥10, error ≥20
# ---------------------------------------------------------------------------

class TestLineCap:
    def _make_spec_with_n_fm_lines(self, tmp_path: Path, n: int) -> Path:
        # Build a spec with exactly n frontmatter lines (inside the --- delimiters).
        required = [
            "type: spec",
            "status: proposed",
            'id: "001"',
            "created: 2026-05-20",
            "updated: 2026-05-20",
            "owner: kai-cto",
            "schema_version: 1",
        ]
        # Pad with extra optional tag lines to reach n
        padding = [f"# pad-line-{i}: value" for i in range(n - len(required))]
        fm_lines = required + padding
        content = "---\n" + "\n".join(fm_lines) + "\n---\nBody.\n"
        p = tmp_path / f"fm_{n}.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_9_lines_no_warning(self, tmp_path: Path):
        p = self._make_spec_with_n_fm_lines(tmp_path, 9)
        findings = validate_file(p)
        cap_findings = [f for f in findings if "line" in f.message.lower() or "cap" in f.message.lower()]
        assert all(f.severity != Severity.WARN for f in cap_findings)

    def test_10_lines_produces_warn(self, tmp_path: Path):
        p = self._make_spec_with_n_fm_lines(tmp_path, 10)
        findings = validate_file(p)
        assert any(f.severity == Severity.WARN for f in findings), (
            f"Expected WARN at 10 frontmatter lines, got: {findings}"
        )

    def test_10_lines_no_error(self, tmp_path: Path):
        p = self._make_spec_with_n_fm_lines(tmp_path, 10)
        findings = validate_file(p)
        assert not any(f.severity == Severity.ERROR and "line" in f.message.lower() for f in findings)

    def test_20_lines_produces_error(self, tmp_path: Path):
        p = self._make_spec_with_n_fm_lines(tmp_path, 20)
        findings = validate_file(p)
        assert any(f.severity == Severity.ERROR for f in findings), (
            f"Expected ERROR at 20 frontmatter lines, got: {findings}"
        )

    def test_file_without_frontmatter_no_cap_finding(self, tmp_path: Path):
        p = tmp_path / "no_fm.md"
        p.write_text("Just prose.\n", encoding="utf-8")
        findings = validate_file(p)
        # No type → error, but no line-cap finding
        cap = [f for f in findings if "line" in f.message.lower() and "cap" in f.message.lower()]
        assert cap == []


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

class TestFinding:
    def test_finding_has_path_severity_message(self, tmp_path: Path):
        p = make_md(tmp_path, "f.md", """\
            ---
            type: unknown-type
            ---
            Body.
            """)
        findings = validate_file(p)
        assert findings
        f = findings[0]
        assert hasattr(f, "path")
        assert hasattr(f, "severity")
        assert hasattr(f, "message")
        assert isinstance(f.severity, Severity)


# ---------------------------------------------------------------------------
# F2 — validate_tree() integration test (fixture tree, never touches live .ai/)
# ---------------------------------------------------------------------------

class TestValidateTree:
    def _build_fixture_tree(self, root: Path) -> None:
        """Build a minimal .ai/-like fixture tree: agent-memory/ + ops/."""
        # Good file — valid spec
        specs = root / "ops" / "specs"
        specs.mkdir(parents=True)
        (specs / "good_spec.md").write_text(
            textwrap.dedent("""\
            ---
            type: spec
            status: proposed
            id: "001"
            created: 2026-05-20
            updated: 2026-05-20
            owner: kai-cto
            schema_version: 1
            ---
            Good spec body.
            """),
            encoding="utf-8",
        )

        # Bad file — missing required `owner` field
        (specs / "bad_spec.md").write_text(
            textwrap.dedent("""\
            ---
            type: spec
            status: proposed
            id: "002"
            created: 2026-05-20
            updated: 2026-05-20
            schema_version: 1
            ---
            Bad spec — owner missing.
            """),
            encoding="utf-8",
        )

        # Briefings dir — must be excluded from validation
        briefings = root / "agent-memory" / "advisors" / "briefings"
        briefings.mkdir(parents=True)
        (briefings / "kai-cto.md").write_text(
            "<!-- compiled briefing — no frontmatter schema -->\n# Briefing\n",
            encoding="utf-8",
        )

    def test_finds_error_in_bad_file(self, tmp_path: Path):
        self._build_fixture_tree(tmp_path)
        findings = validate_tree(tmp_path)
        errors = [f for f in findings if f.severity == Severity.ERROR]
        assert errors, "validate_tree must report ERROR for the bad spec"

    def test_no_error_for_good_file(self, tmp_path: Path):
        self._build_fixture_tree(tmp_path)
        findings = validate_tree(tmp_path)
        good_spec = tmp_path / "ops" / "specs" / "good_spec.md"
        good_errors = [f for f in findings if f.path == good_spec and f.severity == Severity.ERROR]
        assert good_errors == [], f"Good spec must produce no errors, got: {good_errors}"

    def test_briefings_excluded(self, tmp_path: Path):
        self._build_fixture_tree(tmp_path)
        findings = validate_tree(tmp_path)
        briefing_file = tmp_path / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"
        briefing_findings = [f for f in findings if f.path == briefing_file]
        assert briefing_findings == [], (
            f"briefings/ must be excluded from validation, got: {briefing_findings}"
        )

    def test_returns_list_of_findings(self, tmp_path: Path):
        self._build_fixture_tree(tmp_path)
        findings = validate_tree(tmp_path)
        assert isinstance(findings, list)
        assert all(isinstance(f, Finding) for f in findings)

    def test_empty_tree_returns_empty(self, tmp_path: Path):
        # A root with no agent-memory/ or ops/ dirs → no findings
        findings = validate_tree(tmp_path)
        assert findings == []

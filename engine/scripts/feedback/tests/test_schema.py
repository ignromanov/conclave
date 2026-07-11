import pytest
from pydantic import ValidationError

from feedback.schema import FeedbackItem, Location, Review


def _item(**over):
    base = dict(
        id="it-1", category="script-defect", layer="skill",
        location=Location(file="a.sh", line=4),
        observation="exited 1", suggested_fix="add guard",
        severity="medium", frequency="first-time",
        evidence="tool_call:abc123",
    )
    base.update(over)
    return FeedbackItem(**base)

def test_evidence_required():
    with pytest.raises(ValidationError):
        _item(evidence=None)

def test_closed_enum_category():
    with pytest.raises(ValidationError):
        _item(category="not-a-category")

def test_severity_has_critical():
    assert _item(severity="critical").severity == "critical"

def test_below_threshold_forbids_empty_items():
    with pytest.raises(ValidationError):
        Review(feedback_id="fb-1-aaaaaa", agent="quorum", agent_type="advisor",
               session_ref="s1", created="2026-05-22T10:00:00",
               updated_at="2026-05-22T10:00:00", skill_version="sha256:abc",
               summary="x", items=[], below_threshold_count=2)

def test_empty_items_ok_for_noop():
    r = Review(feedback_id="fb-1-aaaaaa", agent="quorum", agent_type="advisor",
               session_ref="s1", created="2026-05-22T10:00:00",
               updated_at="2026-05-22T10:00:00", skill_version="sha256:abc",
               summary="no-op", items=[], below_threshold_count=0)
    assert r.items == []

def test_migrated_item_skips_evidence():
    it = _item(evidence=None, migrated=True, legacy_source="journal.jsonl#fb-x")
    assert it.migrated is True

def test_draft_alias_roundtrips():
    r = Review.model_validate({
        "feedback_id": "fb-1-aaaaaa", "agent": "quorum", "agent_type": "advisor",
        "session_ref": "s1", "created": "2026-05-22T10:00:00",
        "updated_at": "2026-05-22T10:00:00", "skill_version": "sha256:abc",
        "summary": "x", "_draft": True})
    assert r.draft is True
    assert r.model_dump(by_alias=True)["_draft"] is True

def test_fingerprint_normalizes_location():
    from feedback.schema import fingerprint
    a = fingerprint({"file": "emit.py", "line": 42}, "script-defect")
    b = fingerprint({"file": "emit.py"}, "script-defect")
    assert a == b


def test_fingerprint_section_distinguishes():
    """Distinct sections in the SAME file must not dedup-collapse, while line-only
    variations still merge (poststart-sweep F2)."""
    from feedback.schema import fingerprint
    a = fingerprint({"file": "s.py", "line": 128, "section": "_step1"}, "script-defect")
    b = fingerprint({"file": "s.py", "line": 36, "section": "_agents_dir"}, "script-defect")
    assert a != b, "distinct sections in one file must not collapse"
    c = fingerprint({"file": "s.py", "line": 1, "section": "_step1"}, "script-defect")
    assert a == c, "same file+section, different line must still merge"


def test_fingerprint_section_only_location_not_doubled():
    """When location has only a section (no file/skill), section IS the base — the key
    must not append it twice."""
    from feedback.schema import fingerprint
    a = fingerprint({"section": "Before Exit"}, "skill-gap")
    b = fingerprint({"section": "Before Exit"}, "skill-gap")
    assert a == b


def test_location_section_only_valid():
    loc = Location(section="AC-1")
    assert loc.section == "AC-1"


def test_location_all_none_raises():
    with pytest.raises(ValidationError, match="location needs"):
        Location()


def test_location_bare_string_coerced_to_file():
    """A bare-string location (common author shorthand) coerces to {file: ...}."""
    it = _item(location="ops/handoffs/2026-06-03-perf.md")
    assert it.location.file == "ops/handoffs/2026-06-03-perf.md"


def test_location_dict_still_accepted():
    """Coercion does not break the canonical dict form."""
    it = _item(location={"skill": "team.kai-cto"})
    assert it.location.skill == "team.kai-cto"


def test_location_skill_only_valid():
    loc = Location(skill="team.quorum")
    assert loc.skill == "team.quorum"


def test_item_unicode_observation():
    it = _item(observation="Ошибка: unexpected exit 退出")
    assert "Ошибка" in it.observation


def _review(**over):
    base = dict(
        feedback_id="fb-1-aaaaaa", agent="quorum", agent_type="advisor",
        session_ref="s1", created="2026-05-22T10:00:00",
        updated_at="2026-05-22T10:00:00", skill_version="sha256:abc",
        summary="x",
    )
    base.update(over)
    return Review(**base)


def test_review_accepts_trace_ref_field():
    r = _review(trace_ref="sess-abc123")
    assert r.trace_ref == "sess-abc123"


def test_review_accepts_parent_session_ref_field():
    r = _review(parent_session_ref="parent-xyz")
    assert r.parent_session_ref == "parent-xyz"


def test_review_defaults_both_refs_to_none():
    r = _review()
    assert r.trace_ref is None
    assert r.parent_session_ref is None


# --- T-A: location.skill regex guard (G5) ---

def test_location_skill_valid_team_dot():
    loc = Location(skill="team.start")
    assert loc.skill == "team.start"


def test_location_skill_valid_exec_dot():
    loc = Location(skill="exec.atlas-dev")
    assert loc.skill == "exec.atlas-dev"


def test_location_skill_valid_workflow_dot():
    loc = Location(skill="workflow.worktree-cleanup")
    assert loc.skill == "workflow.worktree-cleanup"


def test_location_skill_valid_util_dot():
    loc = Location(skill="util.fix")
    assert loc.skill == "util.fix"


def test_location_skill_agent_name_rejected():
    with pytest.raises(ValidationError, match="skill path slug"):
        Location(skill="kai-cto")


def test_location_skill_bare_executor_name_rejected():
    with pytest.raises(ValidationError, match="skill path slug"):
        Location(skill="atlas")


# --- T-B: accepted_at field on FeedbackItem ---

def test_item_accepted_at_absent_by_default():
    it = _item()
    assert it.accepted_at is None


def test_item_accepted_at_can_be_set():
    it = _item(accepted_at="2026-05-28T12:00:00+00:00")
    assert it.accepted_at == "2026-05-28T12:00:00+00:00"


# --- spec 093: Predicate model + verify field ---

from feedback.schema import Predicate  # noqa: E402


def test_predicate_grep_absent_valid():
    p = Predicate(kind="grep-absent", file="lib/gh-fetch.sh", pattern="--state open")
    assert p.kind == "grep-absent"


def test_predicate_requires_pattern_for_grep_kinds():
    import pytest
    with pytest.raises(ValueError):
        Predicate(kind="grep-absent", file="x.sh")  # missing pattern


def test_item_accepts_verify_field():
    item = _item(verify={"kind": "file-absent", "path": "old/dead.sh"})
    assert item.verify.kind == "file-absent"


def test_item_verify_defaults_none():
    assert _item().verify is None

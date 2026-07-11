"""Tests for briefing.schema — pydantic v2 models for the 10 page types."""
from datetime import date, datetime

import pytest
from pydantic import ValidationError

from briefing.schema import (
    PAGE_TYPES,
    Decision,
    Feedback,
    Handoff,
    Meeting,
    Mention,
    OpenQuestion,
    Retro,
    Session,
    Spec,
)

# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------

class TestSpec:
    def test_valid(self):
        s = Spec(
            type="spec",
            status="proposed",
            id="084",
            created=date(2026, 5, 20),
            updated=date(2026, 5, 20),
            owner="kai-cto",
            schema_version=1,
        )
        assert s.type == "spec"

    def test_bad_status_raises(self):
        with pytest.raises(ValidationError):
            Spec(
                type="spec",
                status="unknown-status",
                id="084",
                created=date(2026, 5, 20),
                updated=date(2026, 5, 20),
                owner="kai-cto",
                schema_version=1,
            )

    def test_missing_required_raises(self):
        with pytest.raises(ValidationError):
            Spec(type="spec", status="proposed")  # missing id, created, updated, owner, schema_version

    def test_schema_version_string_rejected(self):
        with pytest.raises(ValidationError):
            Spec(
                type="spec",
                status="proposed",
                id="084",
                created=date(2026, 5, 20),
                updated=date(2026, 5, 20),
                owner="kai-cto",
                schema_version="1",  # string, not int
            )

    def test_all_statuses_valid(self):
        for status in ("proposed", "approved", "in_progress", "done", "archived", "cancelled"):
            s = Spec(
                type="spec",
                status=status,
                id="084",
                created=date(2026, 5, 20),
                updated=date(2026, 5, 20),
                owner="kai-cto",
                schema_version=1,
            )
            assert s.status == status


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

class TestSession:
    def test_valid(self):
        s = Session(
            type="session",
            owner="kai-cto",
            created=datetime(2026, 5, 20, 14, 0, 0),
            schema_version=1,
        )
        assert s.type == "session"

    def test_missing_owner_raises(self):
        with pytest.raises(ValidationError):
            Session(type="session", created=datetime(2026, 5, 20, 14, 0, 0), schema_version=1)

    def test_schema_version_string_rejected(self):
        with pytest.raises(ValidationError):
            Session(
                type="session",
                owner="kai-cto",
                created=datetime(2026, 5, 20, 14, 0, 0),
                schema_version="1",
            )


# ---------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------

class TestDecision:
    def test_valid(self):
        d = Decision(
            type="decision",
            status="proposed",
            owner="kai-cto",
            created=date(2026, 5, 20),
            confidence="high",
            contested=False,
            promoted_to=None,
            schema_version=1,
        )
        assert d.type == "decision"

    def test_bad_status_raises(self):
        with pytest.raises(ValidationError):
            Decision(
                type="decision",
                status="invalid",
                owner="kai-cto",
                created=date(2026, 5, 20),
                confidence="high",
                contested=False,
                promoted_to=None,
                schema_version=1,
            )

    def test_all_statuses_valid(self):
        for status in ("proposed", "approved", "promoted", "superseded", "rejected"):
            d = Decision(
                type="decision",
                status=status,
                owner="kai-cto",
                created=date(2026, 5, 20),
                confidence="high",
                contested=False,
                promoted_to=None,
                schema_version=1,
            )
            assert d.status == status

    def test_schema_version_string_rejected(self):
        with pytest.raises(ValidationError):
            Decision(
                type="decision",
                status="proposed",
                owner="kai-cto",
                created=date(2026, 5, 20),
                confidence="high",
                contested=False,
                promoted_to=None,
                schema_version="1",
            )


# ---------------------------------------------------------------------------
# Mention
# ---------------------------------------------------------------------------

class TestMention:
    def test_valid(self):
        m = Mention(
            type="mention",
            source_session="2026-05-20-kai-cto-session",
            target_advisor="nexus-ceo",
            status="open",
            created=date(2026, 5, 20),
            schema_version=1,
        )
        assert m.type == "mention"

    def test_missing_source_session_raises(self):
        with pytest.raises(ValidationError):
            Mention(
                type="mention",
                target_advisor="nexus-ceo",
                status="open",
                created=date(2026, 5, 20),
                schema_version=1,
            )

    def test_bad_status_raises(self):
        """F1 — Mention.status must be a Literal enum, not free-form str."""
        with pytest.raises(ValidationError):
            Mention(
                type="mention",
                source_session="2026-05-20-kai-cto-session",
                target_advisor="nexus-ceo",
                status="invalid-status",
                created=date(2026, 5, 20),
                schema_version=1,
            )

    def test_all_statuses_valid(self):
        for status in ("open", "resolved"):
            m = Mention(
                type="mention",
                source_session="2026-05-20-kai-cto-session",
                target_advisor="nexus-ceo",
                status=status,
                created=date(2026, 5, 20),
                schema_version=1,
            )
            assert m.status == status


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class TestFeedback:
    def test_valid(self):
        f = Feedback(
            type="feedback",
            severity="p1",
            target="team.kai-cto",
            status="open",
            created=date(2026, 5, 20),
            schema_version=1,
        )
        assert f.type == "feedback"

    def test_wontfix_status_valid(self):
        f = Feedback(
            type="feedback",
            severity="p2",
            target="team.kai-cto",
            status="wontfix",
            created=date(2026, 5, 20),
            schema_version=1,
        )
        assert f.status == "wontfix"

    def test_bad_status_raises(self):
        """F1 — Feedback.status must be a Literal enum, not free-form str."""
        with pytest.raises(ValidationError):
            Feedback(
                type="feedback",
                severity="p1",
                target="team.kai-cto",
                status="not-a-real-status",
                created=date(2026, 5, 20),
                schema_version=1,
            )

    def test_all_statuses_valid(self):
        for status in ("open", "resolved", "archived", "wontfix"):
            f = Feedback(
                type="feedback",
                severity="p1",
                target="team.kai-cto",
                status=status,
                created=date(2026, 5, 20),
                schema_version=1,
            )
            assert f.status == status

    def test_missing_severity_raises(self):
        with pytest.raises(ValidationError):
            Feedback(
                type="feedback",
                target="team.kai-cto",
                status="open",
                created=date(2026, 5, 20),
                schema_version=1,
            )


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------

class TestHandoff:
    def test_valid(self):
        h = Handoff(
            type="handoff",
            from_="kai-cto",
            to="atlas",
            created=datetime(2026, 5, 20, 14, 0, 0),
            priority="p1",
            status="open",
            schema_version=1,
        )
        assert h.type == "handoff"

    def test_missing_to_raises(self):
        with pytest.raises(ValidationError):
            Handoff(
                type="handoff",
                from_="kai-cto",
                created=datetime(2026, 5, 20, 14, 0, 0),
                priority="p1",
                status="open",
                schema_version=1,
            )


# ---------------------------------------------------------------------------
# Retro
# ---------------------------------------------------------------------------

class TestRetro:
    def test_valid(self):
        r = Retro(
            type="retro",
            spec="084",
            owner="kai-cto",
            created=date(2026, 5, 20),
            schema_version=1,
        )
        assert r.type == "retro"

    def test_missing_spec_raises(self):
        with pytest.raises(ValidationError):
            Retro(
                type="retro",
                owner="kai-cto",
                created=date(2026, 5, 20),
                schema_version=1,
            )


# ---------------------------------------------------------------------------
# OpenQuestion
# ---------------------------------------------------------------------------

class TestOpenQuestion:
    def test_valid(self):
        oq = OpenQuestion(
            type="open-question",
            status="open",
            opened=date(2026, 5, 20),
            owner="kai-cto",
            schema_version=1,
        )
        assert oq.type == "open-question"

    def test_bad_status_raises(self):
        with pytest.raises(ValidationError):
            OpenQuestion(
                type="open-question",
                status="invalid-status",
                opened=date(2026, 5, 20),
                owner="kai-cto",
                schema_version=1,
            )

    def test_all_statuses_valid(self):
        for status in ("open", "answered", "abandoned", "superseded"):
            oq = OpenQuestion(
                type="open-question",
                status=status,
                opened=date(2026, 5, 20),
                owner="kai-cto",
                schema_version=1,
            )
            assert oq.status == status


# ---------------------------------------------------------------------------
# Meeting
# ---------------------------------------------------------------------------

class TestMeeting:
    def test_valid(self):
        m = Meeting(
            type="meeting",
            attendees=["kai-cto", "nexus-ceo"],
            created=datetime(2026, 5, 20, 14, 0, 0),
            schema_version=1,
        )
        assert m.type == "meeting"

    def test_missing_attendees_raises(self):
        with pytest.raises(ValidationError):
            Meeting(
                type="meeting",
                created=datetime(2026, 5, 20, 14, 0, 0),
                schema_version=1,
            )


# ---------------------------------------------------------------------------
# PAGE_TYPES registry
# ---------------------------------------------------------------------------

class TestPageTypesRegistry:
    def test_all_nine_types_present(self):
        expected = {
            "spec", "session", "decision", "mention", "feedback",
            "handoff", "retro", "open-question", "meeting",
        }
        assert set(PAGE_TYPES.keys()) == expected

    def test_registry_maps_to_correct_models(self):
        assert PAGE_TYPES["spec"] is Spec
        assert PAGE_TYPES["session"] is Session
        assert PAGE_TYPES["decision"] is Decision
        assert PAGE_TYPES["mention"] is Mention
        assert PAGE_TYPES["feedback"] is Feedback
        assert PAGE_TYPES["handoff"] is Handoff
        assert PAGE_TYPES["retro"] is Retro
        assert PAGE_TYPES["open-question"] is OpenQuestion
        assert PAGE_TYPES["meeting"] is Meeting

    def test_brief_excluded_from_registry(self):
        assert "brief" not in PAGE_TYPES

    def test_instantiate_via_registry(self):
        model_cls = PAGE_TYPES["spec"]
        s = model_cls(
            type="spec",
            status="approved",
            id="001",
            created=date(2026, 1, 1),
            updated=date(2026, 1, 2),
            owner="kai-cto",
            schema_version=1,
        )
        assert s.status == "approved"

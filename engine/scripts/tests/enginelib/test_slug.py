import pytest

from enginelib import slug


@pytest.mark.parametrize("raw,expected", [
    ("Move To Base L2", "move-to-base-l2"),
    ("need: approval (v2)!", "need-approval-v2"),
    ("a   b---c", "a-b-c"),
    ("  hello  ", "hello"),
    ("", "untitled"),
    ("!!!???", "untitled"),
    ("Привет мир", "untitled"),       # ASCII-only contract
    ("Café v2", "caf-v2"),            # keeps ASCII parts
])
def test_slugify(raw, expected):
    assert slug.slugify(raw) == expected


def test_slugify_caps_40_chars():
    out = slug.slugify("this is a very long title that should get truncated somewhere")
    assert len(out) <= 40


def test_slugify_truncation_trims_trailing_dash():
    out = slug.slugify("aa bbb ccc ddd eee fff ggg hhh iii jjj kkk")
    assert len(out) <= 40 and not out.endswith("-")


def test_mention_id_full():
    assert slug.mention_id("nexus-ceo", "spark-cmo", "video approval",
                           "2026-04-22T16:30:00-03:00") == \
        "2026-04-22-1630-nexus-ceo-to-spark-cmo-video-approval"


def test_mention_id_no_seconds():
    assert slug.mention_id("alice", "bob", "hello", "2026-04-22T16:30") == \
        "2026-04-22-1630-alice-to-bob-hello"


def test_mention_id_rejects_date_only():
    with pytest.raises(ValueError, match="ISO-8601"):
        slug.mention_id("alice", "bob", "hello", "2026-04-22")


def test_mention_id_empty_body_untitled():
    assert slug.mention_id("alice", "bob", "", "2026-04-22T16:30") == \
        "2026-04-22-1630-alice-to-bob-untitled"


def test_decision_id():
    assert slug.decision_id("move-to-base", "2026-04-22") == "2026-04-22-move-to-base"


def test_session_id():
    assert slug.session_id("nexus-ceo", "video-review", "2026-04-22") == \
        "2026-04-22-nexus-ceo-video-review"

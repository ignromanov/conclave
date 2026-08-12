import pytest
from pydantic import ValidationError

from enginelib.protocols.model import STAGE_SEQUENCE, ProtocolMeta


def _valid(**over):
    base = dict(stages=["plan"], tiers=["work"], task_types=["dev"],
                binding="required", last_reviewed="2026-08-07")
    base.update(over)
    return base


def test_accepts_a_valid_meta():
    m = ProtocolMeta(**_valid())
    assert m.stages == ["plan"]
    assert m.external_skill is None


def test_stage_sequence_is_the_documented_order():
    assert STAGE_SEQUENCE == (
        "clarify", "design", "spec", "plan", "implement", "verify", "deliver",
    )


def test_every_stage_literal_appears_in_the_sequence():
    # Completeness assertion: the enum and the ordering constant cannot drift apart.
    import typing
    from enginelib.protocols import model
    literals = set(typing.get_args(model.Stage))
    assert literals == set(STAGE_SEQUENCE)


@pytest.mark.parametrize("field", ["stages", "tiers", "task_types", "binding"])
def test_axis_is_required(field):
    data = _valid()
    del data[field]
    with pytest.raises(ValidationError):
        ProtocolMeta(**data)


def test_unknown_enum_value_is_rejected():
    with pytest.raises(ValidationError):
        ProtocolMeta(**_valid(stages=["marketing"]))


def test_empty_axis_is_rejected():
    # An empty list is the wildcard trap wearing a different hat.
    with pytest.raises(ValidationError):
        ProtocolMeta(**_valid(tiers=[]))


def test_a_yaml_date_is_normalized_not_rejected():
    # YAML turns an unquoted 2026-08-07 into datetime.date. The unit test alone never
    # sees this — only the file round-trip does — so pin it here where the type lives.
    import datetime

    m = ProtocolMeta(**_valid(last_reviewed=datetime.date(2026, 8, 7)))
    assert m.last_reviewed == "2026-08-07"


def test_external_skill_marks_an_adapter():
    m = ProtocolMeta(**_valid(external_skill="pytest-advanced"))
    assert m.is_adapter is True

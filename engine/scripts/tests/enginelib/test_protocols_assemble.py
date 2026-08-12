from pathlib import Path

from enginelib.protocols.assemble import select
from enginelib.protocols.model import ProtocolFile, ProtocolMeta


def pf(name, stages, tiers=("work",), task_types=("dev",)):
    return ProtocolFile(
        path=Path(f"/reg/{name}.md"),
        meta=ProtocolMeta(stages=list(stages), tiers=list(tiers),
                          task_types=list(task_types), binding="required"),
    )


def test_or_within_an_axis():
    f = pf("a", ["plan"], task_types=["dev", "content"])
    assert select([f], "work", "content") == [f]


def test_and_across_axes():
    # Right task_type, wrong tier -> excluded. No cross-axis OR anywhere.
    f = pf("a", ["plan"], tiers=["quick"], task_types=["dev"])
    assert select([f], "work", "dev") == []


def test_ordered_by_the_stage_sequence():
    late = pf("late", ["verify"])
    early = pf("early", ["clarify"])
    mid = pf("mid", ["plan"])
    got = select([late, early, mid], "work", "dev")
    assert [p.path.stem for p in got] == ["early", "mid", "late"]


def test_multi_stage_sorts_by_earliest():
    spanning = pf("spanning", ["deliver", "design"])
    plan_only = pf("plan_only", ["plan"])
    got = select([spanning, plan_only], "work", "dev")
    assert [p.path.stem for p in got] == ["spanning", "plan_only"]


def test_deduplicates_by_path():
    a = pf("same", ["plan"])
    b = pf("same", ["plan"])
    assert len(select([a, b], "work", "dev")) == 1


def test_quick_tier_excludes_work_only_protocols():
    assert select([pf("a", ["implement"], tiers=["work"])], "quick", "dev") == []

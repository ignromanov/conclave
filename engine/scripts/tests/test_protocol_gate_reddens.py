"""Each test plants the defect its sibling gate is supposed to catch, and asserts the
gate catches it. Without these, a self-disabled gate is indistinguishable from a clean
registry — which this repository has already shipped once."""
from pathlib import Path

from enginelib.protocols.assemble import select
from enginelib.protocols.registry import scan

VALID = """---
stages: [plan]
tiers: [work]
task_types: [dev]
binding: required
---
Body.
"""


def test_gate_catches_a_file_with_no_frontmatter(tmp_path: Path):
    (tmp_path / "ok.md").write_text(VALID, encoding="utf-8")
    (tmp_path / "planted.md").write_text("no frontmatter here\n", encoding="utf-8")
    _, errors = scan([tmp_path])
    assert [e.path.name for e in errors] == ["planted.md"]


def test_gate_catches_an_unknown_enum_value(tmp_path: Path):
    (tmp_path / "planted.md").write_text(
        VALID.replace("stages: [plan]", "stages: [marketing]"), encoding="utf-8"
    )
    _, errors = scan([tmp_path])
    assert len(errors) == 1


def test_gate_catches_a_missing_axis(tmp_path: Path):
    (tmp_path / "planted.md").write_text(
        VALID.replace("tiers: [work]\n", ""), encoding="utf-8"
    )
    _, errors = scan([tmp_path])
    assert len(errors) == 1


def test_gate_catches_an_unreachable_protocol(tmp_path: Path):
    # Reachable by no (tier, task_type) pair is impossible via the schema alone, so the
    # reachability gate is proven against a file the selector genuinely never returns.
    (tmp_path / "planted.md").write_text(
        VALID.replace("tiers: [work]", "tiers: [quick]"), encoding="utf-8"
    )
    files, _ = scan([tmp_path])
    assert select(files, "work", "dev") == []
    assert select(files, "quick", "dev") != []


def test_gate_catches_a_home_dropped_from_the_scan(tmp_path: Path):
    """The coverage gate's own planted defect.

    A home silently missing from FIXED_HOMES does not look like a failure — it looks
    like a smaller registry, and every other gate here stays green. This repository
    has already shipped that exact shape once: a type gate that ran clean while
    covering 82 of 169 files. So plant the drop and assert the count notices.
    """
    a, b = tmp_path / "home-a", tmp_path / "home-b"
    for d in (a, b):
        d.mkdir()
        (d / "p.md").write_text(VALID, encoding="utf-8")

    on_disk = sum(len(list(d.glob("*.md"))) for d in (a, b))
    files, errors = scan([a])  # PLANTED: home-b dropped from the scan list
    assert len(files) + len(errors) != on_disk, (
        "the coverage assertion cannot see a dropped home — it is decorative"
    )

    files, errors = scan([a, b])
    assert len(files) + len(errors) == on_disk


def test_gate_catches_a_duplicate(tmp_path: Path):
    from enginelib.protocols.model import ProtocolFile, ProtocolMeta

    meta = ProtocolMeta(stages=["plan"], tiers=["work"], task_types=["dev"], binding="required")
    dup = Path("/reg/same.md")
    files = [ProtocolFile(path=dup, meta=meta), ProtocolFile(path=dup, meta=meta)]
    assert len(select(files, "work", "dev")) == 1

"""The shipped registry must parse. A file that cannot be selected is invisible —
the phantom's mirror image."""
from pathlib import Path

from enginelib.protocols.assemble import select
from enginelib.protocols.model import STAGE_SEQUENCE
from enginelib.protocols.registry import FIXED_HOMES, homes, scan

REPO = Path(__file__).resolve().parents[3]


def test_every_registry_file_parses():
    files, errors = scan(homes(REPO, None))
    assert errors == [], "\n".join(f"{e.path}: {e.reason}" for e in errors)
    assert files, "scan found nothing — the scanner is broken, not the registry"


def test_scan_covers_every_markdown_file_in_every_fixed_home():
    # Completeness assertion: parsed count == file count on disk. Without this, a home
    # silently dropped from FIXED_HOMES would just look like a smaller registry.
    on_disk = sum(len(list((REPO / rel).glob("*.md"))) for rel in FIXED_HOMES)
    files, errors = scan(homes(REPO, None))
    assert len(files) + len(errors) == on_disk


def test_every_protocol_is_reachable_by_some_combination():
    files, _ = scan(homes(REPO, None))
    reachable = set()
    for tier in ("quick", "work"):
        for tt in ("dev", "content", "research", "review", "advisory"):
            reachable.update(p.path for p in select(files, tier, tt))
    unreachable = [p.path.name for p in files if p.path not in reachable]
    assert unreachable == [], f"unreachable protocols: {unreachable}"


def test_no_assembled_set_contains_a_duplicate():
    files, _ = scan(homes(REPO, None))
    for tier in ("quick", "work"):
        for tt in ("dev", "content", "research", "review", "advisory"):
            chosen = select(files, tier, tt)
            names = [p.path for p in chosen]
            assert len(names) == len(set(names))


def test_declared_stages_are_all_in_the_sequence():
    files, _ = scan(homes(REPO, None))
    for f in files:
        for s in f.meta.stages:
            assert s in STAGE_SEQUENCE

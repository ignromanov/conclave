"""Every record directory under `agent-memory/advisors/` must have a rename class.

Commissioned by sage-cto's 117 §6, which asks for `checkpoints/` to be registered in
`rename._classify`. Registering one directory is not the fix: the same requirement has
already been missed twice, and the miss is silent both times.

`rename._classify` ends in `return UNCLASSIFIED` — anything the enumeration does not
name falls through. `plan()` then routes UNCLASSIFIED into `skipped`, so the files are
reported and left alone. That is the right behaviour for a class nobody thought of, and
it is exactly why the omission survives: a rename SUCCEEDS with a retired id still on
disk, and the only reader is whoever scrolls the plan.

Measured on this instance before the gate was written: `rename.plan("forge-chro", …)`
put 60 files in `skipped`, and one of them was
`agent-memory/advisors/retros/2026-09-08-retro.md` — a sibling of `sessions/`, written by
`commands/retro.md`, whose page type `retro` has been in `briefing.schema.PAGE_TYPES`
since the schema was authored. The comment at `rename.py:334-337` records the previous
occurrence (`ops/decisions/`), found "by the `unclassified` bucket on a real instance,
not by design". This is the gate that turns that into a design.

**Why the names are discovered rather than listed.** A directory name is already written
down in four independent places — `rename._classify`, `briefing.backfill._DIR_TYPE_MAP`,
`init.conclave_init.DATA_SUBDIRS`, and the `_instance` fixture in
`tests/cmd/test_advisor_rename.py` — and they disagree today. A fifth hand-maintained
list in this file would not detect drift; it would join it. So the corpus comes from the
two places that actually PRODUCE such a directory:

  1. the scaffolder's `DATA_SUBDIRS`, imported (not grepped) so a registration behind a
     broken import fails loudly rather than passing;
  2. the shipped contracts in `commands/` and `skills/`, where a create-on-write
     directory like `retros/` is named and nowhere else.

**Two exclusions, both with a reason the data forced.**

`CHANGELOG.md` is a record of what changed, not an instruction to a running instance;
its one hit names `advisors/feedback/`, a location `feedback/paths.py` retired under
GH#105. Failing the suite over a changelog entry is how a gate gets switched off.

A slug shaped like an advisor id (`<name>-<role>`, role from the closed vocabulary) is a
PER-ADVISOR directory, not a record class: its whole name is the id, so the fix is a path
rewrite rather than a class, and it has its own open issue (conclave#99 — duty artifacts).
The test is `advisors.validate_advisor_id`, the engine's own vocabulary, so this carve-out
cannot drift away from what an advisor id means.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from enginelib import advisors, rename

# Inline code spans first, then the directory inside them. Splitting the two keeps the
# second pattern from having to defend against matching across a span boundary — the
# same shape `test_contract_verbs_exist.py` uses, and for the same reason: a bare scan of
# prose returns sentences.
_SPAN = re.compile(r"`([^`\n]+)`")
_ADVISOR_DIR = re.compile(r"agent-memory/advisors/([a-z][a-z0-9_-]*)/")

# The shipped surface an installed instance loads.
_CONTRACT_DIRS = ("commands", "skills")


def _repo_root() -> Path:
    # engine/scripts/tests/<this file> → parents[3] is the CODE checkout root.
    return Path(__file__).resolve().parents[3]


def _is_advisor_id(slug: str) -> bool:
    try:
        advisors.validate_advisor_id(slug)
    except ValueError:
        return False
    return True


def _scaffolded_dirs() -> set[str]:
    """Leaf names of the advisor directories `/conclave:init` creates."""
    from init.conclave_init import DATA_SUBDIRS

    prefix = "agent-memory/advisors/"
    return {d[len(prefix):] for d in DATA_SUBDIRS if d.startswith(prefix)}


def _documented_dirs() -> dict[str, str]:
    """name → first `path:line` that names it, over the shipped contracts."""
    root = _repo_root()
    found: dict[str, str] = {}
    for directory in _CONTRACT_DIRS:
        for path in sorted((root / directory).rglob("*.md")):
            if path.name == "CHANGELOG.md":
                continue
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                for span in _SPAN.findall(line):
                    for name in _ADVISOR_DIR.findall(span):
                        if _is_advisor_id(name):
                            continue
                        found.setdefault(name, f"{path.relative_to(root)}:{lineno}")
    return found


def _classify_dir(tmp_path: Path, name: str) -> str:
    """The class `rename.plan()` would give a record sitting in that directory."""
    data_root = tmp_path
    record = data_root / "agent-memory" / "advisors" / name / "2026-01-01-record.md"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text("---\nadvisor: nova-cto\n---\n\nbody\n", encoding="utf-8")
    return rename._classify(record, data_root, [])


def _record_dirs() -> dict[str, str]:
    dirs = {name: "init.conclave_init.DATA_SUBDIRS" for name in _scaffolded_dirs()}
    for name, where in _documented_dirs().items():
        dirs.setdefault(name, where)
    return dirs


# ---------------------------------------------------------------------------
# Vacuity + decoys — the gate states its own denominators before asserting
# ---------------------------------------------------------------------------

def test_the_gate_found_both_of_its_producers():
    """An empty corpus makes the gate below pass while measuring nothing.

    Both halves are asserted separately: the scaffolder is an import that a refactor can
    rename away, and the contract scan is a regex that a formatting change can silence.
    Either failing alone would leave the other looking healthy.
    """
    scaffolded = _scaffolded_dirs()
    documented = _documented_dirs()
    assert len(scaffolded) >= 4, (
        f"only {len(scaffolded)} advisor dirs in DATA_SUBDIRS — the import is measuring nothing"
    )
    assert len(documented) >= 5, (
        f"only {len(documented)} advisor dirs found in {_CONTRACT_DIRS} — the scan is broken"
    )


def test_an_advisor_id_is_not_a_record_class():
    """`agent-memory/advisors/kai-cto/` appears in a shipped template.

    It is a per-advisor directory, not a record class, and conclave#99 owns it. Without
    this filter the gate would redden on a real but different defect, and the fix for
    THAT one is a path rewrite, not an entry in the enumeration.
    """
    assert _is_advisor_id("kai-cto")
    assert _is_advisor_id("forge-chro")
    assert not _is_advisor_id("retros")
    assert not _is_advisor_id("checkpoints")
    assert "kai-cto" not in _documented_dirs()


def test_the_gate_can_fail(tmp_path):
    """A directory nobody registered classifies UNCLASSIFIED.

    Without this, a `_classify` that returned HISTORY unconditionally would make every
    assertion below pass — the failure mode this repository has hit before, where a gate
    passes its own meta-test and the real defect too.
    """
    assert _classify_dir(tmp_path, "a-directory-nobody-registered") == rename.UNCLASSIFIED


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_checkpoints_is_registered_before_its_producer_exists(tmp_path):
    """The commissioned half of 117 §6.1, which the corpus above cannot yet reach.

    `checkpoints/` is named by no shipped contract and by no scaffolder entry today —
    sage-cto's mechanism change adds both. The gate above is therefore blind to it until
    that change lands, which is precisely backwards: the registration exists so that the
    mechanism does not have to remember. Pinned explicitly, and deliberately redundant
    with the parametrized gate once the producer arrives.

    HISTORY, not REGEN: a checkpoint is an in-flight session record that `close_session`
    folds into `sessions/`. REGEN deletes what it classifies, and a checkpoint is not
    derivable from anything.
    """
    assert _classify_dir(tmp_path, "checkpoints") == rename.HISTORY


@pytest.mark.parametrize("name", sorted(_record_dirs()))
def test_every_advisor_record_directory_has_a_rename_class(name, tmp_path):
    cls = _classify_dir(tmp_path, name)
    assert cls != rename.UNCLASSIFIED, (
        f"`agent-memory/advisors/{name}/` is produced by {_record_dirs()[name]} but "
        f"`rename._classify` does not name it, so an advisor rename leaves every record "
        f"in it pointing at the retired id. Add it to the enumeration at "
        f"enginelib/rename.py:328 with the class it deserves."
    )

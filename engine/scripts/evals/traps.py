"""traps.py — the held-out trap store, and how a trial's fixture gets its records.

The trap definitions and the seed bundles live in the DATA repo (`.conclave/eval/`), which is a
separate git repo AND gitignored from CODE. `git archive` — how a fixture is built — cannot emit
them. That is the whole holdout mechanism: not a rule the builder follows, a fact about git.

Seeding runs AFTER `assert_no_leakage`: the fixture arrives with no `.conclave/` at all, and the
seed puts back exactly the record tree the trap needs the agent to be able to destroy.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import yaml

from evals.fixture import Fixture
from evals.predicates import PREDICATES


@dataclass(frozen=True)
class Trap:
    id: str
    principle: str
    predicate: str
    prompt: str
    seed: str
    notes: str = ""


def load_traps(store: Path) -> list[Trap]:
    traps: list[Trap] = []
    for path in sorted((store / "traps").glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        trap = Trap(
            id=raw["id"],
            principle=str(raw["principle"]),
            predicate=raw["predicate"],
            prompt=raw["prompt"],
            seed=raw["seed"],
            notes=raw.get("notes", ""),
        )
        if trap.predicate not in PREDICATES:
            raise ValueError(f"trap {trap.id}: unknown predicate {trap.predicate!r}")
        traps.append(trap)
    return traps


def seed_fixture(fx: Fixture, trap: Trap, store: Path) -> None:
    """Copy the trap's seed bundle into the fixture as its `.conclave/` DATA tree."""
    src = store / "seeds" / trap.seed
    if not src.is_dir():
        raise FileNotFoundError(f"trap {trap.id}: seed bundle absent: {src}")
    shutil.copytree(src, fx.root / ".conclave", dirs_exist_ok=True)


def assert_seed_safe(fx: Fixture) -> None:
    """A seed bundle is hand-authored, so it can smuggle the eval back in. Check, don't trust."""
    forbidden = fx.root / ".conclave" / "eval"
    if forbidden.exists():
        raise AssertionError(f"seed leaks the eval into the fixture: {forbidden}")
    strays = [str(p.relative_to(fx.root)) for p in fx.root.rglob("constitution.md")]
    if strays:
        raise AssertionError(f"seed restored a charter into the fixture: {strays}")

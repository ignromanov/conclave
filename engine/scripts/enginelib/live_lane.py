"""live_lane.py — the plan behind `engine test live`, as data rather than as YAML.

The `live_instance`-marked tests read a real instance tree instead of a synthetic fixture, so
they cannot run under the hermetic default suite. Until now the only thing that knew how to give
them one was a CI job: seed a project with the real scaffolder, export
CONCLAVE_LIVE_INSTANCE_ROOT, run `-m live_instance`, fail on any skip. That made the lane
unreachable before push — a 26-file refactor's one semantic behaviour change was found by CI and
not by the author (feedback 1787103625/i1), because locally those 31 tests reported `skipped` and
`skipped` is what a green run looks like.

This module holds the same four decisions as pure values so the CLI and the workflow can share
one copy. Two copies of a plan is the defect PR #144 spent a session removing from the path
resolvers; reintroducing it one file later would be worse than leaving the lane unreachable.

I/O-free by construction: nothing here touches the filesystem or spawns a process. The adapter
(`engine/cmd/test.py`) owns both.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

#: Instance-root variables scrubbed from every child process this plan describes.
#:
#: Load-bearing, not hygiene. A dogfooding shell exports CONCLAVE_AI_ROOT at the *live* DATA
#: root; an unscrubbed scaffolder would inherit it and seed into the operator's real instance.
#: Same list as the suite's `_INSTANCE_ROOT_VARS` — the retired alias stays in it because
#: scrubbing a name costs nothing and inheriting one costs the tree.
SCRUBBED_ROOT_VARS = ("CONCLAVE_AI_ROOT", "VOIDPAY_AI_ROOT", "CLAUDE_PROJECT_DIR")

#: Set by the seed step, read by the marker's fixture. Deliberately not one of the above:
#: an ambient export must never be able to arm the lane by accident.
LIVE_INSTANCE_ROOT_VAR = "CONCLAVE_LIVE_INSTANCE_ROOT"

#: What `conclave init` names the DATA root it creates under the project dir.
DATA_DIRNAME = ".conclave"

#: pytest's "collected nothing" exit. A mistyped marker expression selects zero tests and exits
#: 5 — distinct from 0, and the reason the workflow ran the marker through a real invocation
#: rather than trusting the expression.
EXIT_NO_TESTS_COLLECTED = 5

#: `-rfEs` (pytest.ini addopts) renders one such line per skipped test in the short summary.
_SKIPPED_LINE = re.compile(r"^SKIPPED\b", re.MULTILINE)


@dataclass(frozen=True)
class Step:
    """One child process: what to run, and what to overlay on the inherited environment."""

    name: str
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    scrub: tuple[str, ...] = ()


@dataclass(frozen=True)
class Verdict:
    ok: bool
    reason: str


def data_root_for(seed_dir: Path) -> Path:
    """Where `plan_seed`'s scaffolder is expected to put the DATA root."""
    return Path(seed_dir) / DATA_DIRNAME


def plan_seed(
    *,
    python: str,
    engine_dir: Path,
    seed_dir: Path,
    roster_name: str = "Live Lane Instance",
) -> Step:
    """Scaffold a fresh instance under `seed_dir` with the engine's own initialiser.

    The real `conclave_init.py`, never a hand-built fixture tree: these tests assert that the
    path resolvers and briefing scans agree with the layout the scaffolder actually produces.
    A hand-written tree would only assert that the tree matches the tests.

    `engine_dir` is the CODE `engine/` directory of the checkout under test — passed in rather
    than resolved from the environment, so the lane always exercises the tree the caller is
    standing in and never one an ambient CONCLAVE_ENGINE_ROOT points at.
    """
    engine_dir = Path(engine_dir)
    return Step(
        name="seed",
        argv=[python, str(engine_dir / "scripts" / "init" / "conclave_init.py")],
        env={
            "CONCLAVE_INIT_NONINTERACTIVE": "1",
            "CLAUDE_PROJECT_DIR": str(seed_dir),
            "CONCLAVE_ENGINE_ROOT": str(engine_dir),
            "ROSTER_NAME": roster_name,
            "PYTHONPATH": str(engine_dir / "scripts"),
        },
        scrub=SCRUBBED_ROOT_VARS,
    )


def plan_pytest(*, python: str, instance_root: Path, extra_args: list[str] | None = None) -> Step:
    """Run the marked tests against the seeded instance."""
    return Step(
        name="live lane",
        argv=[python, "-m", "pytest", "-m", "live_instance", *(extra_args or [])],
        env={LIVE_INSTANCE_ROOT_VAR: str(instance_root)},
        scrub=SCRUBBED_ROOT_VARS,
    )


def child_env(step: Step, base: dict[str, str] | None = None) -> dict[str, str]:
    """`base` with the step's scrub list removed and its overlay applied, in that order.

    Order matters: `plan_seed` sets CLAUDE_PROJECT_DIR, which is also on the scrub list. Scrub
    first, overlay second, or the step cannot name the very variable it needs to control.
    """
    env = dict(os.environ if base is None else base)
    for var in step.scrub:
        env.pop(var, None)
    env.update(step.env)
    return env


def verdict(exit_code: int, output: str) -> Verdict:
    """Did the lane actually run every test it selected, and did they pass?

    Three distinct failures, each of which has previously read as green:

    * a skip — the marked tests skip when the root is unset, and pytest exits 0 on an
      all-skipped run, so a seed step that failed to export the root reported success on 31
      tests that never executed (GH#105);
    * an empty selection — a mistyped marker expression collects nothing and exits 5;
    * an ordinary failure.
    """
    if exit_code == EXIT_NO_TESTS_COLLECTED:
        return Verdict(False, "no tests matched `-m live_instance` — the lane selected nothing")
    skipped = len(_SKIPPED_LINE.findall(output))
    if skipped:
        return Verdict(
            False,
            f"{skipped} live_instance test(s) skipped — the lane must run every test it selects",
        )
    if exit_code != 0:
        return Verdict(False, f"pytest exited {exit_code}")
    return Verdict(True, "every selected test ran and passed")

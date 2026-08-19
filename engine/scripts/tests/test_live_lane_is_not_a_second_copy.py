"""The workflow must invoke `engine test live`, not restate it.

PR #144 spent a session collapsing two drifted copies of `repo_root()`; the copy that had
quietly stopped honouring an env override was the one that hid a real defect. The live lane
was the same shape of hazard in a different language: its seed/assert/run/no-skips sequence
existed only as YAML, so the lane could not be run before pushing, and any local reimplementation
would have been a second copy free to drift from the one CI trusts.

The plan now lives in `enginelib/live_lane.py` and the workflow calls the verb. These tests fail
if the steps grow back — a drift the YAML cannot detect about itself.
"""
import pathlib

import pytest

yaml = pytest.importorskip("yaml")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
JOB = "live-instance"


def _run_steps() -> list[str]:
    spec = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    return [s["run"] for s in spec["jobs"][JOB]["steps"] if "run" in s]


def test_the_job_exists_and_runs_the_verb():
    assert any("engine test live" in run for run in _run_steps()), (
        f"the {JOB} job no longer invokes `engine test live`"
    )


@pytest.mark.parametrize(
    ("fragment", "why"),
    [
        ("conclave_init.py", "seeding belongs to live_lane.plan_seed, not to the workflow"),
        ("CONCLAVE_LIVE_INSTANCE_ROOT", "arming the marker belongs to live_lane.plan_pytest"),
        ("-m live_instance", "selecting the marker belongs to live_lane.plan_pytest"),
        ("^SKIPPED", "the skip-is-a-failure rule belongs to live_lane.verdict"),
    ],
)
def test_the_job_does_not_restate_the_plan(fragment, why):
    offenders = [run for run in _run_steps() if fragment in run]
    assert not offenders, f"{JOB} restates `{fragment}` — {why}\n{offenders}"


def test_the_verb_is_registered_on_the_dispatcher():
    """A workflow calling a noun the dispatcher does not carry fails only in CI, and only
    after the seed step has already run.

    Asserted against the parser's own choices, not against `parse_args(["test", "live"])`
    raising — an unregistered noun raises SystemExit too (argparse's usage error), so that
    assertion would have passed whether or not the verb existed.
    """
    from engine.__main__ import _build_parser

    nouns = {
        name
        for action in _build_parser()._subparsers._group_actions
        for name in action.choices
    }
    assert "test" in nouns, f"`engine test` is not registered; nouns are {sorted(nouns)}"

    verbs = _build_parser().parse_args(["test", "live"])
    assert verbs.test_verb == "live"

"""Tests for enginelib.live_lane — the plan behind `engine test live`.

The load-bearing evidence for this feature is a mutation run, not these tests: strip the env
overlay from `plan_pytest` and the lane skips all 31 tests, pytest exits 0, and the verb must
still fail. What is unit-tested here is the part that mutation cannot reach cheaply — the
scrub/overlay ordering, and each of the three failures that have historically read as green.
"""
from pathlib import Path

from enginelib.live_lane import (
    SCRUBBED_ROOT_VARS,
    Step,
    child_env,
    data_root_for,
    plan_pytest,
    plan_seed,
    verdict,
)


class TestPlanSeed:
    def test_runs_the_checkouts_own_scaffolder(self):
        step = plan_seed(python="py", engine_dir=Path("/co/engine"), seed_dir=Path("/seed"))
        assert step.argv == ["py", "/co/engine/scripts/init/conclave_init.py"]

    def test_points_the_scaffolder_at_the_seed_dir_not_the_ambient_project(self):
        """CLAUDE_PROJECT_DIR is on the scrub list AND set by this step.

        Scrub-then-overlay is the only order that works. Reversed, the step would erase the
        very variable it needs to control and the scaffolder would fall back to the caller's
        project — which on a dogfood run is the operator's live instance.
        """
        step = plan_seed(python="py", engine_dir=Path("/co/engine"), seed_dir=Path("/seed"))
        assert "CLAUDE_PROJECT_DIR" in SCRUBBED_ROOT_VARS
        env = child_env(step, base={"CLAUDE_PROJECT_DIR": "/the/operators/real/project"})
        assert env["CLAUDE_PROJECT_DIR"] == "/seed"

    def test_an_ambient_data_root_cannot_reach_the_scaffolder(self):
        step = plan_seed(python="py", engine_dir=Path("/co/engine"), seed_dir=Path("/seed"))
        env = child_env(step, base={"CONCLAVE_AI_ROOT": "/live/.conclave"})
        assert "CONCLAVE_AI_ROOT" not in env

    def test_the_engine_root_is_the_tree_under_test_not_the_ambient_one(self):
        step = plan_seed(python="py", engine_dir=Path("/co/engine"), seed_dir=Path("/seed"))
        env = child_env(step, base={"CONCLAVE_ENGINE_ROOT": "/some/other/checkout/engine"})
        assert env["CONCLAVE_ENGINE_ROOT"] == "/co/engine"


class TestPlanPytest:
    def test_selects_the_marker_and_arms_it(self):
        step = plan_pytest(python="py", instance_root=Path("/seed/.conclave"))
        assert step.argv == ["py", "-m", "pytest", "-m", "live_instance"]
        assert child_env(step, base={})["CONCLAVE_LIVE_INSTANCE_ROOT"] == "/seed/.conclave"

    def test_extra_args_land_after_the_selection(self):
        step = plan_pytest(python="py", instance_root=Path("/x"), extra_args=["-k", "scans"])
        assert step.argv[-2:] == ["-k", "scans"]


def test_data_root_for_names_what_the_scaffolder_creates():
    assert data_root_for(Path("/seed")) == Path("/seed/.conclave")


def test_child_env_leaves_unrelated_variables_alone():
    step = Step("s", ["x"], {"A": "1"}, scrub=("B",))
    assert child_env(step, base={"B": "2", "C": "3"}) == {"A": "1", "C": "3"}


class TestVerdict:
    """Each case below has, at some point, been reported as a passing run."""

    def test_a_clean_run_passes(self):
        assert verdict(0, "31 passed, 2040 deselected in 17.0s").ok

    def test_a_skip_fails_even_though_pytest_exited_zero(self):
        out = (
            "SKIPPED [1] tests/briefing/test_scans.py:12: needs a live instance root\n"
            "SKIPPED [1] tests/briefing/test_paths.py:30: needs a live instance root\n"
            "31 skipped, 2040 deselected in 1.8s\n"
        )
        v = verdict(0, out)
        assert not v.ok
        assert "2 live_instance test(s) skipped" in v.reason

    def test_an_empty_selection_fails(self):
        v = verdict(5, "2071 deselected in 2.5s")
        assert not v.ok
        assert "selected nothing" in v.reason

    def test_an_ordinary_failure_fails(self):
        v = verdict(1, "1 failed, 30 passed")
        assert not v.ok
        assert "exited 1" in v.reason

    def test_the_word_skipped_mid_line_is_not_a_skip(self):
        """`^SKIPPED` is anchored: a failure message quoting the word must not read as a skip,
        or the verdict would report the wrong reason for a genuinely red run."""
        assert verdict(0, "test_x asserts that nothing was skipped\n1 passed").ok

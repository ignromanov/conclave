"""Which checkout is this process actually running? (GH#126)

The editable install writes the MAIN checkout's `engine/scripts` onto `sys.path` for every
Python process on the machine, so a bare `python -m engine` inside a worktree imports code
from a tree the caller is not standing in — and reports on it as if it were theirs.
"""
from pathlib import Path

from enginelib.provenance import checkout_root_of, diagnose_tree


def _checkout(root: Path) -> Path:
    """Materialise the marker that makes a directory a Conclave CODE checkout."""
    entry = root / "engine" / "scripts" / "engine" / "__main__.py"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text("")
    return root


def test_checkout_root_is_the_nearest_enclosing_checkout(tmp_path):
    outer = _checkout(tmp_path / "main")
    inner = _checkout(outer / "worktrees" / "feature")
    deep = inner / "engine" / "scripts"

    assert checkout_root_of(deep) == inner, "the nearest checkout wins, not the outermost"


def test_checkout_root_is_none_outside_any_checkout(tmp_path):
    elsewhere = tmp_path / "some" / "consumer" / "project"
    elsewhere.mkdir(parents=True)

    assert checkout_root_of(elsewhere) is None


def test_silent_when_the_running_tree_is_the_tree_you_stand_in(tmp_path):
    root = _checkout(tmp_path / "main")

    assert diagnose_tree(
        module_file=root / "engine" / "scripts" / "engine" / "__main__.py",
        cwd=root,
    ) is None


def test_silent_when_the_caller_is_not_inside_a_checkout(tmp_path):
    """The consumer case. A plugin install runs from the user's project, which is not a
    Conclave checkout — there is no second tree to compare against, so there is no claim
    to make. A detector that warns here would be turned off, and stop catching GH#126."""
    root = _checkout(tmp_path / "plugin")
    consumer = tmp_path / "someones-project"
    consumer.mkdir()

    assert diagnose_tree(
        module_file=root / "engine" / "scripts" / "engine" / "__main__.py",
        cwd=consumer,
    ) is None


def test_reports_when_standing_in_a_worktree_while_running_the_main_checkout(tmp_path):
    main = _checkout(tmp_path / "main")
    worktree = _checkout(main / "worktrees" / "feature")

    report = diagnose_tree(
        module_file=main / "engine" / "scripts" / "engine" / "__main__.py",
        cwd=worktree / "engine",
    )

    assert report is not None
    assert report.running_from == main
    assert report.standing_in == worktree


def test_the_report_names_both_trees_and_the_pin_that_fixes_it(tmp_path):
    main = _checkout(tmp_path / "main")
    worktree = _checkout(main / "worktrees" / "feature")

    report = diagnose_tree(
        module_file=main / "engine" / "scripts" / "engine" / "__main__.py",
        cwd=worktree,
    )
    message = report.message()

    assert str(main) in message
    assert str(worktree) in message
    # Both pins, because CONCLAVE_ENGINE_ROOT alone does not fix an import path — the
    # distinction that made GH#126 survive three earlier encounters with GH#86.
    assert "PYTHONPATH" in message
    assert "CONCLAVE_ENGINE_ROOT" in message

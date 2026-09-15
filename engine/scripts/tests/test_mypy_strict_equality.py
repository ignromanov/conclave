"""`strict_equality` is in effect, not merely written down.

A flag in `pyproject.toml` is a claim about the configuration; the question a reader
actually has is whether mypy, invoked the way the gate invokes it, rejects the comparison.
GH#31's ruling on audit/doctor applies exactly here — a claim about topology must be a
behavioural assertion rather than a source grep. A test that read the toml would pass on a
config mypy never loads, on a flag a later section overrides, and on a mypy too old to
know the option.

The shape under test is live: `feedback_verify.py:391` read `if _rebuild_index(root) != 0:`
while `_rebuild_index` returned a tuple, so `--apply` took its failure branch
unconditionally and exited 1 with an empty stderr.
"""
from __future__ import annotations

import subprocess

import pytest

from tests.test_mypy_gate import SCRIPTS_ROOT, _mypy_cmd

_CASE = '''def _rebuild_index(root: str) -> tuple[int, str]:
    return (0, "")


def apply(root: str) -> int:
    if _rebuild_index(root) != 0:
        return 1
    return 0
'''


def _run(tmp_path, source: str) -> subprocess.CompletedProcess:
    cmd = _mypy_cmd()
    if cmd is None:
        pytest.skip("mypy is genuinely unavailable")
    f = tmp_path / "case.py"
    f.write_text(source, encoding="utf-8")
    return subprocess.run(
        [*cmd, "--config-file", "pyproject.toml", str(f)],
        cwd=SCRIPTS_ROOT, capture_output=True, text=True,
    )


def test_comparing_a_widened_return_type_to_an_int_is_reported(tmp_path):
    """Reddens under: removing `strict_equality` from `[tool.mypy]`.

    Asserts on the error code rather than the prose, so a mypy release that rewords the
    message does not redden a gate whose subject has not changed.
    """
    r = _run(tmp_path, _CASE)
    assert r.returncode != 0
    assert "comparison-overlap" in r.stdout


def test_a_comparison_whose_types_do_overlap_is_left_alone(tmp_path):
    """Paired: a config that rejected every comparison would satisfy the test above, and
    would also make the flag unadoptable. Reddens under: any blanket ban on `!= 0`.
    """
    r = _run(tmp_path, "def apply(rc: int) -> int:\n    return 1 if rc != 0 else 0\n")
    assert r.returncode == 0, r.stdout

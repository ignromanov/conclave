"""The gate must fail when the mechanism is unarmed.

A test asserting `run(narrated) has crit` passes just as well against a `run` that
returns CRIT unconditionally. This module varies the mechanism and requires the
verdict to follow — the only shape that distinguishes a live check from a constant.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from enginelib.audit.output_discipline import ACTIVE_WINDOW_S, run


def _later() -> float:
    return time.time() + ACTIVE_WINDOW_S + 1


def _transcript(tmp_path: Path, intermediate: int) -> Path:
    lines = [json.dumps({"type": "user", "message": {"content": "go"}})]
    for _ in range(intermediate):
        lines.append(json.dumps({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "a narrated intermediate conclusion" * 4},
            {"type": "tool_use", "id": "t", "name": "Bash", "input": {}},
        ]}}))
    lines.append(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "text", "text": "the terminal report" * 20},
        {"type": "tool_use", "id": "z", "name": "Bash", "input": {}},
        {"type": "tool_use", "id": "y", "name": "Bash", "input": {}},
        {"type": "tool_use", "id": "x", "name": "Bash", "input": {}},
    ]}}))
    p = tmp_path / f"n{intermediate}.jsonl"
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_verdict_follows_the_mechanism(tmp_path: Path) -> None:
    """Same code, two inputs, opposite verdicts. A constant gate fails this."""
    clean = run([_transcript(tmp_path, intermediate=0)], now=_later())
    dirty = run([_transcript(tmp_path, intermediate=8)], now=_later())
    assert clean.crit == [], f"a single-report turn must pass, got {clean.crit}"
    assert dirty.crit, "an 8-block turn must fail"


def test_raising_the_cap_unarms_the_gate(tmp_path: Path) -> None:
    """Explicitly demonstrate the threshold is load-bearing, not decorative."""
    t = _transcript(tmp_path, intermediate=8)
    assert run([t], ratio_cap=0.15, p90_cap=2, now=_later()).crit
    assert run([t], ratio_cap=1.0, p90_cap=99, now=_later()).crit == []

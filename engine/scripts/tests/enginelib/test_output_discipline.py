"""Spec 113 §7.3 — the output-discipline measurement.

The load-bearing test is `test_no_transcripts_is_crit_not_clean`: an audit that
reports clean because it could not run has verified nothing (the specs_registry R6
lesson). The others would all pass on a gate that always returns clean.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from enginelib.audit.output_discipline import (
    ACTIVE_WINDOW_S,
    Measurement,
    measure,
    parse_transcript,
    run,
    settled,
)


def _later() -> float:
    """A clock far enough ahead that files written this instant count as settled.

    Without it every test would write a file, `settled` would judge it in-flight, and
    the whole module would report `unrunnable` — passing the one test that asserts
    unrunnable and telling us nothing about the rest.
    """
    return time.time() + ACTIVE_WINDOW_S + 1


def _line(kind: str, content: object) -> str:
    return json.dumps({"type": kind, "message": {"content": content}})


def _user(text: str) -> str:
    return _line("user", text)


def _tool_result() -> str:
    return _line("user", [{"type": "tool_result", "content": "ok"}])


def _assistant(text: str | None = None, tools: int = 0) -> str:
    content: list[dict[str, object]] = []
    if text is not None:
        content.append({"type": "text", "text": text})
    for i in range(tools):
        content.append({"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {}})
    return _line("assistant", content)


def _write(tmp_path: Path, name: str, lines: list[str]) -> Path:
    p = tmp_path / name
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def test_tool_results_are_not_operator_turns(tmp_path: Path) -> None:
    """A `user` entry carrying a tool_result is the harness, not the operator.

    Counting it as a turn would split one task into many and make every turn look
    disciplined — the metric would improve while nothing changed.
    """
    p = _write(tmp_path, "a.jsonl", [
        _user("do the thing"),
        _assistant("narration one", tools=1),
        _tool_result(),
        _assistant("narration two", tools=1),
        _tool_result(),
        _assistant("narration three", tools=1),
        _assistant("the report"),
    ])
    turns = parse_transcript(p)
    assert len(turns) == 1
    assert turns[0].blocks == 4
    assert turns[0].tool_calls == 3


def test_intermediate_chars_exclude_the_final_block(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.jsonl", [
        _user("go"),
        _assistant("x" * 100, tools=1),
        _assistant("y" * 50, tools=1),
        _assistant("z" * 30, tools=1),
    ])
    (turn,) = parse_transcript(p)
    assert turn.intermediate_chars == 150
    assert turn.final_chars == 30


def test_chatter_turns_are_excluded(tmp_path: Path) -> None:
    """Fewer than min_tool_calls is not a task; including it dilutes the ratio."""
    p = _write(tmp_path, "a.jsonl", [
        _user("hi"),
        _assistant("hello"),
    ])
    m = measure([p], min_tool_calls=3, now=_later())
    assert m.turns == 0


def test_p90_uses_the_baseline_formula(tmp_path: Path) -> None:
    """sorted(xs)[int(len(xs) * 0.9) - 1] — Global Constraint 6.

    Ten turns with intermediate counts 0..9: index int(10 * 0.9) - 1 == 8 -> value 8.
    numpy-style linear interpolation would give 8.1, and the pre-registered
    baseline of 18 would stop being comparable.
    """
    lines: list[str] = []
    for n in range(10):
        lines.append(_user(f"task {n}"))
        for _ in range(n):
            lines.append(_assistant("noise", tools=1))
        lines.append(_assistant("report", tools=3))
    p = _write(tmp_path, "a.jsonl", lines)
    m = measure([p], min_tool_calls=3, now=_later())
    assert m.turns == 10
    assert m.p90_blocks == 8


def test_disciplined_run_is_clean(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.jsonl", [
        _user("go"),
        _assistant(None, tools=5),
        _assistant("the one report"),
    ])
    f = run([p], now=_later())
    assert f.crit == []
    assert f.warn == []


def test_narrated_run_is_flagged(tmp_path: Path) -> None:
    lines = [_user("go")]
    for _ in range(6):
        lines.append(_assistant("here is what I think so far, at some length", tools=1))
    lines.append(_assistant("short report"))
    p = _write(tmp_path, "a.jsonl", lines)
    f = run([p], now=_later())
    assert f.crit, "a 6-block turn must not pass the p90 cap of 2"
    assert any("p90" in m for m in f.crit)


def test_no_transcripts_is_crit_not_clean(tmp_path: Path) -> None:
    """The gate cannot run. Clean would be a false negative, not a pass."""
    f = run([])
    assert f.crit == ["unrunnable: no transcripts found to measure"]


def test_transcripts_present_but_no_work_turns_is_crit(tmp_path: Path) -> None:
    """Files existed and nothing was measurable — still unrunnable, not clean."""
    p = _write(tmp_path, "a.jsonl", [_user("hi"), _assistant("hello")])
    f = run([p], now=_later())
    assert f.crit and "unrunnable" in f.crit[0]


def test_malformed_lines_do_not_abort_the_scan(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.jsonl", [
        "{not json",
        _user("go"),
        _assistant(None, tools=5),
        _assistant("report"),
    ])
    assert len(parse_transcript(p)) == 1


def test_in_flight_transcripts_are_excluded(tmp_path: Path) -> None:
    """The session running the audit is a file in the corpus it measures.

    Measured: identical code reported ratio 0.532 and then 0.538 twenty minutes
    apart, the difference being one turn of the measuring session. Without this
    filter the endpoint drifts and never looks wrong.
    """
    p = _write(tmp_path, "a.jsonl", [_user("go"), _assistant(None, tools=5), _assistant("r")])
    assert settled([p], now=time.time()) == []
    assert settled([p], now=_later()) == [p]
    assert run([p]).crit == ["unrunnable: no transcripts found to measure"]


def test_measurement_is_a_value_not_a_print(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.jsonl", [_user("go"), _assistant(None, tools=5), _assistant("r")])
    m = measure([p], now=_later())
    assert isinstance(m, Measurement)
    assert m.transcripts == 1

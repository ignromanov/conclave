"""enginelib/audit/output_discipline.py — spec 113 §7.3.

I/O-free: no print/argparse/sys.exit. Returns Findings for the adapter to format.

Measures the forced channel (102 §2.1), which the harness writes unconditionally and
the model therefore cannot curate. For each operator turn, every assistant message
carrying text before the last one is narration the protocol forbids.

Two decisions that look like details and are not:

  * A `user` entry whose content is a tool_result is the harness, not the operator.
    Counting it as a turn boundary would split one task into many, and every turn
    would look disciplined while nothing had changed.

  * p90 is `sorted(xs)[int(len(xs) * 0.9) - 1]`, the formula the pre-registered
    baseline used. A different percentile convention is not a better estimate here;
    it silently voids the comparison against 18 that the endpoint is stated in.

  * A transcript still being written is excluded. A session in flight has not yet
    emitted the terminal report of its current turn, so its blocks count as narration
    systematically — and the session running this audit is itself a file in the
    corpus. Measured: identical code reported 0.532 then 0.538 twenty minutes apart,
    the difference being one turn of the measuring session. With the exclusion the
    figure is stable across 300 s, 900 s and 3600 s windows.

Zero measurable turns is CRIT `unrunnable`, never clean: a gate that reports 0 CRIT
because it could not check has verified nothing (the specs_registry R6 lesson).
"""
from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from enginelib.audit import Findings

#: Below this, a turn is conversation rather than a task. Matches the baseline run.
MIN_TOOL_CALLS = 3

#: A transcript touched more recently than this belongs to a session still working.
ACTIVE_WINDOW_S = 300

#: Pre-registered in spec 113 §8, from the 2026-08-21 baseline (0.532 and 18).
RATIO_CAP = 0.15
P90_CAP = 2


@dataclass(frozen=True)
class Turn:
    blocks: int
    intermediate_chars: int
    final_chars: int
    tool_calls: int


@dataclass(frozen=True)
class Measurement:
    transcripts: int
    turns: int
    ratio: float
    p90_blocks: int


def _is_operator_turn(entry: dict[str, object]) -> bool:
    if entry.get("type") != "user":
        return False
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        return True
    if isinstance(content, list):
        return not any(
            isinstance(b, dict) and b.get("type") == "tool_result" for b in content
        )
    return False


def _assistant_parts(entry: dict[str, object]) -> tuple[str, int]:
    """Return (text, tool_call_count) for an assistant entry; ("", 0) otherwise."""
    if entry.get("type") != "assistant":
        return "", 0
    message = entry.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return "", 0
    text = "".join(
        str(b.get("text", ""))
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    ).strip()
    tools = sum(
        1 for b in content if isinstance(b, dict) and b.get("type") == "tool_use"
    )
    return text, tools


def _p90(values: list[int]) -> int:
    """Global Constraint 6 — the baseline's formula, verbatim. Do not 'improve'."""
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[int(len(ordered) * 0.9) - 1]


def parse_transcript(path: Path) -> list[Turn]:
    """Every operator turn in one transcript. A malformed line is skipped, not fatal."""
    turns: list[Turn] = []
    texts: list[str] = []
    tools = 0
    open_turn = False

    def close() -> None:
        nonlocal texts, tools, open_turn
        if open_turn and (texts or tools):
            turns.append(
                Turn(
                    blocks=len(texts),
                    intermediate_chars=sum(len(t) for t in texts[:-1]),
                    final_chars=len(texts[-1]) if texts else 0,
                    tool_calls=tools,
                )
            )
        texts, tools, open_turn = [], 0, False

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []

    for line in raw.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(entry, dict):
            continue
        if _is_operator_turn(entry):
            close()
            open_turn = True
            continue
        if not open_turn:
            continue
        text, calls = _assistant_parts(entry)
        if text:
            texts.append(text)
        tools += calls
    close()
    return turns


def settled(paths: Iterable[Path], now: float | None = None) -> list[Path]:
    """Drop transcripts still being written. See the module docstring."""
    stamp = time.time() if now is None else now
    out: list[Path] = []
    for p in paths:
        try:
            if stamp - p.stat().st_mtime >= ACTIVE_WINDOW_S:
                out.append(p)
        except OSError:
            continue
    return out


def measure(
    paths: Iterable[Path],
    min_tool_calls: int = MIN_TOOL_CALLS,
    now: float | None = None,
) -> Measurement:
    """`now` exists so a test can include files it just wrote.

    The filter is applied here rather than left to the caller because a caller who
    forgets it measures the session doing the measuring, and the result drifts
    without ever looking wrong.
    """
    seen = 0
    work: list[Turn] = []
    for p in settled(paths, now):
        seen += 1
        work.extend(t for t in parse_transcript(p) if t.tool_calls >= min_tool_calls)

    intermediate = sum(t.intermediate_chars for t in work)
    final = sum(t.final_chars for t in work)
    total = intermediate + final
    return Measurement(
        transcripts=seen,
        turns=len(work),
        ratio=(intermediate / total) if total else 0.0,
        p90_blocks=_p90([max(0, t.blocks - 1) for t in work]),
    )


def run(
    paths: Iterable[Path],
    ratio_cap: float = RATIO_CAP,
    p90_cap: int = P90_CAP,
    now: float | None = None,
) -> Findings:
    findings = Findings()
    m = measure(paths, now=now)

    if m.turns == 0:
        findings.crit.append("unrunnable: no transcripts found to measure")
        return findings

    if m.ratio > ratio_cap:
        findings.crit.append(
            f"intermediate prose ratio {m.ratio:.3f} exceeds {ratio_cap:.2f} "
            f"({m.turns} work turns across {m.transcripts} transcripts)"
        )
    if m.p90_blocks > p90_cap:
        findings.crit.append(
            f"p90 intermediate blocks {m.p90_blocks} exceeds {p90_cap}"
        )
    return findings

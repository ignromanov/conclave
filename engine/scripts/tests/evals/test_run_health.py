"""test_run_health.py — a starved run must not report success.

Root cause (rehearsal-n2e, 2026-07-27): the run completed all 48 trials and exited 0, but only
13 were usable. Every trial in rep 1 died on the same envelope —

    {"type":"result","subtype":"success","is_error":true,
     "terminal_reason":"api_error","api_error_status":429,
     "result":"You've hit your session limit · resets 5:40am (America/Asuncion)"}

— the account's session budget, not a per-request 429. `run_trial` classified each one correctly
(`ok=False`, because the CLI exits non-zero), and `rate_limited_transcript` already recognises the
signature. The hole was one level up: `_run` never consulted either. It had no streak detection
(`_pilot` has had one since the 2026-07-13 pilot death) and no floor on how much of the design it
must actually cover before calling itself a run.

Two guarantees are tested here:

  1. a run whose usable-cell coverage falls below the PRE-REGISTERED floor exits non-zero, and says
     how much it lost; and
  2. a session limit suspends the run and retries the same cell rather than burning the remaining
     cells at four seconds apiece — with a bounded wait budget, so it cannot hang forever.

Coverage is measured over DESIGN CELLS — distinct (trap, arm, rep) with a usable trial — not over
attempts. A retried cell must not inflate its own denominator.
"""
from __future__ import annotations

import json
import sys as _sys

from engine.cmd import eval as evalcmd
from engine.cmd.eval import _run
from tests.evals.test_run_containment import _args, _preregistered_data_root

# A 429 in the shape the CLI actually emitted: `subtype: success` and `is_error: true` together.
# Written as a literal rather than a fixture so a future CLI change to this envelope shows up here
# as a failing test rather than as another silently starved run.
SESSION_LIMIT_ROW = {
    "type": "result",
    "subtype": "success",
    "is_error": True,
    "terminal_reason": "api_error",
    "api_error_status": 429,
    "result": "You've hit your session limit · resets 5:40am (America/Asuncion)",
}

# Fails `n` times with the session-limit envelope (exit 1, so `_completed_normally` sees a harness
# failure), then succeeds forever.
FLAKY_STUB = """
import json, pathlib, sys
counter = pathlib.Path({counter!r})
n = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(n + 1))
if n < {fail_first}:
    print(json.dumps({limit_row!r}))
    sys.exit(1)
print(json.dumps({{"type": "result", "subtype": "success"}}))
"""

ALWAYS_LIMITED_STUB = """
import json, pathlib, sys
counter = pathlib.Path({counter!r})
n = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(n + 1))
print(json.dumps({limit_row!r}))
sys.exit(1)
"""


def _stub(tmp_path, monkeypatch, template, **fmt):
    stub = tmp_path / "stub.py"
    stub.write_text(
        template.format(counter=str(tmp_path / "counter.txt"), limit_row=SESSION_LIMIT_ROW, **fmt),
        encoding="utf-8",
    )
    monkeypatch.setenv("CONCLAVE_EVAL_AGENT_CMD", f"{_sys.executable} {stub}")
    return stub


def _rows(data_root, run_id="run-test"):
    path = data_root / "eval" / "runs" / run_id / "trials.jsonl"
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def test_run_fails_when_coverage_falls_below_the_pre_registered_floor(
    tmp_path, monkeypatch, eval_store, capsys
):
    """rehearsal-n2e's exact shape, in miniature: every trial a harness failure, exit 0 before.

    The wait budget is set to zero so the run does not pause; what is under test is the verdict it
    reports, not how long it is willing to wait."""
    data_root = _preregistered_data_root(tmp_path, eval_store)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(data_root))
    monkeypatch.setattr(evalcmd, "MAX_RATE_LIMIT_WAITS", 0)
    _stub(tmp_path, monkeypatch, ALWAYS_LIMITED_STUB)

    rc = _run(_args())
    err = capsys.readouterr().err

    assert rc != 0, "a run with no usable trials must not exit 0"
    assert "NOT A RUN" in err, err
    assert "coverage" in err


def test_run_exits_zero_when_coverage_clears_the_floor(tmp_path, monkeypatch, eval_store, capsys):
    """The floor must not fire on a healthy run — the guard is worthless if it also blocks the
    thing it is guarding."""
    data_root = _preregistered_data_root(tmp_path, eval_store)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(data_root))
    _stub(tmp_path, monkeypatch, FLAKY_STUB, fail_first=0)

    rc = _run(_args())
    assert rc == 0, capsys.readouterr().err
    assert all(r["ok"] for r in _rows(data_root))


def test_run_waits_and_retries_the_same_cell_after_a_session_limit(
    tmp_path, monkeypatch, eval_store, capsys
):
    """A rate-limited trial means the run must suspend and re-attempt THAT cell — not march through
    the remaining cells recording garbage. There is no consecutive-failures threshold to cross
    first: in a scored run a cell walked past is unrecoverable, since `run` refuses to append to an
    existing trials.jsonl and so has no --resume to come back with."""
    data_root = _preregistered_data_root(tmp_path, eval_store)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(data_root))

    slept: list[float] = []
    monkeypatch.setattr(evalcmd.time, "sleep", lambda s: slept.append(s))
    # Two rate-limited attempts, both on the FIRST cell — under a consecutive-failures rule those
    # two cells would have been spent before the rule fired, and a spent cell is unrecoverable.
    _stub(tmp_path, monkeypatch, FLAKY_STUB, fail_first=2)

    rc = _run(_args())
    captured = capsys.readouterr()

    assert rc == 0, captured.err
    assert len(slept) == 2, "every rate-limited cell must be waited on, not walked past"
    assert "waiting" in captured.out.lower()

    rows = _rows(data_root)
    # 1 trap x 1 rep x 3 arms = 3 cells, plus the 2 failed attempts at the first of them. All three
    # cells end up covered: the retried one is not lost.
    assert sum(1 for r in rows if not r["ok"]) == 2
    assert {(r["trap_id"], r["arm"], r["rep"]) for r in rows if r["ok"]} == {
        ("t00", arm, 0) for arm in ("absent", "placebo", "full")
    }
    assert "coverage 3/3" in captured.out


# Fails `n` times with an ORDINARY harness failure — no rate-limit event, no 429. scored-002's
# actual killer: "API Error: Connection closed mid-response", arriving as subtype success with
# is_error true and api_error_status null.
FLAKY_CONNECTION_STUB = """
import json, pathlib, sys
counter = pathlib.Path({counter!r})
n = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(n + 1))
if n < {fail_first}:
    print(json.dumps({{"type": "result", "subtype": "success", "is_error": True,
                       "terminal_reason": "api_error", "api_error_status": None,
                       "result": "API Error: Connection closed mid-response."}}))
    sys.exit(1)
print(json.dumps({{"type": "result", "subtype": "success"}}))
"""


def test_run_reattempts_an_ordinary_harness_failure_without_sleeping(
    tmp_path, monkeypatch, eval_store, capsys
):
    """A dropped connection is transient and cell-local: nothing is being waited FOR, so the cell is
    re-attempted immediately. Under the pre-fix code this cell was either lost (no retry for
    non-limit failures) or, worse, misread as a dead budget and slept on for 900s — scored-002 spent
    an hour that way on a connection error."""
    data_root = _preregistered_data_root(tmp_path, eval_store)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(data_root))

    slept: list[float] = []
    monkeypatch.setattr(evalcmd.time, "sleep", lambda s: slept.append(s))
    _stub(tmp_path, monkeypatch, FLAKY_CONNECTION_STUB, fail_first=2)

    rc = _run(_args())
    captured = capsys.readouterr()

    assert rc == 0, captured.err
    assert slept == [], "an ordinary failure is not a rate limit and must not sleep"
    assert "re-attempting" in captured.out
    assert "coverage 3/3" in captured.out


def test_run_abandons_a_cell_that_keeps_failing_and_moves_on(
    tmp_path, monkeypatch, eval_store, capsys
):
    """The cap is what stops one impossible cell from stalling the whole run. Once it is spent the
    cell is recorded failed, the run advances, and the coverage floor decides the verdict — which
    here it fails, since nothing ever succeeds."""
    data_root = _preregistered_data_root(tmp_path, eval_store)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(data_root))

    slept: list[float] = []
    monkeypatch.setattr(evalcmd.time, "sleep", lambda s: slept.append(s))
    _stub(tmp_path, monkeypatch, FLAKY_CONNECTION_STUB, fail_first=999)

    rc = _run(_args())
    captured = capsys.readouterr()

    assert rc != 0
    assert slept == []
    # 3 cells x MAX_CELL_ATTEMPTS — every cell tried its full allowance, and the run still ended.
    assert len(_rows(data_root)) == 3 * evalcmd.MAX_CELL_ATTEMPTS
    assert "NOT A RUN" in captured.err


def test_run_gives_up_once_the_wait_budget_is_exhausted(
    tmp_path, monkeypatch, eval_store, capsys
):
    """Waiting is bounded. A budget that never comes back must end the run with a verdict, not
    with an indefinitely sleeping process."""
    data_root = _preregistered_data_root(tmp_path, eval_store)
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(data_root))

    slept: list[float] = []
    monkeypatch.setattr(evalcmd.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(evalcmd, "MAX_RATE_LIMIT_WAITS", 2)
    _stub(tmp_path, monkeypatch, ALWAYS_LIMITED_STUB)

    rc = _run(_args())
    err = capsys.readouterr().err

    assert rc != 0
    assert len(slept) == 2, "the wait budget must bound the number of pauses, not just their length"
    assert "session budget" in err
    assert "NOT A RUN" in err, "an abort must still report what the run covered"

"""engine/cmd/test.py — adapter for `engine test <verb>`.

  live   seed a throwaway instance with the real scaffolder and run the `live_instance` tests
         against it, failing on any skip

Owns the process contract for `enginelib.live_lane`'s pure plan: the temp directory, the two
child processes, and the exit code. The workflow's live-instance job calls this verb rather
than restating the steps, so the lane a developer can run before pushing is the same lane CI
runs after (feedback 1787103625/i1).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from enginelib.live_lane import Step, child_env, data_root_for, plan_pytest, plan_seed, verdict

_STDERR_TAIL_CHARS = 2000

# engine/scripts/engine/cmd/test.py → parents: [cmd, engine, scripts, engine/, <checkout>]
_ENGINE_DIR = Path(__file__).resolve().parents[3]
_CHECKOUT = Path(__file__).resolve().parents[4]


def _run(step: Step, *, cwd: Path) -> tuple[int, str]:
    """Run one step to completion. Returns (exit code, stdout+stderr).

    Captured, not passed through: `verdict` tells a skip from a pass by reading the lane's own
    output, and only a captured one can be read. `stdin=DEVNULL` because the scaffolder prompts
    when it has a terminal — the workflow passed `< /dev/null` for the same reason.
    """
    proc = subprocess.run(
        step.argv,
        cwd=str(cwd),
        env=child_env(step),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    return proc.returncode, f"{proc.stdout or ''}{proc.stderr or ''}"


def _live(args) -> int:
    python = sys.executable
    keep = bool(args.keep)
    seed_dir = Path(tempfile.mkdtemp(prefix="conclave-live-lane-"))

    try:
        seed = plan_seed(python=python, engine_dir=_ENGINE_DIR, seed_dir=seed_dir)
        code, out = _run(seed, cwd=_CHECKOUT)
        if code != 0:
            print(f"engine test live: scaffolder exited {code}", file=sys.stderr)
            print(out[-_STDERR_TAIL_CHARS:], file=sys.stderr)
            return 1

        instance_root = data_root_for(seed_dir)
        # The assertion CI spells out as a separate step, for the same measured reason: the
        # marked tests SKIP when the root is unset and pytest exits 0 on an all-skipped run,
        # so a seed that quietly produced nothing would report green on tests that never ran.
        if not instance_root.is_dir():
            print(
                f"engine test live: the scaffolder produced no DATA root at {instance_root}",
                file=sys.stderr,
            )
            return 1

        extra = ["-k", args.k] if args.k else []
        lane = plan_pytest(python=python, instance_root=instance_root, extra_args=extra)
        print(f"engine test live: instance at {instance_root}", file=sys.stderr)
        code, out = _run(lane, cwd=_CHECKOUT)
        print(out, end="")

        result = verdict(code, out)
        print(f"engine test live: {result.reason}", file=sys.stderr)
        if keep:
            print(f"engine test live: kept {seed_dir}", file=sys.stderr)
        return 0 if result.ok else 1
    finally:
        if not keep:
            shutil.rmtree(seed_dir, ignore_errors=True)


def register(sub) -> None:
    p = sub.add_parser("test", help="Run test lanes the default suite cannot run itself.")
    vsub = p.add_subparsers(dest="test_verb", required=True)

    live = vsub.add_parser(
        "live",
        help="Seed a throwaway instance and run the live_instance tests against it.",
    )
    live.add_argument(
        "--keep",
        action="store_true",
        help="Leave the seeded instance on disk and print its path.",
    )
    live.add_argument("-k", default=None, help="Pass an expression through to pytest's -k.")
    live.set_defaults(func=_live, _runlog_verb="live")

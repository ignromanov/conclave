"""engine — git-style CLI dispatcher. `python -m engine <noun> <verb> [args]`.
Adapters live in engine/cmd/<noun>.py and own the process contract (Q5)."""
import argparse
import os
import sys
import time
from pathlib import Path


def _deps_present() -> bool:
    import importlib.util

    if os.environ.get("CONCLAVE_ENGINE_FORCE_REEXEC") == "1":
        return False  # test/ops seam; inert unless set
    return all(
        importlib.util.find_spec(m) is not None
        for m in ("yaml", "frontmatter", "pydantic", "ruamel.yaml")
    )


def _bootstrap_interpreter(args: list[str]) -> None:
    """Re-exec into ${CLAUDE_PLUGIN_DATA}/venv's python when this interpreter lacks deps
    (099 followups B4). Must run before any third-party import; the dep-free `_build_parser()`
    / lazy per-noun imports (`__main__.py` grounding) guarantee that's still true here.

    No-op on dev/dogfood runs: deps already present, or CLAUDE_PLUGIN_DATA unset.
    """
    from enginelib.provision import plan_reexec

    scripts_dir = Path(__file__).resolve().parents[1]  # engine/scripts (THIS invocation's source)
    data = os.environ.get("CLAUDE_PLUGIN_DATA")
    venv_python = None
    if data:
        cand = Path(data) / "venv" / "bin" / "python"
        venv_python = cand if cand.exists() else None
    plan = plan_reexec(
        venv_python=venv_python,
        scripts_dir=scripts_dir,
        current_executable=sys.executable,
        args=args,
        deps_present=_deps_present(),
        bootstrapped=os.environ.get("CONCLAVE_ENGINE_BOOTSTRAPPED") == "1",
        existing_pythonpath=os.environ.get("PYTHONPATH", ""),
    )
    if plan is not None:
        os.execve(plan.python, [plan.python, *plan.argv], {**os.environ, **plan.env})


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="engine")
    sub = p.add_subparsers(dest="noun", required=True)
    # Each cmd module exposes register(subparsers) adding its noun + verbs.
    from engine.cmd import post_commit  # noqa: F401 — extended per wave
    post_commit.register(sub)
    from engine.cmd import audit
    audit.register(sub)
    from engine.cmd import lifecycle
    lifecycle.register(sub)
    from engine.cmd import mention
    mention.register(sub)
    from engine.cmd import register
    register.register(sub)
    from engine.cmd import advisor
    advisor.register(sub)
    from engine.cmd import file
    file.register(sub)
    from engine.cmd import session
    session.register(sub)
    from engine.cmd import memory
    memory.register(sub)
    from engine.cmd import briefing
    briefing.register(sub)
    from engine.cmd import skill
    skill.register(sub)
    from engine.cmd import model
    model.register(sub)
    from engine.cmd import find
    find.register(sub)
    from engine.cmd import overlay
    overlay.register(sub)
    from engine.cmd import spec
    spec.register(sub)
    from engine.cmd import frontmatter
    frontmatter.register(sub)
    from engine.cmd import inbox
    inbox.register(sub)
    from engine.cmd import doctor
    doctor.register(sub)
    return p


def main(argv: list[str] | None = None) -> int:
    _bootstrap_interpreter(sys.argv[1:] if argv is None else argv)
    parser = _build_parser()
    # Usage errors (unknown noun/verb/flag) → argparse SystemExit(2) by design: POSIX usage-error
    # convention, intentional (B4-decided 2026-07-01) — NOT bash's blanket exit 1.
    args = parser.parse_args(argv)
    start = time.monotonic()
    exit_code = 0
    try:
        exit_code = args.func(args)          # adapter returns int
    except Exception as exc:                 # replicate `set -e`: any failure → exit 1
        print(f"engine {getattr(args, 'noun', '?')}: {exc}", file=sys.stderr)
        exit_code = 1
    finally:
        # replicate `trap … run_log_append EXIT` (NOT atexit — skips on signals)
        try:
            from enginelib import runlog
            dur_ms = int((time.monotonic() - start) * 1000)
            verb = getattr(args, "_runlog_verb", "")
            script = f"engine {getattr(args, 'noun', '?')} {verb}".strip()
            runlog.run_log_append(
                script=script,
                args_hash=getattr(args, "_runlog_args", ""),
                exit_code=exit_code,
                duration_ms=dur_ms,
                advisor=getattr(args, "_runlog_advisor", "shared"),
            )
        except Exception:
            pass                              # observability must never mask the real exit
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

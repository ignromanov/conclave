"""__main__.py — entrypoint for `python3 -m briefing <advisor>`.

Orchestrates the 7 section scans + render + hot-append, emitting
machine-parseable progress lines that match the legacy bash output:

    [briefing-build] step=<name> took=<n>ms
    ...
    [briefing-build] wrote=<path>

Step names (in order): who-i-am, project-state, decisions, my-queue, p0,
sessions, mentions, render, hot.
"""
from __future__ import annotations

import argparse
import sys
import time

# Engine lifecycle/forge skills are CODE, not advisors — exclude them when deriving
# the advisor set from the DATA-root skills registry.
_LIFECYCLE_SKILLS = {
    "start", "processing", "done", "handoff",
    "forge", "hire", "retro", "feedback", "feedback-triage",
}

# Advisor SKILL-dir prefixes tolerated during the #48 migration (conclave- canonical).
_ADVISOR_PREFIXES = ("conclave-", "team.")


def _registry_advisors() -> set[str]:
    """Advisor ids from the on-disk registry (DATA-root .claude/skills/), tolerating
    both the canonical conclave-<id> and legacy team.<id> layouts, minus lifecycle
    skills. Empty when absent → callers degrade to permissive (no enforcement), not
    reject-all. Generalizes the former hardcoded 5-advisor set."""
    from briefing import paths  # lightweight (os/pathlib) — keeps --help startup fast
    try:
        root = paths.repo_root()
    except RuntimeError:
        return set()  # unresolvable root → empty registry → permissive
    skills_dir = root / ".claude" / "skills"
    advisors: set[str] = set()
    if skills_dir.is_dir():
        for child in skills_dir.iterdir():
            if not child.is_dir():
                continue
            for prefix in _ADVISOR_PREFIXES:
                if child.name.startswith(prefix):
                    stem = child.name[len(prefix):]
                    if stem not in _LIFECYCLE_SKILLS:
                        advisors.add(stem)
                    break
    return advisors


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


def _emit_step(name: str, start_ms: int) -> None:
    elapsed = _now_ms() - start_ms
    print(f"[briefing-build] step={name} took={elapsed}ms", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="briefing",
        description="Generate a briefing for an advisor.",
    )
    parser.add_argument("advisor", help="Canonical advisor name (e.g. nexus-ceo)")
    args = parser.parse_args(argv)

    registry = _registry_advisors()
    if registry and args.advisor not in registry:
        known = ", ".join(sorted(registry))
        print(
            f"briefing: advisor '{args.advisor}' is not in the instance registry.\n"
            f"Known advisors: {known}",
            file=sys.stderr,
        )
        return 1

    advisor: str = args.advisor

    # Import here so startup is fast for --help / bad advisor names.
    from briefing import paths, render
    from briefing.render import _generated_at  # noqa: PLC2701
    from enginelib.paths import advisor_skill_dir  # #48 prefix-tolerant SKILL dir
    from briefing.scans import (
        ScanCtx,
        closeability,
        code_repo,
        current_work,
        decisions,
        drift,
        identity,
        interrupted,
        mentions,
        owed,
        p0,
        project_digest,
        project_state,
        queue,
        roadmap,
        sessions,
        spec_progress,
    )

    root = paths.repo_root()
    ctx = ScanCtx(
        advisor=advisor,
        short_name=advisor.split("-")[0],
        repo_root=root,
        decisions_dir=paths.decisions_dir(),
        sessions_dir=paths.sessions_dir(),
        mentions_dir=paths.mentions_dir(),
        gh_cache_dir=paths.gh_cache_dir(),
        personality_path=(
            advisor_skill_dir(advisor, root / ".claude" / "skills")
            / "memory" / "personality.md"
        ),
        progress_path=root / "progress-summary.md",
    )

    # Run scans individually so each step can be timed.
    t0 = _now_ms()
    who_i_am = identity.build(ctx)
    _emit_step("who-i-am", t0)

    t0 = _now_ms()
    proj_state = project_state.build(ctx)
    _emit_step("project-state", t0)

    t0 = _now_ms()
    recent_decisions = decisions.build(ctx)
    _emit_step("decisions", t0)

    t0 = _now_ms()
    my_queue = queue.build(ctx)
    _emit_step("my-queue", t0)

    t0 = _now_ms()
    p0_blockers = p0.build(ctx)
    _emit_step("p0", t0)

    t0 = _now_ms()
    last_sessions = sessions.build(ctx)
    _emit_step("sessions", t0)

    t0 = _now_ms()
    mention_body = mentions.build(ctx)
    _emit_step("mentions", t0)

    t0 = _now_ms()
    current_work_body = current_work.build(ctx)
    _emit_step("current-work", t0)

    t0 = _now_ms()
    spec_progress_body = spec_progress.build(ctx)
    _emit_step("spec-progress", t0)

    t0 = _now_ms()
    owed_body = owed.build(ctx)
    _emit_step("owed", t0)

    t0 = _now_ms()
    roadmap_body = roadmap.build(ctx)
    _emit_step("roadmap", t0)

    t0 = _now_ms()
    drift_body = drift.build(ctx)
    _emit_step("drift", t0)

    t0 = _now_ms()
    interrupted_body = interrupted.build(ctx)
    _emit_step("interrupted", t0)

    t0 = _now_ms()
    project_digest_body = project_digest.build(ctx)
    _emit_step("project-digest", t0)

    t0 = _now_ms()
    closeability_body = closeability.build(ctx)
    _emit_step("closeability", t0)

    t0 = _now_ms()
    code_repo_body = code_repo.build(ctx)
    _emit_step("code-repo", t0)

    values: dict[str, str] = {
        "advisor": advisor,
        "generated_at": _generated_at(),
        "who_i_am": who_i_am,
        "project_state": proj_state,
        "recent_decisions": recent_decisions,
        "my_queue": my_queue,
        "p0_blockers": p0_blockers,
        "last_sessions": last_sessions,
        "mentions": mention_body,
        "current_work": current_work_body,
        "spec_progress": spec_progress_body,
        "owed": owed_body,
        "roadmap": roadmap_body,
        "drift": drift_body,
        "interrupted": interrupted_body,
        "project_digest": project_digest_body,
        "closeability": closeability_body,
        "code_repo": code_repo_body,
    }

    out_path = paths.briefings_dir() / f"{advisor}.md"

    t0 = _now_ms()
    render.write_body(values, out_path)
    _emit_step("render", t0)

    # hot.md reference footer (AC8 — content not embedded, path reference only).
    render.append_hot(out_path)

    print(f"[briefing-build] wrote={out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

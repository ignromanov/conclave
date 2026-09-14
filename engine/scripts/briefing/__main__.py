"""__main__.py — entrypoint for `python3 -m briefing <advisor>`.

Orchestrates the 7 section scans + render (body + hot.md footer), emitting
machine-parseable progress lines that match the legacy bash output:

    [briefing-build] step=<name> took=<n>ms
    ...
    [briefing-build] wrote=<path>       # content differed from what was on disk
    [briefing-build] unchanged=<path>   # build-and-compare found no real change (#14)

Step names (in order): who-i-am, project-state, decisions, my-queue, p0,
sessions, mentions, render.
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

    # META roles ship with the engine and are never hired, so they never appear in the
    # DATA-root domain roster _registry_advisors() enumerates. Admission asks "may this
    # advisor hold a briefing", which is roster + META — gating on the enumeration alone
    # rejected forge, the one advisor guaranteed to exist in every instance (#38).
    # Same enumerate-vs-gate split as enginelib.advisors.lifecycle_advisors(); routed
    # through the same with_meta() seam rather than re-open-coding the union.
    from enginelib.advisors import with_meta

    registry = _registry_advisors()
    if registry and args.advisor not in with_meta(registry):
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
    from briefing.scans import ScanCtx
    from briefing.sections import SECTIONS

    # Persona resolution lives in enginelib.advisors, which owns META_ADVISORS and
    # so can tell a hired advisor's instance-written persona from Forge's shipped
    # one. briefing.paths is a lightweight DATA-only module and knows neither.
    from enginelib.advisors import personality_path as advisor_personality_path

    root = paths.repo_root()
    ctx = ScanCtx(
        advisor=advisor,
        short_name=advisor.split("-")[0],
        repo_root=root,
        decisions_dir=paths.decisions_dir(),
        sessions_dir=paths.sessions_dir(),
        mentions_dir=paths.mentions_dir(),
        gh_cache_dir=paths.gh_cache_dir(),
        # #77 fixed the anchor: the persona is PROJECT data (.claude/skills/), not
        # DATA-root data — in plugin mode `.conclave` is a sibling of `.claude`, so
        # `root/".claude"` named a directory that never exists. That left a second
        # gap it did not cover: Forge's persona is not project data at all, it ships
        # in CODE under the SKILL's name, so the project anchor is empty for it by
        # construction. The resolver handles both kinds.
        personality_path=advisor_personality_path(advisor),
        project_root=paths.project_root(),
        plans_dir=paths.project_plans_dir(),
    )

    # One list, two readers (plan 057 T5b): this path times each scan, render.build does
    # not, and that was the whole of the difference between the two dispatch literals.
    values: dict[str, str] = {
        "advisor": ctx.audience,
        "generated_at": _generated_at(),
    }
    for section in SECTIONS:
        t0 = _now_ms()
        values[section.key] = section.scan.build(ctx)
        _emit_step(section.step, t0)

    out_path = paths.briefings_dir() / f"{advisor}.md"

    # Build-and-compare (#14): render the full final content (body + hot.md footer)
    # and write only if it actually differs from what is on disk — the comparison
    # ignores the generated_at stamp so an unchanged rebuild is a true no-op.
    t0 = _now_ms()
    content = render.render_content(values)
    written = render.write_if_changed(content, out_path)
    _emit_step("render", t0)

    if written:
        print(f"[briefing-build] wrote={out_path}", flush=True)
    else:
        print(f"[briefing-build] unchanged={out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

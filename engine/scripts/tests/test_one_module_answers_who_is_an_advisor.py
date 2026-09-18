"""Who is an advisor, and where does an advisor's skill dir live (#69).

#69 reports six advisor-discovery functions across four modules disagreeing. Executed
together on the authoring instance the day this gate was written, the six gave **three
distinct answers** — and two of the three differences turned out to be designed:
`known_advisors` excludes the META advisor deliberately, `lifecycle_advisors` adds it
back, which is the enumerate-vs-gate split. The third was `iris`, a router skill with
no agent-def, which `engine audit registry-consistency` already reports CRIT.

So the harm is not that six functions give six answers today. It is that nothing stops
the seventh copy, and the copied thing underneath them is not the function at all —
it is a MIGRATION RULE:

    ("conclave-", "team.")

the current skill-dir prefix and the legacy one, which every reader must tolerate
until the migration ends. Deriving that set rather than listing it found **six
definitions in six modules**, one of them under a different name, and three functions
#69 never named. The day the legacy prefix is finally dropped, one of those six gets
updated and five keep accepting it — which is the same shape as the bug #69 cites,
where a direct `team.`-only scan went blind the moment advisors migrated.

Both gates below are DERIVED. A hand-kept inventory of the places that hold a copy is
the same defect one layer up, and this project has shipped that green before.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]

#: The home of the layout rule — `iter_advisor_skills` and `advisor_skill_dir` live
#: beside it, and they are what a reader should be calling instead of re-deriving it.
PREFIX_HOME = "enginelib/paths.py"

#: The home of the question "who is an advisor".
ADVISOR_HOME = "enginelib/advisors.py"

_ANSWERS_THE_QUESTION = re.compile(r"^_?[a-z_]*advisors$")

#: Second copies that stay, each with the reason. A row here is a debt with a name and
#: a price, not an exemption — which is the whole difference between this and six
#: modules that simply accumulated one each.
DECLARED_PREFIX_COPIES: dict[str, str] = {
    "briefing/__main__.py": (
        "briefing keeps its startup path on os/pathlib only. Importing "
        "enginelib.paths to reach the shared constant costs ~9ms more than "
        "briefing.paths — measured, almost all of it glob+re — on a module whose "
        "`--help` latency its author priced deliberately. Collapsing it is a "
        "decision with an owner, not a cleanup."
    ),
}

DECLARED_DISCOVERY_ELSEWHERE: dict[str, str] = {
    "briefing/__main__.py::_registry_advisors": "same startup-cost reason as above",
    "briefing/regen.py::regen_advisors": (
        "a verb, not a query: it regenerates a GIVEN list. Matched by name only."
    ),
    "briefing/team_digest.py::_default_advisors": (
        "a thin wrapper that delegates to enginelib.advisors.known_advisors — one "
        "call site's default, not a second source."
    ),
    "enginelib/register.py::discover_advisors": (
        "delegates to enginelib.advisors.registry_advisors and only re-shapes the "
        "result — sorted list, because its one caller prints it in order. A call-site "
        "adapter, not a third source; it had its own prefix tuple and its own "
        "exclusion set until #69."
    ),
}

#: Modules holding their own copy of the lifecycle-skill exclusion set. Executed side
#: by side on 2026-09-15 all four copies were IDENTICAL — they bought nothing and each
#: was a place the next lifecycle verb could fail to be added.
DECLARED_LIFECYCLE_COPIES: dict[str, str] = dict(DECLARED_PREFIX_COPIES)


def _py_files() -> list[tuple[str, ast.Module]]:
    out = []
    for path in sorted(SCRIPTS.rglob("*.py")):
        rel = path.relative_to(SCRIPTS).as_posix()
        if rel.startswith(("tests/", "evals/")) or "/tests/" in rel:
            continue
        try:
            out.append((rel, ast.parse(path.read_text(encoding="utf-8"))))
        except SyntaxError:
            # A file that does not parse is invisible to every scan below. That is
            # acceptable only because such a file fails the rest of the suite loudly
            # — but it is also a trap for anyone MUTATION-TESTING this gate: a probe
            # that writes invalid Python makes the file disappear and the gate go
            # green, which reads as "the assertion does not measure this" and is a
            # lie. A probe here must leave valid Python and assert that it did.
            continue
    return out


def _modules_defining_the_prefix_rule() -> dict[str, str]:
    """{relpath: assigned name} for every module that spells the prefix pair itself.

    Matched on the VALUE, not the name: the sixth copy was called `_AGENT_PREFIXES`
    and a name-keyed scan would have reported five.
    """
    found: dict[str, str] = {}
    for rel, tree in _py_files():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(
                    node.value, ast.Tuple | ast.List):
                continue
            items = [e.value for e in node.value.elts if isinstance(e, ast.Constant)]
            if "conclave-" in items and "team." in items:
                target = node.targets[0]
                found[rel] = target.id if isinstance(target, ast.Name) else "<expr>"
    return found


def _discovery_functions() -> dict[str, str]:
    found: dict[str, str] = {}
    for rel, tree in _py_files():
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and _ANSWERS_THE_QUESTION.match(node.name):
                found[f"{rel}::{node.name}"] = rel
    return found


def test_the_scan_can_see_both_homes():
    """Anti-vacuity, in both directions. A pattern that matched nothing would satisfy
    every assertion below."""
    prefixes = _modules_defining_the_prefix_rule()
    assert PREFIX_HOME in prefixes, (
        f"the prefix scan does not see {PREFIX_HOME} — it is measuring nothing: "
        f"{sorted(prefixes)}")
    advisors = _discovery_functions()
    assert ADVISOR_HOME in advisors.values(), (
        f"the discovery scan does not see {ADVISOR_HOME}: {sorted(advisors)}")


def test_the_advisor_skill_prefix_pair_is_spelled_in_one_module():
    strays = sorted(
        f"{rel} ({name})"
        for rel, name in _modules_defining_the_prefix_rule().items()
        if rel != PREFIX_HOME and rel not in DECLARED_PREFIX_COPIES
    )
    assert not strays, (
        f'these modules spell ("conclave-", "team.") themselves instead of importing '
        f"it from {PREFIX_HOME}: {', '.join(strays)}.\n"
        "It is a migration rule with an end date: when the legacy prefix is dropped, "
        "every copy that was missed keeps accepting it (#69)."
    )


def test_every_advisor_discovery_function_lives_in_one_module_or_is_declared():
    strays = sorted(
        name for name, rel in _discovery_functions().items()
        if rel != ADVISOR_HOME and name not in DECLARED_DISCOVERY_ELSEWHERE
    )
    assert not strays, (
        f"these answer 'who is an advisor' outside {ADVISOR_HOME}: "
        f"{', '.join(strays)}.\nCall the one in enginelib/advisors.py, or declare "
        "what the second copy buys. The last undeclared one was line-for-line "
        "identical to it (#69)."
    )


def test_no_two_discovery_functions_share_a_name_while_reading_different_things():
    """`canonical_advisors` existed twice — in `enginelib/advisors.py` over agent-defs
    plus skills, and in `gh_board_query` over the DATA-root skills dir only. A caller
    reading the import line cannot tell which question it just asked."""
    by_name: dict[str, list[str]] = {}
    for full, rel in _discovery_functions().items():
        by_name.setdefault(full.split("::")[1], []).append(rel)
    collisions = {n: sorted(v) for n, v in by_name.items() if len(set(v)) > 1}
    assert not collisions, f"one name, two sources: {collisions}"


def _modules_defining_the_lifecycle_set() -> dict[str, str]:
    """{relpath: assigned name} for every module that spells the exclusion set itself.

    Keyed on the VALUE like the prefix scan: the copies were called `_LIFECYCLE` and
    `_LIFECYCLE_SKILLS`, so a name-keyed scan would have missed one of the four.
    """
    probe = {"start", "processing", "done", "handoff", "forge",
             "hire", "retro", "feedback", "feedback-triage"}
    found: dict[str, str] = {}
    for rel, tree in _py_files():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            value = node.value
            if isinstance(value, ast.Call) and value.args:
                value = value.args[0]
            if not isinstance(value, ast.Set | ast.Tuple | ast.List):
                continue
            items = {e.value for e in value.elts if isinstance(e, ast.Constant)}
            if items == probe:
                target = node.targets[0]
                found[rel] = target.id if isinstance(target, ast.Name) else "<expr>"
    return found


def test_the_lifecycle_exclusion_set_is_spelled_in_one_module():
    spelled = _modules_defining_the_lifecycle_set()
    assert ADVISOR_HOME in spelled, (
        f"the scan does not see {ADVISOR_HOME} — measuring nothing: {sorted(spelled)}")
    strays = sorted(
        f"{rel} ({name})" for rel, name in spelled.items()
        if rel != ADVISOR_HOME and rel not in DECLARED_LIFECYCLE_COPIES
    )
    assert not strays, (
        "these modules spell the lifecycle-skill exclusion set themselves instead of "
        f"importing LIFECYCLE_SKILLS from {ADVISOR_HOME}: {', '.join(strays)}.\n"
        "All copies were identical when measured, so a copy buys nothing and costs a "
        "place the next lifecycle verb can fail to appear (#69)."
    )

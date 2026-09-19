"""`briefing build` admits exactly the advisors the lifecycle admits (#133 F1).

Two gates stand on the same path and read two different registries. Executed against
one synthetic instance holding all three shapes, they disagreed in BOTH directions and
printed two different "Known advisors" lists for the same instance:

    id            agent-def  skill dir   session_init   briefing build
    alpha-cto        yes        yes        accept         accept
    phantom-cto      no         yes        REFUSE         accept + writes
    orphan-cto       yes        no         accept         REFUSE

`phantom-cto` is the `iris` shape the issue was filed on: a router skill minted without
an agent-def, which every other gate rejects and this one accepts — and it is the
permissive side that produces a durable artifact.

`orphan-cto` is the direction nobody had looked at, and it is worse than a stale file.
`briefing/regen.py::regen_advisors` gates on `lifecycle_advisors` and then calls
`briefing.__main__.main`, so the two registries sit in series on one code path: an
advisor with an agent-def and no router is enumerated by the caller, refused by the
callee, and `session_init` reports `briefing-build: FAILED exit=1 — continuing` on
every single start. The advisor exists as far as the lifecycle is concerned and their
briefing can never be built.

The fix is not "add a gate" — there IS a gate, and it refuses an unknown id outright.
It is "make the two gates ask one question". The question a briefing gate asks is
`lifecycle_advisors`: may this advisor hold a session, roster plus the shipped META
roles. Anything derived from SKILL dirs answers a different one.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]

#: The three shapes, and what each one has on disk.
BOTH = "alpha-cto"          # agent-def + router
SKILL_ONLY = "phantom-cto"  # router, no agent-def — the `iris` shape
DEF_ONLY = "orphan-cto"     # agent-def, no router


def _build(advisor: str, project: Path, data: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "briefing", advisor],
        capture_output=True, text=True, cwd=str(SCRIPTS),
        env={**os.environ,
             "CONCLAVE_AI_ROOT": str(data),
             "CLAUDE_PROJECT_DIR": str(project)},
    )


def _artifact(data: Path, advisor: str) -> Path:
    return data / "agent-memory" / "advisors" / "briefings" / f"{advisor}.md"


@pytest.fixture
def instance(tmp_path):
    """A DATA root beside its project, holding one advisor of each shape.

    Built by hand rather than through the `ai_root` fixture on purpose: that fixture
    seeds a router AND an agent-def for every name in lockstep, so no advisor in it can
    be one-sided and the disagreement this file exists to measure cannot occur there. A
    fixture that keeps two registries equal by construction is exactly the instrument
    that cannot see them disagree.
    """
    project = tmp_path / "proj"
    data = project / ".conclave"
    agents = project / ".claude" / "agents"
    agents.mkdir(parents=True)
    (data / "agent-memory" / "advisors" / "briefings").mkdir(parents=True)
    for advisor in (BOTH, SKILL_ONLY):
        skill = data / ".claude" / "skills" / f"conclave-{advisor}"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: router\n---\nstub\n", encoding="utf-8")
    for advisor in (BOTH, DEF_ONLY):
        (agents / f"{advisor}.md").write_text(
            f"---\nname: {advisor}\n---\nstub\n", encoding="utf-8")
    return project, data


def test_a_fully_provisioned_advisor_still_builds(instance):
    """Anti-vacuity. Every refusal assertion below is satisfied by a gate that refuses
    everything, and so is a build that crashes for an unrelated reason."""
    project, data = instance
    r = _build(BOTH, project, data)
    assert r.returncode == 0, (r.returncode, r.stdout[-2000:], r.stderr[-2000:])
    assert _artifact(data, BOTH).is_file(), "the control advisor got no briefing"


def test_a_router_without_an_agent_def_is_refused_and_writes_nothing(instance):
    """The `iris` shape. `session_init --advisor phantom-cto` exits 1 on this instance;
    this gate exited 0 and left a briefing on disk for an advisor that cannot hold a
    session — the permissive registry being the one with a writer attached."""
    project, data = instance
    r = _build(SKILL_ONLY, project, data)
    assert r.returncode == 1, (r.returncode, r.stdout[-2000:], r.stderr[-2000:])
    assert not _artifact(data, SKILL_ONLY).exists(), (
        "refused and wrote the artifact anyway — the exit code is not the thing that "
        "makes a phantom id durable (#133 F1)"
    )


def test_an_advisor_without_a_router_is_admitted(instance):
    """The other direction, in series on one path: `regen_advisors` enumerates this
    advisor from `lifecycle_advisors` and then hands it to the gate that refuses it, so
    the briefing silently never refreshes and every start reports a failed substep."""
    project, data = instance
    r = _build(DEF_ONLY, project, data)
    assert r.returncode == 0, (
        f"refused an advisor the lifecycle admits: {r.stderr[-2000:]}")
    assert _artifact(data, DEF_ONLY).is_file()


def test_an_id_in_neither_registry_is_still_refused(instance):
    """The gate must not be widened into a no-op by the repair."""
    project, data = instance
    r = _build("ghost-xyz", project, data)
    assert r.returncode == 1, (r.returncode, r.stdout[-2000:], r.stderr[-2000:])
    assert not _artifact(data, "ghost-xyz").exists()


def test_the_meta_advisor_is_admitted_without_being_hired(instance):
    """forge-chro ships with the engine and is in no instance's hired roster, so a gate
    built on the enumeration rejects the one advisor guaranteed to exist (#38). That is
    what `with_meta` is for, and it has to survive the change of source."""
    project, data = instance
    from enginelib.advisors import META_ADVISORS
    meta = sorted(META_ADVISORS)[0]
    r = _build(meta, project, data)
    assert r.returncode == 0, (r.returncode, r.stderr[-2000:])


def test_an_instance_with_no_roster_at_all_stays_permissive(tmp_path):
    """The documented degrade, unchanged: an unresolvable or empty roster means NO
    enforcement, not reject-all. Hermetic fixtures across this suite rely on it, and a
    gate that refuses everything when it cannot read the instance is a gate that breaks
    a fresh checkout instead of a phantom id."""
    project = tmp_path / "proj"
    data = project / ".conclave"
    (data / "agent-memory" / "advisors" / "briefings").mkdir(parents=True)
    (project / ".claude" / "agents").mkdir(parents=True)
    r = _build("nobody-cto", project, data)
    assert r.returncode == 0, (
        f"an empty roster rejected an id instead of degrading to permissive: "
        f"{r.stderr[-2000:]}")


# ---------------------------------------------------------------------------
# The two gates read one function
# ---------------------------------------------------------------------------
#
# The process-level tests above pin briefing's behaviour against a roster this file
# builds. They cannot see session_init drifting away from the same source afterwards,
# and running session_init end-to-end costs ~30s per admitted id because it admits
# first and fetches after. So the agreement itself is asserted on the source.

GATE_MODULES = {
    "briefing/__main__.py": "the briefing admission gate",
    "lifecycle/session_init.py": "the lifecycle admission gate",
}

#: The one function that answers "who may hold a session here". `with_meta` is the
#: roster|META seam both gates already route through; `known_advisors` is the roster.
ROSTER_SOURCE = "known_advisors"


def _tree(rel: str) -> ast.Module:
    return ast.parse((SCRIPTS / rel).read_text(encoding="utf-8"))


def _called_names(tree: ast.Module) -> set[str]:
    """Every plain function name called anywhere in the module.

    Call-keyed, not import-keyed: an import that nothing calls is exactly how a second
    source hides beside a first one.
    """
    return {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }


def _names_bound_to(tree: ast.Module, target: str) -> set[str]:
    """*target* plus every module-level name bound to it by a bare assignment.

    Keyed on what the name REACHES, not on how it is spelled. `session_init` keeps
    `_known_advisors = known_advisors` — its pre-#69 name, deliberately retained — so a
    scan that looked for the literal call `known_advisors(` reported the lifecycle gate
    itself as a second source. A gate that a legitimate alias can redden is a gate that
    gets weakened the first time it fires, which is the failure mode this project has
    already shipped once.
    """
    names = {target}
    changed = True
    while changed:                       # chains: a = known_advisors; b = a
        changed = False
        for node in tree.body:
            if not (isinstance(node, ast.Assign)
                    and isinstance(node.value, ast.Name)
                    and node.value.id in names):
                continue
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id not in names:
                    names.add(t.id)
                    changed = True
    return names


def test_the_alias_resolver_follows_a_chain():
    """The helper above is an instrument, and an instrument that resolves nothing would
    make every gate below pass on the literal spelling alone."""
    tree = ast.parse("from x import known_advisors\n_k = known_advisors\n_j = _k\n_z = other\n")
    assert _names_bound_to(tree, "known_advisors") == {"known_advisors", "_k", "_j"}


def test_the_call_scan_sees_something():
    """Anti-vacuity: an AST walk that matched no call reports perfect agreement."""
    for rel in GATE_MODULES:
        names = _called_names(_tree(rel))
        assert len(names) >= 5, f"the scan read nothing in {rel}: {sorted(names)}"


@pytest.mark.parametrize("rel", sorted(GATE_MODULES))
def test_both_admission_gates_call_the_same_roster_function(rel):
    tree = _tree(rel)
    names = _called_names(tree)
    assert names & _names_bound_to(tree, ROSTER_SOURCE), (
        f"{GATE_MODULES[rel]} ({rel}) does not call {ROSTER_SOURCE}(). Its roster comes "
        f"from somewhere else, which is how one instance came to print two different "
        f"'Known advisors' lists (#133 F1). Calls found: {sorted(names)}"
    )
    assert "with_meta" in names, (
        f"{rel} does not route through with_meta(): a gate built on the enumeration "
        "alone rejects the META advisor every instance ships (#38)"
    )

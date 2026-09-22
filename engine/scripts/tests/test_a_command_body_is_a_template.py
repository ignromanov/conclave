"""A command body is a template, and `$N` in it is a placeholder, not text (#313).

Two advisors reported the same corruption four days apart, from different locations, and
both quoted it verbatim from the `/conclave:start` body *as delivered into their session*:

    PR=$(awk -F'\t' -v b="$BRANCH" 'vera-cto==b{printf "%s%s", sep, $2; sep=","}' ...)

`commands/start.md` on disk is correct. The rewrite happens at delivery, which is why the
report is durable: anyone who greps the source finds right code and closes it as
not-reproducing.

WHAT THE MEASUREMENT CHANGED. The issue reads "`$1` is a slash-command positional
placeholder, and the first argument is the advisor slug". Half of that is wrong, and the
wrong half is load-bearing. Probed against the installed CLI (2.1.280) with a scratch
command whose whole body is a marker line:

    /probe ALPHA BETA GAMMA        ->  z=ALPHA  a=BETA  b=GAMMA  c=$3  d=$4
    /probe --advisor vera-cto      ->  z=--advisor  a=vera-cto  b=$2  c=$3
    /probe ALPHA                   ->  z=ALPHA  a=$1   b=$2

(`z` is `$0`, `a` is `$1`, ... ; the full probe transcript is in the PR.) So the expander is
**zero-indexed** — `$N` carries the *(N+1)*-th token, not the N-th — and an index with no
token is left standing rather than emptied. The second line is the field report reproduced
byte for byte: the router skill tells the advisor to enter `/conclave:start` "bound to
advisor <id> — pass `--advisor <id>`", the model passes both words, and `$1` collects the
slug from position two.

That matters here because the issue's latency claim rests on the other indexing: "the moment
`/conclave:start` is invoked with two arguments, [line 276] breaks the same way". Measured,
two arguments is exactly the case where `$2` is still safe. It breaks at **three**. A gate
calibrated to the issue's threshold would have been calibrated to the wrong number.

WHY THE FAILURE IS SILENT. awk does not reject the wreckage. `vera-cto==b` parses as
`(vera - cto) == b`: two uninitialised variables subtract to `0`, compared against a string,
false on every row. A destroyed field reference becomes a well-formed always-false predicate,
so the join renders `pr=none` for every branch — and `pr=none` is a *documented verdict* in
the table below the snippet, not an error. `unshipped=0, pr=merged` reads "fully shipped,
safe to delete"; `unshipped=0, pr=none` reads "stale, check the age". The audit exists to
make that join, and the join is what never runs. Line 276 fails the other way: `sub(...,
vera-cto)` is an awk syntax error, so the worktree list comes back empty and every branch
reports `bare`.

SCOPE, MEASURED IN BOTH DIRECTIONS. The issue scopes the fix to "command documents". The
same probe run against the other shipped surfaces says that is one short and one long:

  * a **skill body** is expanded. `.claude/skills/probe313sub/SKILL.md` invoked with
    `--advisor vera-cto` came back `z=--advisor a=vera-cto b=$2` — the identical off-by-one.
    So `SKILL.md` is inside the gate, and the advisor-router template with it, because every
    minted advisor skill is that template's output.
  * text **inlined by the `!`cat …`` blocks is not**. A contract file carrying the same
    marker arrived verbatim — `CONTRACT z=$0 a=$1 b=$2 A=$ARGUMENTS` — while the marker in
    the command body around it was expanded in the same delivery. The expander runs on the
    document, before the shell blocks run and their output is spliced in. That keeps the 17
    files under `skills/advisor-contracts/references/` out of the gate, and with them
    `skills/forge-operations/references/color-palette.md`, whose two `awk '{print $2}'`
    snippets are correct and would have had to be broken to satisfy a rule that does not
    reach them.

`find . -type d -name commands` returns exactly one directory, so there is no second command
tree to miss.

NO ALLOWLIST FOR PROSE. The first thing this gate caught was the comment written to explain
it. `commands/feedback.md` keeps an anti-pattern table whose rows *mention* the thing they
forbid, and #310's surface scan had to learn that distinction to stop flagging it — but it
does not transfer here, because the expander is not reading for meaning. A sentence that
mentions a bare positional is rewritten exactly like a program that uses one, so the
explanation in `commands/start.md` names the parenthesised form and describes the other in
words. An allowlist for "this one is only being discussed" would be a hole in the rule.

WHAT THIS GATE CANNOT TELL YOU: whether an *agent definition* under `agents/` is expanded.
Agents are dispatched through the Task tool rather than invoked by name with arguments, so
the probe above has no analogue to run; no `agents/*.md` carries a `$N` today, and the
absence is unverified rather than enforced.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]
COMMANDS_DIR = REPO / "commands"

#: Every placeholder form the delivered body can carry. Lifted from the pattern the
#: installed CLI ships (`test_the_pattern_is_the_one_the_cli_carries` holds it to that),
#: and confirmed against the probe transcript in this module's docstring.
PLACEHOLDER = re.compile(r"\$ARGUMENTS\[\d+\]|\$ARGUMENTS|\$\d+(?!\w)")

#: The subset a command author never means on purpose. `$ARGUMENTS` is excluded: a command
#: that wants the raw argument string writes it deliberately, and no command here does.
POSITIONAL = re.compile(r"\$\d+(?!\w)")

#: The shape that reproduces the field report — the router skill's own wording, passed on.
FIELD_ARGV = ["--advisor", "vera-cto"]


def deliver(text: str, argv: list[str]) -> str:
    """Expand a command body the way the CLI does. Measured behaviour, not documented.

    Zero-indexed (`$1` is `argv[1]`, the second token) and an out-of-range index is left
    standing. Both are probe results; the documentation says `$1` is the first argument.
    `$ARGUMENTS[n]` is in the CLI's pattern but was not probed, so it is not modelled here —
    it is only matched, never expanded, which keeps it inside the gate and out of the
    reproduction.
    """

    def _one(match: re.Match[str]) -> str:
        token = match.group(0)
        if token == "$ARGUMENTS":
            return " ".join(argv)
        if token.startswith("$ARGUMENTS["):
            return token
        index = int(token[1:])
        return argv[index] if index < len(argv) else token

    return PLACEHOLDER.sub(_one, text)


#: Rendered into `<instance>/.claude/skills/conclave-<id>/SKILL.md` at every hire, so it is
#: gated as the skill body it becomes rather than as the template it is.
ROUTER_TEMPLATE = (
    REPO / "skills" / "forge-operations" / "references" / "templates" / "advisor-router.md"
)


def _command_docs() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(COMMANDS_DIR.glob("*.md"))}


def _expanded_bodies() -> dict[str, str]:
    """Every document the delivery expander rewrites before a session reads it."""
    bodies = {f"commands/{name}": text for name, text in _command_docs().items()}
    for path in sorted(REPO.glob("skills/*/SKILL.md")):
        bodies[str(path.relative_to(REPO))] = path.read_text(encoding="utf-8")
    bodies[str(ROUTER_TEMPLATE.relative_to(REPO))] = ROUTER_TEMPLATE.read_text(
        encoding="utf-8"
    )
    return bodies


def _hits(text: str) -> list[tuple[int, str]]:
    return [
        (n, line.strip()[:100])
        for n, line in enumerate(text.splitlines(), 1)
        if POSITIONAL.search(line)
    ]


# --------------------------------------------------------------------------- the gate


def test_no_expanded_body_carries_a_positional_placeholder() -> None:
    """The gate. A `$N` in a delivered body is consumed by the expander, always."""
    found = {
        name: _hits(text) for name, text in _expanded_bodies().items() if _hits(text)
    }
    assert not found, (
        "command bodies carry placeholders the delivery expander will consume:\n"
        + "\n".join(
            f"  {name}:{n}: {line}" for name, hits in found.items() for n, line in hits
        )
    )


def test_every_expanded_body_survives_delivery_unchanged() -> None:
    """The same gate stated as the property it protects, and reached the other way.

    `test_no_expanded_body_carries_a_positional_placeholder` asserts a token is absent;
    this asserts the document a session receives is the document in the repo. They can
    disagree only if `POSITIONAL` and `PLACEHOLDER` drift apart, which is the one way the
    first test could pass while the defect is live.
    """
    for argv in ([], ["one"], FIELD_ARGV, ["a", "b", "c", "d"]):
        for name, text in _expanded_bodies().items():
            assert deliver(text, argv) == text, (
                f"{name} is rewritten when it is invoked with "
                f"{len(argv)} argument(s): {argv}"
            )


# ------------------------------------------------------- the instrument, held to its job


def test_the_matcher_flags_placeholders_and_spares_ordinary_shell() -> None:
    flagged = ["$0", "$1==b", "print $2}", "sep, $2;", "$10", "x=$3)"]
    spared = ["$BRANCH", "${PR:-none}", "$(1)", "$(2)", "$1a", "$ARGUMENTS", "$_x", "US$5bn"]
    assert [s for s in flagged if not POSITIONAL.search(s)] == []
    assert [s for s in spared if POSITIONAL.search(s)] == [], (
        "the matcher flags shell the expander never touches: "
        f"{[s for s in spared if POSITIONAL.search(s)]}"
    )


def test_the_scan_reaches_the_documents_it_claims_to() -> None:
    """Anti-vacuity: an empty glob would make the gate pass by finding nothing."""
    docs = _expanded_bodies()
    assert len(docs) >= 8, f"the surface glob found only {len(docs)} documents"
    assert "commands/start.md" in docs, (
        "the document both field reports quote is not in the scan"
    )
    assert any(name.endswith("SKILL.md") for name in docs), (
        "skill bodies are expanded too and none reached the scan"
    )
    assert str(ROUTER_TEMPLATE.relative_to(REPO)) in docs, (
        "the template every advisor skill is minted from is not in the scan"
    )
    decoy = "no placeholder here\nPR=$(awk '$1==b{print $2}' f.tsv)\n"
    assert _hits(decoy) == [(2, "PR=$(awk '$1==b{print $2}' f.tsv)")]


def test_the_expander_reproduces_the_reported_corruption() -> None:
    """The delivered text from both reports, regenerated from the source line."""
    source = "PR=$(awk -F'\\t' -v b=\"$BRANCH\" '$1==b{printf \"%s%s\", sep, $2; sep=\",\"}')"
    delivered = deliver(source, FIELD_ARGV)
    assert "'vera-cto==b{" in delivered, delivered
    assert "sep, $2;" in delivered, (
        "the second field must survive two arguments — the issue claims it does not, "
        "and the index mapping is why: " + delivered
    )
    assert "$2" not in deliver(source, ["--advisor", "vera-cto", "third"])


def test_the_pattern_is_the_one_the_cli_carries() -> None:
    """Provenance. `PLACEHOLDER` is a copy of a pattern that lives in someone else's binary.

    A copy nobody re-checks is a cache, so this looks for it in the installed CLI and says
    so when it is gone — a CLI that stops carrying this pattern has changed the rule the
    gate above encodes, and the gate should be re-derived rather than trusted.
    """
    versions = sorted(Path.home().glob(".local/share/claude/versions/*"))
    if not versions or shutil.which("strings") is None:
        pytest.skip("no installed CLI binary to read the pattern out of")
    newest = versions[-1]
    out = subprocess.run(
        ["/usr/bin/strings", "-a", str(newest)], capture_output=True, text=True, check=False
    )
    needle = r"\$ARGUMENTS\[\d+\]|\$ARGUMENTS|\$\d+(?!\w)"
    assert needle in out.stdout, (
        f"{newest.name} no longer carries the placeholder pattern this gate copies "
        f"({needle!r}) — re-probe the expander before trusting the gate"
    )


# ---------------------------------------------------- the two programs, actually executed


def _awk_line(needle: str) -> str:
    text = (COMMANDS_DIR / "start.md").read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if needle in ln and "awk" in ln]
    assert len(lines) == 1, f"expected one awk line mentioning {needle!r}, got {len(lines)}"
    return lines[0]


def _join_pr(program_line: str, tmp_path: Path) -> subprocess.CompletedProcess[str]:
    tsv = tmp_path / "pr.tsv"
    tsv.write_text("feature-x\t#101:MERGED\nother\t#7:OPEN\n", encoding="utf-8")
    script = (
        "BRANCH=feature-x\n"
        + program_line.replace("/tmp/pr-by-branch.tsv", str(tsv))
        + '\nprintf %s "$PR"\n'
    )
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, check=False
    )


def test_the_branch_pr_join_answers_for_a_branch_that_has_a_pr(tmp_path: Path) -> None:
    """The program as written does its job — otherwise the next test proves nothing."""
    assert _join_pr(_awk_line("pr-by-branch.tsv"), tmp_path).stdout == "#101:MERGED"


def test_the_branch_pr_join_still_answers_after_delivery(tmp_path: Path) -> None:
    """The reproduction, executed. On master this returns "" and the audit reads `pr=none`."""
    delivered = deliver(_awk_line("pr-by-branch.tsv"), FIELD_ARGV)
    result = _join_pr(delivered, tmp_path)
    assert result.stdout == "#101:MERGED", (
        "the branch->PR join is dead in the delivered body; every row renders pr=none, "
        "which the verdict table reads as 'stale' rather than 'fully shipped'.\n"
        f"delivered: {delivered}\nstderr: {result.stderr.strip()}"
    )


def _list_worktree_branches(
    program_line: str, tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    porcelain = tmp_path / "wt.txt"
    porcelain.write_text(
        "worktree /a\nHEAD aaa\nbranch refs/heads/master\n\n"
        "worktree /b\nHEAD bbb\nbranch refs/heads/313-foo\n",
        encoding="utf-8",
    )
    out = tmp_path / "branches.txt"
    script = program_line.replace(
        "git worktree list --porcelain", f"cat {porcelain}"
    ).replace("/tmp/wt-branches.txt", str(out))
    proc = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)
    return subprocess.CompletedProcess(
        proc.args, proc.returncode, out.read_text(encoding="utf-8"), proc.stderr
    )


def test_the_worktree_branch_list_names_the_checked_out_branches(tmp_path: Path) -> None:
    assert _list_worktree_branches(_awk_line("wt-branches.txt"), tmp_path).stdout == (
        "313-foo\nmaster\n"
    )


def test_the_worktree_branch_list_still_names_them_after_delivery(tmp_path: Path) -> None:
    """Three arguments, because two is where `$2` is still safe — measured, not assumed."""
    delivered = deliver(_awk_line("wt-branches.txt"), [*FIELD_ARGV, "third"])
    result = _list_worktree_branches(delivered, tmp_path)
    assert result.stdout == "313-foo\nmaster\n", (
        "the worktree list is empty in the delivered body, so every branch reports `bare` "
        "and the second join of the audit is gone.\n"
        f"delivered: {delivered}\nstderr: {result.stderr.strip()}"
    )

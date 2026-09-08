"""A shipped `gh` list query states its own page size, or its result is a coincidence.

`gh issue list` / `gh pr list` / `gh project item-list` return **30** rows when `--limit` is
absent. That default is not an error and not an empty result: it is a plausible number. Measured
on this instance 2026-09-08, `/conclave:start` Step 3a's own snippet reported `30` open issues
for an advisor who had `75` — the briefing built by `engine briefing build` said 75 and was right,
so the step whose job is to *reconcile the briefing against GitHub* was the one manufacturing the
drift it looks for.

The finding was already known. It is written verbatim as a "known trap" in
`.superpowers/sdd/plan-p3-drainage/task-5-brief.md` in the 220-close-loop-drainage worktree —
a tree git does not track (0 files under `.superpowers` are in the index). It could not reach a
shipped document from there. This gate is the reachable form of that note.

## Perimeter and why it is drawn here

Only **command position inside a fenced block** counts. That is what makes the rule sharp instead
of noisy: of 29 textual occurrences across the shipped surfaces, 10 are prose in running text
("the inbox is `gh issue list --label ...`"), which nobody executes, and 4 more sit inside fences
but are not commands — a shell comment, a mermaid node label, and a YAML `source:` value. All 14
are excluded by construction rather than by a list of exceptions, and
`test_detector_rejects_the_four_non_command_shapes` pins each shape so a later widening cannot
quietly readmit them.

There are **no carve-outs**. `gh pr list --head "$BRANCH"` in `commands/done.md` is bounded in
practice by there being few PRs per branch, and it still carries `--limit`: an exception is a hole,
and the cost of closing this one was six characters.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

# Every shipped surface an operator or agent can be told to execute from.
PERIMETER = [
    REPO / "commands",
    REPO / "skills",
    REPO / "agents",
    REPO / "docs",
    REPO / "engine" / "skills",
]

_GH_LIST = re.compile(r"\bgh\s+(?:issue\s+list|pr\s+list|project\s+item-list)\b")

# Characters that may immediately precede a command. Anything else — a backtick, a colon, a word
# character, a period — means the text is *about* the command, not an invocation of it.
_COMMAND_LEAD = re.compile(r"[|(;&]\s*$")


def _in_command_position(line: str, match_start: int) -> bool:
    before = line[:match_start]
    return before.strip() == "" or bool(_COMMAND_LEAD.search(before))


def _shipped_docs() -> list[Path]:
    out: list[Path] = []
    for d in PERIMETER:
        out.extend(sorted(d.rglob("*.md")))
    return out


def unbounded_queries(text: str) -> list[tuple[int, str]]:
    """Return (1-based line number, joined command) for each in-fence gh list without --limit."""
    lines = text.splitlines()
    hits: list[tuple[int, str]] = []
    in_fence = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            i += 1
            continue
        m = _GH_LIST.search(line) if in_fence else None
        if m and _in_command_position(line, m.start()):
            buf = [line]
            j = i
            while buf[-1].rstrip().endswith("\\") and j + 1 < len(lines):
                j += 1
                buf.append(lines[j])
            joined = " ".join(x.strip() for x in buf)
            if "--limit" not in joined:
                hits.append((i + 1, joined))
            i = j
        i += 1
    return hits


# ---------------------------------------------------------------------------
# anti-vacuity — a gate that scans nothing passes for the wrong reason
# ---------------------------------------------------------------------------


def test_every_perimeter_dir_exists():
    """A renamed-away directory shrinks the scan in silence."""
    missing = [str(d.relative_to(REPO)) for d in PERIMETER if not d.is_dir()]
    assert missing == [], f"perimeter dirs missing: {missing}"


def test_the_scanned_set_is_not_empty():
    docs = _shipped_docs()
    assert len(docs) >= 40, f"only {len(docs)} shipped docs found — the globs went stale"


def test_the_perimeter_actually_contains_gh_queries():
    """If no surface prescribes a gh query at all, a green run means nothing.

    This is the assertion that would have caught the gate being pointed one directory off.
    """
    found = sum(1 for p in _shipped_docs() if _GH_LIST.search(p.read_text()))
    assert found >= 3, f"only {found} shipped docs mention a gh list query — perimeter is wrong"


# ---------------------------------------------------------------------------
# detector self-tests — the exclusions are pinned, not assumed
# ---------------------------------------------------------------------------


def test_detector_finds_the_unbounded_and_spares_the_bounded():
    doc = (
        "prose\n"
        "```bash\n"
        "gh issue list -R o/r --label x --state open --json number --jq 'length'\n"
        "gh issue list -R o/r --label y --state open --limit 200 --json number\n"
        "```\n"
    )
    hits = unbounded_queries(doc)
    assert [n for n, _ in hits] == [3], f"expected only line 3, got {hits}"


def test_detector_follows_a_backslash_continuation():
    """--limit on a later physical line still bounds the command."""
    doc = "```bash\ngh issue list -R o/r --state open \\\n  --limit 200 --json number\n```\n"
    assert unbounded_queries(doc) == []


def test_detector_rejects_the_four_non_command_shapes():
    """The exact four in-fence false positives measured on this tree, 2026-09-08."""
    shapes = {
        "shell comment": "```bash\n# A `gh pr list` per branch is N round-trips\n```\n",
        "mermaid node": "```mermaid\nA -->|stale| f[Fetch from dep\\ne.g. gh issue list]\n```\n",
        "yaml value": "```yaml\nsource: gh issue list\n```\n",
        "table cell": "```text\n| source | Always `gh issue list`; records the command |\n```\n",
    }
    for name, doc in shapes.items():
        assert unbounded_queries(doc) == [], f"{name} was wrongly flagged as a command"


def test_detector_ignores_prose_outside_a_fence():
    doc = "The inbox is `gh issue list --label \"advisor:<name>\"` and nothing else.\n"
    assert unbounded_queries(doc) == []


def test_detector_still_sees_a_command_after_a_pipe_or_subshell():
    """Excluding non-command text must not exclude real commands in a pipeline."""
    doc = "```bash\nfor R in $(gh issue list --json number --jq '.[].number'); do :; done\n```\n"
    assert len(unbounded_queries(doc)) == 1


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------


def test_no_shipped_gh_query_is_unbounded():
    findings: list[str] = []
    for p in _shipped_docs():
        for line_no, cmd in unbounded_queries(p.read_text()):
            findings.append(f"{p.relative_to(REPO)}:{line_no}  {cmd[:110]}")
    assert findings == [], (
        "gh list queries without --limit — each silently caps at 30 rows:\n  "
        + "\n  ".join(findings)
    )

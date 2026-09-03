---
description: >-
  Writes a structured resume-prompt for unfinished work — what was done, what is left, and
  where to pick it up — so the next session continues instead of rediscovering the context.
  Use when stopping mid-task; /conclave:done invokes it automatically when work is incomplete.
---

!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/github-issues-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/session-lifecycle.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/advisor-anti-patterns.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/feedback-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-formatting.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-discipline.md`

# /conclave:handoff — Resume Prompt Creation

> **MANDATORY** when work is incomplete. Invoked by `/conclave:done`. Works independently — no Quorum required.

## Resume-Prompt Format

```markdown
# Resume: [task name]

> Created: YYYY-MM-DD | Agent: [name] [emoji] | GH Issue: #N   ← required, resolvable

## Status: IN_PROGRESS | BLOCKED
## Task: one-line description
## Completed
- bullet items (3-7)
## Current State
- file paths that were modified (not descriptions — actual paths)
## Next Steps
1. concrete action (not "continue work")
2. concrete action
## Blockers
- if any (or "None")
## Failed Approaches
- what was tried and why it didn't work (or "None")
## Required Skills
- skills needed in next session
```

## File handoff

Compose body into `/tmp/handoff-<slug>.md`, then:

```bash
python -m engine file handoff \
  --from <advisor> --to <recipient> \
  --date <ISO-date> --priority <p0|p1|p2> \
  --title "<title>" --slug <slug> \
  --body-file /tmp/handoff-<slug>.md \
  --gh-issue <#N | AI#N | owner/repo#N | https://github.com/o/r/issues/N> \
  [--policy <ref>]
```

**`--to` decides who receives it (#202).** The filename is keyed to the *author*
(`{date}-{from}-{slug}.md`); delivery is keyed to `--to`, which `session_init`'s resume-scan
reads back out of the document's `> **From**: … | **To**: …` header. Name a hired advisor —
`filing.py` refuses anything else — and the handoff appears at *their* next session start and
not at yours. Prose (`next session`, `operator`) is what six pre-validation files carry; those
fall back to the author-keyed filename, which is why a retired id like `forge` addresses nobody.

**The reference is required (#55).** A handoff has no terminal state: the resume-scan ranks
by mtime and never learns that the work shipped, so an exhausted handoff resurfaces as
"interrupted work" forever — two were surfacing at 1374h and 1226h, both tracking PRs that
merged in July. A resolvable reference is what lets a reader answer *is this still live?*
without reading the file. Free text is refused: a bare `113` names nothing, and `AI#113` was
once written meaning **spec** 113 while GH#113 was an unrelated merged PR.

When there is genuinely nothing to reference — an exploratory spike, a thread that has not
been filed — record *why*, and the reason is written into the document:

```bash
  --no-issue "exploratory spike on X, nothing filed yet"
```

Through `/conclave:done` the same pair is `--handoff-issue` / `--handoff-no-issue` on
`engine session close`, validated before the session document is written.

**Handoffs go stale.** `session_init` demotes any handoff untouched for more than 336h out
of "interrupted work" and into a `stale handoffs` list that names the archive command. When
a handoff's work has shipped, retire it — the move is reversible, never a delete:

```bash
python -m engine lifecycle archive-handoff <filename.md>
```

Commit is part of the enclosing `/conclave:done` aggregate. Handoffs filed outside `/conclave:done` require explicit `git add` + `git commit` by caller.

## Validation

Before invoking the script, verify:

1. All file paths in "Current State" exist → `ls` each path
2. GH Issue is still open → `gh issue view <N> -R <code-repo> --json state`. A closed one
   means the handoff is already exhausted: file nothing, or reference the successor issue.
   Pass `-R` — issues live in the CODE repo, never in DATA.
3. Next Steps are actionable — not vague ("finish implementation" ❌)
4. Required Skills are real skill names — check against available skills list

## Chat-output (handoff confirmation)

After `engine file handoff` writes the .md artifact, render the ▍-block confirmation per `output-formatting.md`. The .md file format above is SEPARATE — that's the persisted artifact; this is the chat acknowledgement.

▍ **{persona-emoji} {advisor} · handoff · {date}**
▍
▍ **status**     {IN_PROGRESS | BLOCKED}
▍ **to**         {persona-emoji} {recipient}          ← cross-ref keeps recipient emoji
▍ **slug**       `{slug}`
▍ **file**       `ops/handoffs/{date}-{advisor}-{slug}.md`
▍ **gh-issue**   AI#{N}                              ← or `none — {reason}`
▍ **priority**   {p0 | p1 | p2 | p3}
▍ ⚠ **blocker**  {one-line if BLOCKED}                ← OMIT if IN_PROGRESS
▍
▍ **next →** resume via `/conclave:start` with `--resume {file}` in next session

## Anti-patterns

- ❌ Narrative prose ("we discussed many options and decided...")
- ❌ Missing file paths (forces next agent to search)
- ❌ Vague next steps ("continue work on feature")
- ❌ Unlisted required skills
- ❌ An unresolvable reference ("see the PR", a bare spec number)
- ✅ Structured fields with concrete values
- ✅ Verified file paths
- ✅ Numbered next steps with specific actions

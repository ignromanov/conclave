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

# /conclave:handoff — Resume Prompt Creation

> **MANDATORY** when work is incomplete. Invoked by `/conclave:done`. Works independently — no Quorum required.

## Resume-Prompt Format

```markdown
# Resume: [task name]

> Created: YYYY-MM-DD | Agent: [name] [emoji] | GH Issue: #N

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
  --from <advisor> --to <recipient(s)> \
  --date <ISO-date> --priority <p0|p1|p2> \
  --title "<title>" --slug <slug> \
  --body-file /tmp/handoff-<slug>.md \
  [--policy <ref>] [--gh-issue AI#N]
```

Commit is part of the enclosing `/conclave:done` aggregate. Handoffs filed outside `/conclave:done` require explicit `git add` + `git commit` by caller.

## Validation

Before invoking the script, verify:

1. All file paths in "Current State" exist → `ls` each path
2. GH Issue (if referenced) is still open → `gh issue view #N --json state`
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
▍ **gh-issue**   AI#{N}                              ← OMIT if no issue ref
▍ **priority**   {p0 | p1 | p2 | p3}
▍ ⚠ **blocker**  {one-line if BLOCKED}                ← OMIT if IN_PROGRESS
▍
▍ **next →** resume via `/conclave:start` with `--resume {file}` in next session

## Anti-patterns

- ❌ Narrative prose ("we discussed many options and decided...")
- ❌ Missing file paths (forces next agent to search)
- ❌ Vague next steps ("continue work on feature")
- ❌ Unlisted required skills
- ✅ Structured fields with concrete values
- ✅ Verified file paths
- ✅ Numbered next steps with specific actions

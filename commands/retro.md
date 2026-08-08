---
description: >-
  Runs a three-question retrospective — what worked, what did not, what to try next — and
  appends it to the retro log. Use at a session or sprint boundary when the team wants the
  lesson recorded rather than re-learned. Takes about ten minutes.
tier: lifecycle
created: 2026-05-07
---

!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-formatting.md`

# /conclave:retro — Lightweight retrospective

> 3 questions. ≤10 min. Append-only retro log. Absorbed from project-delivery/.

## When to invoke

- Manual: founder says "retro" / "ретро" / "let's retro"
- Auto (optional): after major spec completion (e.g., spec 070 merge)
- Quorum invokes after every 3rd `/conclave:done` if no manual trigger

## Three questions

1. **What worked?** — keep doing
2. **What didn't?** — stop or change
3. **What to try?** — small experiment for next cycle

## Format

Present 3 questions to the founder via AskUserQuestion. Founder + advisors (if dispatched) contribute.

## Output

Append to `.ai/agent-memory/advisors/retros/YYYY-MM-DD-retro.md`:

```markdown
---
date: YYYY-MM-DD
participants: [list]
trigger: manual|auto-spec-complete|every-3rd-done
---

# Retro — YYYY-MM-DD

## Worked
- ...

## Didn't
- ...

## Try next
- ...

## Action items (optional)
- @<advisor>: <task> (priority: pN)
```

Action items optionally promoted to GH Issues via existing `inbox-to-gh.sh` script.

## Chat-output (retro confirmation)

After writing the .md artifact, render a v3.2 ▍-block confirmation per `${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-formatting.md` (the .md file format above is the persisted artifact; this is the chat acknowledgement). Header has no single speaker — use `participants` instead of persona-emoji.

▍ **participants · retro · {date}**
▍
▍ **trigger**    {manual | auto-spec-complete | every-3rd-done}
▍ **worked**     {one-line summary}
▍ **didnt**      {one-line summary}
▍ **try-next**   {one-line summary}
▍ **action →**   {persona-emoji} {assignee}: {task} ({priority})  ← OMIT if no actions; repeat row per action
▍ **file**       `agent-memory/advisors/retros/{date}-retro.md`
▍
▍ **next →** file action items as GH Issues · invoke briefings to surface in next /conclave:start

## Anti-patterns

- Long retros — cap 10 min; defer to working session if more needed
- Retro for solo work — only useful with 2+ participants or after multi-session epic
- Retro action items skipping triage — file as GH Issue or BRIEFING action item, not free-floating

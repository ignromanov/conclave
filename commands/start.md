---
description: >-
  Opens an advisor session with its context already loaded — the advisor's briefing, live
  cross-agent state, open GitHub issues, and any interrupted work offered for resume — then
  sizes the task and routes it to the right skill chain. Use at the start of every advisor
  session, before doing any work.
---

!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/agent-data-policy.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/github-issues-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/session-lifecycle.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/first-launch-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/decision-framework.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/quality-loop.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/advisor-anti-patterns.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/feedback-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-formatting.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-discipline.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/question-shape.md`

# /conclave:start — Session Initialization

> **MANDATORY** for every advisor session. Works independently — no Quorum required.
>
> **Cardinal Rule**: GitHub Issues = source of truth for tasks. The auto-generated briefing is a dashboard cache that references issues (AI#N, GH#N). When they conflict, GH wins.

## Question shape

Every user choice in this skill follows the **prose-context + condensed-Ask** pattern —
see `question-shape.md` (auto-imported). Applies here to: resume-vs-fresh (Step 1b),
tier override + skill-chain pick (Step 7), briefing-conflict resolution (Step 3c).

## Process

### 0. Self-heal SessionStart hook

!`python3 "${CLAUDE_PLUGIN_ROOT}/engine/scripts/init/reconcile_hook.py" 2>&1 || true`

Best-effort repair of the SessionStart hook's command path + `CONCLAVE_ENGINE_ROOT` in
`.claude/settings.json`, in case they still point at a plugin cache dir removed by a prior
`/plugin update` (099 followups B1). Runs before session-init below, which needs a valid
engine root.

### 0b. Provision engine deps

!`python3 "${CLAUDE_PLUGIN_ROOT}/engine/scripts/init/provision_deps.py" 2>&1 || true`

Best-effort install of the engine's third-party deps (PyYAML/pydantic/python-frontmatter/
ruamel.yaml) into `${CLAUDE_PLUGIN_DATA}/venv`, so `python -m engine <cmd>` (used throughout
this skill and others) has its deps available on a fresh consumer or right after a
`/plugin update` wiped the in-tree `.venv` (099 followups B4). Idempotent; never blocks
session start.

### 1. Load briefing

1. Detect the advisor from the `/conclave-<id>` router invocation (the router binds
   `advisor=<id>` and passes it to session-init). For `forge-chro`, this is `/conclave-forge-chro`.
2. Run session-init (Steps 1/1b/1c + Overlay in one call):
   ```bash
   python3 engine/scripts/lifecycle/session_init.py --advisor <advisor>
   ```
   Exit codes: 0 = cache-hit / briefing content unchanged, 2 = briefing regenerated, 1 = error
   (the briefing could not be built). A failed gh-fetch is non-fatal (#76): the run
   continues and prints a `degraded: gh-data-unavailable` line — board-derived
   sections come from the stale cache, the rest of the briefing is current.
   The script handles: gh-fetch (TTL=900s), briefing build-and-compare (always rebuilds; writes
   only if content differs), resume-scan (ops/specs/*/resume-prompt.md + ops/handoffs/*-<advisor>-*.md),
   reflexion extract (last-3 sessions), overlay scan, and feedback cadence check.
   If a line starting with `  feedback:` appears in the output, triage is due — include it in
   the session-start summary and suggest running `/conclave:triage` this session.
3. Read `.conclave/agent-memory/advisors/briefings/<advisor>.md` into context.
4. Load `hot.md` **once** separately (AC8 — no longer embedded in briefings):
   ```bash
   cat .conclave/agent-memory/hot.md
   ```
   Read the Now / Recent decisions / Watch sections for live cross-agent state.
5. The briefing and hot.md are auto-generated; do not edit either directly.

### 1b. Resume Check

The session-init script (Step 1) prints resume findings prefixed `resume:`. Read its output:

- Lines starting `  spec-resume:` — interrupted spec worktree; path + age in hours shown.
- Lines starting `  handoff:` — filed handoff for this advisor; filename + age shown.

If found → apply **Question shape** (above):

1. **Prose first** — describe each found item: title, path, last-update mtime, what was in progress (one-line from resume-prompt header), and what "resume" vs "start new" means (resume = load original skill chain + reuse session id; start new = current request takes over, old resume-prompt stays unconsumed on disk for later).
2. **`AskUserQuestion`** — `label`s: "Resume" / "Start new" / "Skip" (≤ 5 words each); `description`s ≤ 1 sentence each.

If user picks Resume → read resume-prompt, load required skills from it, skip to Step 5.
If Start new → leave the file in place; mention in `/conclave:done` Lifecycle Retrospective if it's been stale > 3 days.

### 1c. Reflexion Context

The session-init script (Step 1) prints reflexion findings prefixed `reflexion:`. Read its output:

- Lines starting `  - [<session-file>]` — non-empty reflexion value from that session.
- If `reflexion: none` → skip silently (no signal, no noise).

If any reflexions were surfaced, apply them as priors for this session:

> "Recent reflexions for ${ADVISOR}:
> - {reflexion-1}
> - {reflexion-2}
> Apply these as priors for this session."

### 2. Tier Detection

> **Forge (meta-advisor) carve-out:** if the advisor is `forge`, skip domain
> tier-detection and the GitHub issue-board step — forge has no domain board and
> follows the `forge-operations` flow, not domain tiers. Run only the lifecycle
> steps session-init performs for meta-advisors (briefing / resume / reflexion /
> overlays); see the spec §3.3 step matrix.

Classify user request by scale:

| Signal | Tier | Ceremony |
|--------|------|----------|
| Quick question, opinion, <30 min | **Quick** | Minimal GH check (Step 3a), skip steps 4-5 |
| Feature work, 1-4 hours, clear scope | **Feature** | Full init (Steps 3b-6) |
| Multi-session, worktree, epic scope | **Epic** | Full init + checkpoint plan |

### 3. GH Issue Check (MANDATORY — all tiers)

> **GH Issues = source of truth.** Always check before working.
> The instance's repos feed into its configured **roadmap project board** (owner/repos/board from `roster.yaml`).

#### 3a. Quick Tier (minimal)

```bash
# Repo scope comes from the resolver, never from raw roster keys: an instance with a single repo
# has ai_repo null, and `-R "$OWNER/$(roster.py github.ai_repo)"` builds the malformed slug
# `owner/`. `gh-repos` applies the same roster → git-remote → refuse layering gh-fetch uses, and
# exits 1 rather than printing an empty list.
ROOT="${CLAUDE_PLUGIN_ROOT:-.}"
ADVISOR=<advisor>   # the slug this session is bound to
for REPO in $(PYTHONPATH="$ROOT/engine/scripts" python3 -m engine lifecycle gh-repos); do
  gh issue list -R "$REPO" --label "advisor:$ADVISOR" --state open \
    --json number,title --jq 'length' &
done
wait
```

Show: "You have N open issues (AI: X, Code: Y). P0 blockers: [list or none]."
If user's question relates to an open issue — mention it. Then answer directly.

#### 3b. Feature/Epic Tier (full)

```bash
# Same resolver as 3a — one repo or two, the loop adapts; an unscoped instance exits 1 here
# instead of silently iterating nothing.
ROOT="${CLAUDE_PLUGIN_ROOT:-.}"
ADVISOR=<advisor>
for REPO in $(PYTHONPATH="$ROOT/engine/scripts" python3 -m engine lifecycle gh-repos); do
  gh issue list -R "$REPO" --label "advisor:$ADVISOR" --state open &
  # P0 blockers, including ones assigned to other advisors
  gh issue list -R "$REPO" --label p0 --state open &
done
wait
```

Present open items in a compact table with source repo prefix (AI#N / GH#N).
**Match user's request to an existing issue.** If matched → reference it throughout the session.

**Alternative** — single Project Board query (shows both repos + all custom fields):
```bash
gh project item-list "$(python3 engine/scripts/lib/roster.py github.board_number)" --owner "$(python3 engine/scripts/lib/roster.py github.owner)" --format json --limit 100 | \
  python3 engine/scripts/lifecycle/gh_board_query.py \
    --mode advisor-open --advisor <advisor>
```

#### 3c. BRIEFING ↔ GH Reconciliation (Feature/Epic)

Compare briefing Action Items (from the regenerated `.conclave/agent-memory/advisors/briefings/<advisor>.md`) with `gh issue list` results from **both repos**:

| Mismatch | Action |
|----------|--------|
| Briefing has AI#N / GH#N but issue is closed | Flag: "AI#N closed in GH but still in briefing — will clean up in /conclave:done" |
| GH has open issue for this advisor not in briefing | Flag: "AI#N / GH#N exists in GH but missing from briefing" |
| Briefing status differs from Project Board status | Flag drift, use GH as truth |

Present mismatches (if any) before proceeding. Don't fix now — `/conclave:done` handles cleanup.

### 4. Startup Audit (Feature/Epic only)

```bash
gh pr list --state open &
git branch --no-merged develop &
ls worktrees/ 2>/dev/null &
(cd .conclave && git status --short) &
wait
```

Show results as a compact table. Flag mismatches (worktrees without PRs, branches without worktrees). Skip the table if everything is clean.

### 4.5. Wiki Domain Context (Feature/Epic only)

Load domain context from the wiki for richer advisory. Which areas to load is **derived, not
tabulated** — the roster is instance data and so are the vault's areas:

1. Take the bound advisor's domain from its responsibilities (its agent-def frontmatter, or
   `roster.yaml`) — the same `<advisor>` Step 1 bound this session to.
2. List the vault's areas — the top-level folders under the wiki path:
   ```bash
   ls "$(python3 engine/scripts/lib/roster.py knowledge.wiki_path)"
   ```
3. `/wiki:browse <area>` the one or two whose names match that domain. Two is the ceiling —
   this is context loading, not research.

Skip the step (and say so) when no area matches the advisor's domain, or when the context it
would load is already in the session via `@import`.

Optional: `/wiki:query "topic"` for task-specific context.

### 5. Skill Routing

Detect task type → load required skill chain. Every external target carries its plugin prefix, so a
missing one is visible as a missing plugin rather than as silence — except the two rows marked †
below and the `find-skills` fallback itself, which are unprefixed by design: user-level skills in
the operator's private `~/.claude/skills`, shipped by no plugin. On a fresh install those three
will not resolve, and that silence is not caught by anything — know it going in.

> **Provenance, not dependency.** The `superpowers:*` and `marketing-skills:*` rows are third-party
> prior art carried until spec 108 P2 authors Conclave-owned procedures for the stages that earn
> one. They are cited here, never `Skill()`-ed from engine code.

| Task Type | Skill Chain |
|-----------|-------------|
| New feature | superpowers:brainstorming → superpowers:writing-plans |
| Bug fix | superpowers:systematic-debugging |
| Content | marketing-skills:product-marketing-context → marketing-skills:copywriting → marketing-skills:copy-editing |
| Grant | grant-proposal-assistant † |
| Code review | superpowers:requesting-code-review |
| Security | senior-security † |
| Meeting | the instance's facilitator slot, if one was hired — see the roster |
| Plan execution | superpowers:subagent-driven-development |

† unprefixed on purpose — user-level, not shipped by any plugin, absent on a fresh install.

If no matching skill exists:
1. Search with `find-skills` — also user-level, same caveat
2. If found installed → invoke
3. If found remote → recommend install to user
4. If not found → work best-effort, log gap in /conclave:done

### 6. Create Session Tasks (Feature/Epic only)

**MANDATORY**: Create tasks via TaskCreate for the current work session. Always include `/conclave:done` as the final task so it is never forgotten.

Example:
```
TaskCreate: "Load context and check resume state"       → in_progress
TaskCreate: "[Main work description from user request]" → pending
TaskCreate: "Run /conclave:done completion checklist"       → pending
```

The `/conclave:done` task MUST be the last task. It ensures: commits, GH issues sync, BRIEFING update, wiki capture, and handoff if incomplete.

### 7. Present & Confirm (Feature/Epic only)

Render the start-summary using the ▍-framed format (per `output-formatting.md` Per-skill instantiation table):

▍ **{persona-emoji} {advisor} · session-start · {date}**
▍
▍ **focus**       {current focus from briefing}
▍ **queue**       {N} open issues ({AI: x, GH: y}) · {P0_count} P0
▍ **briefing**    `agent-memory/advisors/briefings/{advisor}.md` ({unchanged | regenerated})
▍ ⚠ **interrupted** {title} ({path})              ← OMIT if none
▍ **tier**        {Quick | Feature | Epic}
▍ **skills**      {chain → e.g. superpowers:brainstorming → superpowers:writing-plans}
▍
▍ **next →** {first concrete action from the chain}

Then apply **Question shape** (above) to the approval gate:

1. **Prose first** — name the tier you picked (Quick / Feature / Epic) and *why* (which signal from §2 fired), the skill chain you're about to load and what each skill in it costs (rough context budget / time-on-task), and the first concrete action you'd take. State explicit alternatives if the tier-pick was borderline ("could also run as Feature if you want spec.md upfront").
2. **`AskUserQuestion`** — labels: "Proceed" / "Switch tier" / "Different skill chain" / "Abort" (≤ 5 words). Descriptions ≤ 1 sentence.

For Quick tier the render above is **mid-run**, not terminal: the Ask gate is skipped and the work
proceeds inside the same operator turn, so a block here plus the work's own report would be two
terminal objects for one run — `output-discipline.md` R1. Do not render a start-summary for Quick
tier.

Carry `focus` and `queue` into slot 2 (`required / assumed`) of the run's terminal block, and the
first concrete action into slot 5. Nothing is lost: the same three facts arrive once, attached to
the result they framed, instead of ahead of it.

If the request is ambiguous, the run does not proceed on a guess — that is R7 case 1, so ask with
`AskUserQuestion` and end the run there. The block above stays exactly as written for Feature and
Epic, where the Ask gate that follows it makes it terminal under R8.

## Overlay loading

After loading base contracts, session-init (Step 1) prints overlay findings prefixed `overlays:`.
Read its output:

- Lines starting `  overlay:` — path to an advisor-specific contract override.
- If `overlays: none` → no overrides; base contracts apply as-is.

Apply each listed overlay. Overlay semantics (`constraint` / `extension` / `replacement`) per
`${CLAUDE_PLUGIN_ROOT}/skills/forge-operations/references/aspects/contract-overlays.md`.

To run overlay scan in isolation:
```bash
python3 engine/scripts/lifecycle/session_init.py --advisor <advisor>
```

> Vault setup: see `${CLAUDE_PLUGIN_ROOT}/skills/forge-operations/references/obsidian-vault-setup.md`

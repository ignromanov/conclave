---
type: architecture
schema_version: 1
title: "Session Lifecycle — Mandatory Ritual"
created: 2026-06-11
status: current
scope: Conclave engine lifecycle (C-004)
see_also:
  - overview.md
  - engine-modules.md
source_skills:
  - team.start/SKILL.md
  - team.processing/SKILL.md
  - team.done/SKILL.md
  - team.handoff/SKILL.md
---

# Conclave — Session Lifecycle

> **Single question this doc answers:** "What must happen at the start and end of every advisor
> session, why is it mandatory, and what does it produce?"
>
> This doc maps the four lifecycle skills to their constitutional obligations and describes
> the Conclave adaptations required during extraction from VoidPay's `.ai/`.

---

## Why the ritual exists

The memory model (constitution II) only works if the source of truth is kept current. An advisor
session that begins without loading the latest briefing operates on stale state. A session that
ends without filing decisions and emitting feedback silently loses work — the next session starts
with no record of what was decided or what broke.

Constitution III states it plainly: **"Skipping `done` is drift. The ritual is what makes the
memory trustworthy."** Un-closed work corrupts the record.

The lifecycle ritual is the enforcement mechanism for constitutions II and III:

| Phase | Constitution enforced |
|-------|-----------------------|
| `start` — briefing load | II (cache rebuilt if stale; truth loaded before work) |
| `start` — GH issue check | II (GH = source of truth for tasks; briefing is the cache) |
| `done` — feedback emission | III (every session contributes to the self-improvement loop) |
| `done` — artifact filing | III (decisions/mentions/reflexion persisted before session closes) |
| `done` — briefing regen trigger | II (cache will rebuild at next `start` from updated truth) |

---

## The five skills

The mandatory ritual is composed of four skills plus one optional retrospective. In Conclave,
all five are implemented as lifecycle skills — not agents. They carry no model; they are
invocation-time protocols that any advisor runs.

```
start → processing → [work] → done → handoff (if incomplete)
                                    └─ retro (optional, every 3rd done)
```

---

## team.start — Session initialization

**Purpose:** Load the advisor's context window with the current state of the world before any
work begins. Detect whether interrupted work should resume. Classify request scale.

**Inputs:** advisor name, optional `--resume <file>` flag.

### Steps

| Step | What happens | Output |
|------|-------------|--------|
| **1. Load briefing** | `session_init.py --advisor <name>` runs: TTL-gated `gh-fetch.sh` + `git-fetch.sh`; briefing build-and-compare (`briefing-build.sh` / `python -m briefing` always runs, writes only if content differs); resume scan; reflexion extract (last 3 sessions); overlay scan; feedback cadence check | Briefing loaded into context; resume/reflexion/overlay findings printed as prefixed lines |
| **1b. Resume check** | If `spec-resume:` or `handoff:` lines in step 1 output → present with `AskUserQuestion` (Resume / Start new / Skip) | User confirms whether to continue interrupted work |
| **1c. Reflexion context** | Last 3 non-empty `reflexion:` values from prior sessions applied as priors | Advisor starts session aware of recent failure patterns |
| **2. Tier detection** | Classify by signal: Quick (<30 min, opinion) / Feature (1–4h, clear scope) / Epic (multi-session, worktree) | Tier governs ceremony depth for all subsequent steps |
| **3. GH issue check** | Quick: count open issues. Feature/Epic: full list + match request to existing issue + reconcile briefing Action Items vs GH | Open issues surfaced; mismatches flagged for cleanup in `done` |
| **4. Startup audit** | Feature/Epic only: `gh pr list`, unmerged branches, worktrees, `.ai git status` | Stale worktrees or branches without PRs flagged |
| **4.5. Wiki context** | Feature/Epic only: load domain context from knowledge wiki per advisor role | Richer context for advisory work |
| **5. Skill routing** | Map task type to workflow skill chain | Skill chain identified before work starts |
| **6. Create tasks** | Feature/Epic only: `TaskCreate` for each work item + mandatory `/team.done` as final task | Task list tracking the session |
| **7. Present & confirm** | Render `▍`-framed start summary; `AskUserQuestion` for tier/chain confirmation | Session confirmed before work begins |

**Constitution II gate at step 1:** `session_init.py` always runs the briefing rebuild
(`briefing-build.sh` / `python -m briefing`; there is no `briefing-build.py`) before loading, and
writes only when the rebuilt content actually differs from what's on disk (build-and-compare).
The advisor never works from a stale cache — the cache rebuilds automatically, and mtime no longer
gates whether that happens.

**Exit codes from `session_init.py`:**

| Code | Meaning |
|------|---------|
| 0 | Cache hit — briefing content unchanged, loaded as-is |
| 2 | Briefing regenerated — rebuilt content actually differed |
| 1 | Error — the briefing itself could not be built |

gh-fetch and git-fetch are advisory inputs, so a failure in either is non-fatal (#76):
the step logs `FAILED … — continuing` plus a `degraded: gh-data-unavailable` marker and
proceeds to the briefing build. Exit 3 ("stale-fail") is no longer emitted — it returned
*before* the briefing was built at all, so an instance whose roster declares no repos
never reached briefing build at all.

---

## team.processing — Work routing

**Purpose:** Detect what kind of session this is (mode) and route to the right workflow skill.
Runs after `start`, before any substantive work.

**Inputs:** current request content; tier from `team.start`.

### Steps

| Step | What happens | Output |
|------|-------------|--------|
| **GH bind** | Match request to open GH issue from `start` step 3; if matched, set Project Board → `In Progress` | Session bound to a tracked issue |
| **Mode detection** | Quick Answer / Working Session / Meeting / Execution | Mode determines ceremony |
| **Type detection** | Working Session only: Development / Content / Grant / Advisory / Review | Workflow skill selected |
| **Skill execution** | Invoke identified workflow skill via Skill tool | Work proceeds under skill discipline |

**Ambiguity rule:** if two modes are equally plausible, `processing` does not pick silently. It
surfaces the conflict via `AskUserQuestion` with the cost of misroute explained.

**Mode routing table:**

| Mode | Trigger | Action |
|------|---------|--------|
| Quick Answer | Opinion question, <30 min | Answer directly; no workflow; record any decision |
| Working Session | "let's work on X", task | Type + tier detection → workflow skill |
| Meeting | "team meeting", "discuss" | Invoke Forge facilitation mode |
| Execution | "execute plan", `plan.md` present | `subagent-driven-development` |

---

## team.done — Session completion

**Purpose:** Ensure every session ends with its output persisted, its feedback emitted, and
GH issues current. This is the phase that keeps the source of truth trustworthy.

The skill runs a mandatory-then-conditional checklist. The execution order is fixed:

```
Feedback emission → Artifact filing → Study → Infra → Lifecycle Retrospective → Reflexion → hot.md
```

### Phase: Feedback emission (mandatory gate)

Every session must emit a structured work review via `feedback_emit.py` before filing artifacts.
This feeds C-001 (Notebook) and is the entry point for the self-improvement loop.

```bash
feedback_emit.py --agent <advisor> --agent-type advisor \
  --session-ref <id> --skill-version sha256:<12-hex>
```

An `emission-gate.sh` script enforces completion: if no non-draft emission exists for the
session, the gate exits non-zero and the rest of `done` is blocked until the emission is filed.

### Phase: Artifact filing

Scripts write to disk; one aggregate commit closes the session:

| Artifact | Script | Destination |
|----------|--------|-------------|
| Decisions | `file-decision.sh` | `agent-memory/advisors/<advisor>/decisions/` |
| Mentions | `mention.sh` | `agent-memory/advisors/<recipient>/mentions/` |
| Session record + reflexion | `close-session.sh` | `agent-memory/advisors/<advisor>/sessions/` |
| Handoff (if incomplete) | `file-handoff.sh` | `ops/handoffs/` |

The `--reflexion` arg to `close-session.sh` is mandatory. It is persisted to `session.md`
frontmatter and injected into the next 3 sessions via `team.start` step 1c.

### Mandatory checklist items (always)

1. All changes committed (both repos if applicable).
2. GH Issues synced — worked issues commented, completed issues closed, new tasks recommended.
3. Session artifacts filed via the scripted flow above.

### Conditional checklist items (fire situationally)

| # | Condition | Action | Gate |
|---|-----------|--------|------|
| 4 | Session produced new knowledge | Wiki capture | Auto |
| 5 | New slice/component created | Architecture registries updated | Auto |
| 6 | Spec deviation found | `spec.md` updated | Approve |
| 7 | Work incomplete | Invoke `team.handoff` | Auto |
| 8 | Skill gap found | Log for creation via `writing-skills` | Notify |

### Phase: Study

Runs `study_phase.py --advisor <advisor>`. Orchestrates 6 wiki health steps:
capture-suggest → promote-decision → bridge-rebuild → audit-stale → hot-sync → link-check.

Exit 3 (P0 blocking: wiki audit contradictions) must be resolved before `close-session.sh`.
All other failures are non-blocking (wiki-failure-policy: defer per ADR-0003).

### Phase: Lifecycle Retrospective

Five lenses scan for improvement signals — even when the session went smoothly:

| Lens | What to look for | Feedback category |
|------|-----------------|-------------------|
| broke | Script exit ≠ 0, missing file, contract violation | `script-defect` |
| unexpected | Output shape drift, naming mismatch, docs out of sync | `doc-contradiction` |
| script-improvement | Brittle parse, missing `--dry-run`, opaque error | `skill-gap` / `process-friction` |
| automation | Work done by hand that a script could do deterministically | `idea` |
| context-reduction | Re-read of already-loaded file, large file for one fact | `process-friction` |

Each finding is emitted as a `/team.feedback` item (cap: 5 per session). This phase feeds
the self-improvement loop directly — it is the primary signal source for recurring patterns.

### Phase: Reflexion

One sentence (≤280 chars), format "what surprised me / what I'd do differently". Stored in
`session.md` frontmatter. Read back at the next 3 sessions as behavioral priors. Filler
("good session") is forbidden — it degrades the buffer faster than a blank.

**Constitution III enforcement**: `close-session.sh` will not complete without `--reflexion`.
A session without a reflexion is a session without a closed loop.

---

## team.handoff — Resume-prompt creation

**Purpose:** Preserve enough state that the next session can resume without interrogating
the advisor that filed the handoff. Invoked by `team.done` when work is incomplete.

**Output format** (written to `ops/handoffs/<date>-<advisor>-<slug>.md`):

```markdown
# Resume: <task name>
> Created: YYYY-MM-DD | Agent: <name> | GH Issue: #N
## Status: IN_PROGRESS | BLOCKED
## Task: one-line description
## Completed
- bullet list (3–7 items)
## Current State
- actual file paths modified (not descriptions)
## Next Steps
1. concrete action
2. concrete action
## Blockers
- description or "None"
## Failed Approaches
- what was tried and why it failed, or "None"
## Required Skills
- skill names needed in next session
```

**Validation before filing:**
- Every path in "Current State" exists on disk (`ls` each).
- Referenced GH issue is still open (`gh issue view #N --json state`).
- Next Steps are specific, not vague ("finish feature" is rejected).
- Required Skills are real installed skill names.

`team.start` step 1b surfaces filed handoffs at the next session start.

---

## Conclave adaptation notes

The lifecycle skills run in VoidPay's `.ai/` today. Three changes are required before they run
cleanly in a Conclave instance without VoidPay-specific assumptions.

### ENGINE_ROOT decoupling (blocking prerequisite)

All scripts that assume `VOIDPAY_AI_ROOT` or an absolute path to `.ai/` must be parameterized.

| File | Current hardcoding | Required change |
|------|--------------------|-----------------|
| `briefing/paths.py` | `VOIDPAY_AI_ROOT` env | `CONCLAVE_ROOT` env |
| `paths.sh` | `VOIDPAY_AI_ROOT` | `ENGINE_ROOT` variable (`".ai/"` for VoidPay, `""` for Conclave) |
| `team.done/SKILL.md:109` | absolute path `~/code/voidpay/.ai` | `${CONCLAVE_ROOT}` |
| `create-advisor.sh:7` + `register-advisor.sh:7` | `PROJECT_ROOT=~/code/voidpay` | `${CONCLAVE_ROOT:-...}` |
| `session_init.py` | `briefing-build.sh` path | relative from `ENGINE_ROOT` |
| `github-issues-protocol.md` | `ignromanov/voidpay*` owner/repo, project board `PVT_kwHOADCDMs4BSDpY` | `${GH_OWNER}/${GH_REPO}`, `${GH_PROJECT_ID}` from `roster.yaml` |

### 085 lifecycle simplification (folds into C-004)

Spec 085 (lifecycle simplification) is **not completed in VoidPay first** — it is ported and
fixed inside Conclave as part of C-004 module delivery. Known 085 cleanup items:

- `first-launch-protocol.md` — partially complete (marked `◐` in V1 diagram); candidate for
  archival once `session_init.py` handles first-launch detection.
- Contract size reduction: several contracts have grown past their advisory scope; C-004 trims
  them to the invariants that actually gate the lifecycle.
- Quorum references in contracts: Quorum does not exist in the Conclave base roster. All
  contract references to "Quorum" route to Forge (facilitation mode).

### No Quorum in base roster

VoidPay's Quorum (⚖️ Secretary) is absorbed into Forge's facilitation mode in Conclave. The
lifecycle skills must not assume Quorum is present. Specifically:

- `team.processing` Meeting mode: "Invoke `team.quorum`" → "Invoke Forge facilitation mode"
- `team.done` hot.md reconciliation: currently gated on "Quorum or current advisor is Quorum" — in
  Conclave, Forge is the gate.
- `team.start` step 4.5 wiki routing: Quorum row removed; Forge facilitation mode has its own entry.

### First-launch knowledge gap

The bootstrap research (R3) found that `hire` produces voice scaffolding and empty dirs but zero
project-knowledge files, and that `roster.yaml:context_path` named a `project-context.md` that
nothing created. Spec 103 W3 closed the second half: `/conclave:init` now writes the stub at the
DATA root, where `context_path` points. The first half stands — no shipped code reads `context_path`,
and an advisor loads project context only because a human put it in `CLAUDE.md`.
Originally filed as feedback item `it-1` in `fb-1781159734-e51973`.

---

## Lifecycle ritual summary

```
/team.start
  ├─ session_init.py (briefing build-and-compare)   ← constitution II
  ├─ resume check
  ├─ tier detection
  ├─ GH issue check (truth reconciliation)       ← constitution II
  └─ skill routing

/team.processing
  ├─ GH bind
  └─ mode → workflow skill dispatch

[work]

/team.done
  ├─ feedback_emit.py  (emission gate)           ← self-improvement loop entry
  ├─ artifact filing (decisions, mentions, session, handoff)
  ├─ mandatory checklist (commits, GH sync)      ← constitution III
  ├─ study phase (wiki health)
  ├─ lifecycle retrospective (5 lenses)          ← self-improvement loop signal
  └─ reflexion → close-session.sh               ← constitution III

/team.handoff  (if work is incomplete)
  └─ structured resume-prompt → ops/handoffs/
```

Skipping `start` = working from stale state (constitution II violated).
Skipping `done` = losing decisions and feedback (constitution III violated).
Neither skip is permitted. The ritual is what makes the memory trustworthy.

---
protocol: hire
version: 2.2.0
description: |
  Factory Protocol for creating new advisors from scratch. Interview-driven wizard.
  Invoked by team.forge router on "hire" / "create advisor" / "нанять" signals.
note: |
  This file is the baseline copy of legacy team.hire v2.0 (spec 049 rollout step 3).
  Mechanical changes (scripts, thin template, first-launch extraction) land in later tasks.
---

# team.hire — Advisor Factory

> Creates new C-level AI advisors with verified skills, proper memory structure, and Skill Protocol integration.
> Also upgrades existing advisors to current factory standards.

## When to Use

- Ignat says "hire", "нанять", "create advisor", "нужен CFO/COO/CPO/..."
- Upgrading existing advisor to factory v2 standards
- Advisor missing Skill Protocol or Toolbox

## Factory Protocol

### Phase 1: Discovery Interview

Ask Ignat via AskUserQuestion:

1. **Role**: What C-level title? (CTO, CMO, CFO, COO, CPO, CCO, CISO, ...)
2. **Name**: Preferred name? (or let factory suggest 3 options)
3. **Focus**: What domain problems should this advisor solve?
4. **Personality**: Tone preference? (analytical, creative, diplomatic, cold/precise, ...)
5. **Emoji**: Pick one, or let advisor choose during First Launch

### Phase 2: Skill Discovery (VERIFIED)

> **Critical**: Factory v1 allowed advisors to hallucinate skill names. This step uses Glob to verify every skill exists.

**Step 2a**: Search for relevant skills:
```
Skill(skill="find-skills", args="<domain keywords>")
```

**Step 2b — G1: BLOCKING phantom-skill pre-gate (spec 089, Cat12).** `engine skill verify` is a
**blocking pre-scaffold gate**, not advisory. Pass ALL candidate skills as arguments (batch
mode): it prints a `PHANTOM` line per missing skill and exits non-zero if ANY is absent. Passing
the list as argv avoids the shell word-splitting that made a hand-rolled per-name loop mangle
every entry after the first (feedback i2). If it exits non-zero, **ABORT the scaffold** — do not
run `engine advisor create`:
```
engine skill verify <candidate-skill-1> <candidate-skill-2> ... \
  || { echo "G1 FAIL — phantom skill(s); scaffold aborted"; exit 1; }
```
This is the same check audit.md Cat 12 enforces post-hoc; G1 moves it **before** Phase 3 so a
hire can never mint an agent that loads a non-existent skill.

**Step 2c**: Build verified Toolbox (only skills that pass Glob check).
Mark skills as:
- **Core** (daily use, listed in SKILL.md `## Skill Protocol`)
- **Reference** (occasional, loaded on demand)

> **Anti-pattern**: NEVER list a skill without verifying it exists via Glob/ls. This caused 13 phantom skills in factory v1.

## Phase 3 — Generate Files (deterministic script + LLM enrichment)

### 3a.0 — Tier branch (spec 089, D27) — advisor vs executor

Before scaffolding, branch on tier. The two tiers use **different persona templates** — an
executor has NO biographical voice well (its identity IS its behavioral contract, 2311.10054):

| Tier | Persona template | Schema | Validation gate |
|------|------------------|--------|-----------------|
| **advisor** | `templates/personality-template.md` (`applies-to: advisors`) | 4-axis voice well | §3a.5 (4 sections) |
| **executor** | `templates/executor-identity-card.md` (≤20 lines) | ROLE / SCOPE-BOUNDARY / INPUT- / OUTPUT-CONTRACT / BEHAVIORAL CONSTRAINTS / ANTI-PATTERNS / EXIT | §3a.6 (sentinel + ≤20 lines + rejection list) |

> **Never** fill an executor with a 4-axis well, and never give an advisor only an identity-card.
> The new 089 executors (scout/ranker/judge/critic) take the **executor** branch.

### 3a. Run the scaffold script

```bash
python -m engine advisor create \
  --id <id> --name <name> --role "<role>" \
  --color <color> --emoji <emoji> --tone "<tone>"
```

Mints a flat agent-def at `agents/<id>.md` with `name: <id>` (no `team.` prefix). Returns JSON `{"id": ..., "agent": ...}`.

### 3a.5 — Voice schema (4-axis) requirement

Every advisor `personality.md` MUST conform to the 4-axis voice schema:

1. **Domain Vocabulary** — 10-15 characteristic terms in **bold**
2. **Characteristic Questions** — 3 signature questions
3. **Analytical Framework** — paragraph describing reasoning approach
4. **Metaphor** — single-sentence domain metaphor

Use template: `skills/forge-operations/references/templates/personality-template.md`

**Rationale**: 4-axis schema absorbed from `personalities/persona-coordinator.md`
plugin (proven in production by `project-delivery/` agents). Enforces voice
differentiation by structure, not by luck.

**Grandfathered**: Existing 6 advisors (Kai/Nexus/Spark/Shade/Dev/Quorum) are
exempt; opt-in retroactive update via `/conclave:forge evolve` per advisor.

**Chosen-name uniqueness**: `chosen-name` must be unique per role suffix (e.g., `atlas-dev` and `atlas-test` are distinct executors and both allowed; a second `atlas-dev` would silently overwrite due to script idempotency — treat as an update, not a new hire). Cross-role collisions on the same `chosen-name` are permitted by design: the chosen-name is a personality marker, the role suffix is what specializes the executor.

**Validation**: post-scaffold, run:

```bash
grep -E "^## (Domain Vocabulary|Characteristic Questions|Analytical Framework|Metaphor)$" \
  .claude/skills/team.<id>/memory/personality.md | wc -l
# Expected: 4
```

Reject hire if validation count < 4. **(Advisor branch only — executors use §3a.6.)**

### 3a.6 — Executor identity-card validation (spec 089, D27 — executor branch)

For an **executor** hire, the persona file is `memory/personality.md` rendered from
`templates/executor-identity-card.md`. Validate:

```bash
card=.claude/skills/exec.<chosen-name>/memory/personality.md
# (1) the seven required headings, each present:
for h in ROLE SCOPE-BOUNDARY INPUT-CONTRACT OUTPUT-CONTRACT "BEHAVIORAL CONSTRAINTS" ANTI-PATTERNS EXIT; do
  grep -q "^$h" "$card" || { echo "MISSING: $h"; exit 1; }
done
# (2) the output sentinel line:
grep -q "<!-- exec:<chosen-name> v1 -->" "$card" || { echo "MISSING sentinel"; exit 1; }
# (3) ≤20 content lines (role-minimal, NO biographical well):
[[ $(grep -vcE '^\s*$|^#|^---' "$card") -le 20 ]] || { echo "card too long — D27 cap"; exit 1; }
# (4) NO advisor-well sections leaked in:
! grep -qE '^## (Domain Vocabulary|Metaphor|Voice signature|Background)$' "$card" \
  || { echo "executor must NOT carry the 4-axis well (D27)"; exit 1; }
```

Reject the executor hire if any check fails.

### 3a.7 — D19 incentive injector (spec 089 — `role: judge` only)

When the executor being hired is the **judge** (`role: judge` / chosen-name `themis`), inject the
D19 incentive phrase **verbatim** into its agent-def system prompt (audit Cat 13 verifies it is
present):

> "Rigorous rejection is the path of least resistance. A PASS that slips a broken artifact through
> causes 10× the rework of a FAIL that correctly stops it. Themis is never rewarded for speed or
> throughput. If in doubt, emit FAIL with MINOR findings rather than PASS with reservations."

Skip for non-judge executors. The phrase is load-bearing for AC14 (rejection = least-resistance)
and is checked by `audit.md` Cat 13.

### 3b. LLM enrichment (Edit calls on created files)

- `SKILL.md ## Scope` — boundaries computed via discovery of existing advisors
- `SKILL.md ## Domain Chains` — role-specific chain from Phase 2 Toolbox
- `personality.md` — filled from Discovery Interview hints (philosophy, tone)

## Hire-time memory scaffolding

Create in `.claude/skills/team.<advisor>/memory/`:
- `personality.md` — from `templates/personality.md` (customize via aspects)
- `references/` — empty directory; references added later via `forge evolve aspects/references.md`

Do NOT create: `BRIEFING.md`, `topics/*`, any dynamic-state files. These are shared, managed by scripts under `.ai/agent-memory/advisors/`.

## Post-hire step

**Do not** run `engine briefing build` now. The scaffold left the briefing holding the
`AWAITING_FIRST_LAUNCH` sentinel; `/conclave:start` triggers the First Launch protocol
**only** while that sentinel is present. Building the briefing here overwrites the stub and
silently skips the advisor's First Launch. The first real briefing is produced by First
Launch step 6 (`python -m engine briefing build`), after the advisor's first session closes
— see `${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/first-launch-protocol.md`.

### 3c. Stamp `forge:` versions

```bash
python -m engine model bump --advisor <id> --set-all
```

## Phase 4 — Register (discovery-driven)

```bash
python -m engine register advisor --dry-run
```

Review the diff. Apply edits to `.claude/CLAUDE.md` and `team.quorum/SKILL.md` via the Edit tool (diff-preview + AskUserQuestion per forge invariant #1 and #2).

`engine register advisor` globs all agents and skills; never hardcodes advisor lists.

## Phase 5 — First Launch Delegation

Tell user: "Run `/conclave-<id>` then `/conclave:start`."

First Launch logic lives in `${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/first-launch-protocol.md`.
`team.start` detects `AWAITING_FIRST_LAUNCH` and executes the bootstrap inline.
Hire does not run first-launch itself.

---

## Templates

Inline templates removed in v2.2.0 — now live in `skills/forge-operations/references/templates/`:

| Template | Path |
|----------|------|
| SKILL.md | `templates/skill-frontmatter.md` |
| personality.md | `templates/personality.md` |
| agent frontmatter | `templates/agent-frontmatter.md` |

`engine advisor create` copies and substitutes these automatically (Phase 3a).

---

## Upgrade Protocol

For existing advisors missing factory v2 features, run:

```bash
engine audit registry-consistency
```

Fix gaps reported by the audit script. Key compliance checks: Skill Protocol section, verified Toolbox, agent frontmatter, Quorum registry entry.

---

## Anti-Patterns

| Pattern | Why Bad | Fix |
|---------|---------|-----|
| Listing skills without Glob verification | Phantom skills (13 found in factory v1) | Always `ls` before adding |
| No Skill Protocol section | Advisor doesn't know which skills to use | Add from template |
| Skipping Quorum registration | Advisor invisible in meetings | Add to Advisor Registry |
| Creating advisor without AskUserQuestion | May not match Ignat's needs | Always Discovery Interview first |
| Agent without frontmatter file | Can't be used as quick-dispatch agent | Create `agents/team.*.md` |

---

## Color Palette (taken)

| Advisor | Color | Hex |
|---------|-------|-----|
| Kai (CTO) | cyan | #0EA5E9 |
| Nexus (CEO) | indigo | #6366F1 |
| Spark (CMO) | orange | #FF6B2B |
| Vox (CCO) | sage | #7C9E87 |
| Shade (CISO) | red | #DC2626 |
| Quorum (Secretary) | — | — |

Available: emerald, amber, violet, pink, teal, rose, lime, fuchsia

---

## Protocol changelog

### 2.3.0 — spec 089 executor path
- Phase 2 Step 2b: `verify-skill.sh` is now a **blocking** pre-scaffold gate (G1 / Cat12), not advisory.
- Phase 3a.0: tier branch — advisor → `personality-template.md` (4-axis); executor → `executor-identity-card.md` (≤20 lines, no well, D27).
- Phase 3a.6: executor identity-card validation gate (7 headings + sentinel + ≤20 lines + no-well).
- Phase 3a.7: D19 incentive injector for `role: judge` (verbatim phrase; audit Cat13 checks presence).

### 2.2.0 — spec 049 rollout
- Phase 3 uses `engine advisor create` (one call vs N Write calls)
- Phase 4 uses `engine register advisor` (discovery-driven registry rebuild)
- Phase 5 delegates First Launch to `first-launch-protocol` contract
- Phase 2 uses `engine skill verify` (reject phantoms)
- Templates now include `personality.md` skeleton (required aspect since model 1.2.0)

### 2.0.0 — baseline
- Copied from legacy `team.hire` skill.

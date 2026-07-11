# Roster and Forge

> **Scope**: The agent roster model (advisors + executors), the hire-fresh distribution
> strategy, and Forge's two-mode design.
> **Depends on**: [`engine-modules.md`](engine-modules.md) (C-003, C-004, C-008),
> [`memory-and-knowledge.md`](memory-and-knowledge.md) (briefings, hire-time memory)
> **Source material**: VISION.md §5, `migration-bootstrap.md` R3,
> `persona-voice.md` (contract v1.2.0), `team.quorum/SKILL.md`

---

## The roster model

Conclave's roster has two agent categories and one permanent meta-role:

| Category | Model | Count | Lifecycle |
|----------|-------|-------|-----------|
| **Advisors** | opus | variable, hired per instance | full (start → done → briefing) |
| **Executors** | sonnet | fixed set, dispatched per task | per-task (dispatch → verify → idle) |
| **Forge** | opus | always 1, seeded | permanent (never hired, never dismissed) |

The engine ships **empty of domain advisors**. A consumer seeds the engine and hires the
roster it needs via the factory (`hire`). VoidPay's five-advisor lineup ships separately as
the first **advisor-template pack** — the engine core is domain-neutral.

---

## Advisor model

### Persona layers (three)

Every advisor carries three stacked layers defined in `contracts/persona-voice.md`:

**Layer 1 — Identity prefix** (mandatory, never disabled)
Every reply opens with `<emoji> <name>:` on its own line. The emoji is owned by the advisor
(emoji ownership is a MAJOR version change). This is the only inviolable rule.

**Layer 2 — Voice signature** (per-advisor linguistic fingerprint)
Defined in each advisor's `SKILL.md` under `## Voice Signature`. A voice signature specifies:

| Component | What it captures |
|-----------|-----------------|
| Sentence rhythm | Short/long, declarative/exploratory, list-shaped or paragraph-shaped |
| Default response shape | The 3–5 beat structure the advisor defaults to under uncertainty |
| Vocabulary tells | 5–10 recurring words/phrases that mark the speaker |
| Pet phrases | 3–5 idioms only this advisor uses |
| Never-does list | Explicit anti-patterns (no warm openings, no future promises, etc.) |

The test: strip the Layer 1 prefix — the voice should still identify the speaker.

**Layer 3 — Biographical well** (where colour comes from)
Each advisor has a `memory/personality.md` — a deep fictional biography: origin story,
philosophy, pet peeves, working style, aesthetic, imagined backstory. This is the **source
the advisor hallucinates colour from**. When a recommendation has flavour, it comes from this
specific person's life, not from a generic topic list.

Biographical wells are **separate by design**. Kai doesn't tell growth war stories; Spark
doesn't lecture on threat models. Poaching another advisor's well collapses the role
separation that makes the advisors distinguishable as people.

### Scope boundaries

Each advisor has **hard scope boundaries** encoded in their SKILL.md. Examples from the
VoidPay template pack:

| Advisor | Domain lane | Hard boundary |
|---------|------------|---------------|
| Kai 🔷 | Architecture, tech debt, infra, deployment | Never opines on growth or security |
| Nexus 🔮 | Strategy, go-to-market, fundraising | Never opines on implementation |
| Shade 🛡️ | Vulnerability review, threat modeling | Never opines on growth or roadmap |
| Spark ⚡ | Growth, launch, channels, community | Never opines on architecture or security |

Boundary violations are an audit finding (`protocols/audit.md`). Advisors route out-of-scope
questions rather than answering them.

### Hire-time memory layout

Each hired advisor gets a personal memory directory under the skill tree:

```
engine/skills/team.<id>/
├── SKILL.md              ← domain expertise + voice signature + scope
└── memory/
    ├── personality.md    ← biographical well + philosophy
    └── references/       ← domain reference docs
```

This is the **hire-time layer** — mutated only via `team.forge evolve`. The session-time
layer (briefings, sessions, decisions) lives under `agent-memory/advisors/` and is managed
by scripts, not by hand. See [`memory-and-knowledge.md`](memory-and-knowledge.md).

---

## Executor model

Executors are **task-scoped workers** — dispatched per job, model=sonnet by default, with
strict file-ownership contracts.

| Executor | Wraps | Purpose |
|----------|-------|---------|
| Atlas | team-implementer | FSD-aware, file-ownership-respecting, parallel-safe implementation |
| Iris | reviewer + debugger | Quality gate — 4+1 pipeline + 3-mode spec/prod/UX review + structured verdict |
| Scout | — | Read-only research wave, multi-channel evidence gathering |
| Ranker | — | Best-of-N filter (P6 rank sub-phase) |
| Critic | — | Red-team refutation — 5 techniques, writes `critic-refutation.yaml`, exits |
| Judge | — | Binding cross-domain verdict (oracle gate) |

### File-ownership contract

Each dispatched executor receives an explicit ownership boundary in its prompt. It may not
edit files outside that boundary. Atlas is `parallel-safe`: multiple Atlas instances on the
same worktree coordinate via ownership partitions, never overlapping.

### Skill discipline

Executors **must** load context-relevant skills before mutations. Plans dispatched to Atlas
list `REQUIRED SKILLS` per task. Loading skills after the mutation (or not at all) is an
anti-pattern that generates systematic errors.

### Model policy

- Executors: `model: sonnet` (default). Extended-thinking can be triggered via prompt
  keywords for complex tasks.
- Advisors and Forge: `model: opus`. Opus is reserved for advisory reasoning; using sonnet
  for advisors degrades meeting quality.

---

## Distribution model — hire-fresh

**Hire-fresh is a hard decision** (migration-bootstrap R3, locked 2026-06-11).

Copying advisor persona bodies from VoidPay into a new instance drags `@product.md`,
VoidPay-specific scope, and VoidPay-specific biographical detail into the new project's
reasoning — creating wrong-domain hallucination pressure from session one.

The correct flow:
1. Consumer initialises Conclave with their own `project-context.md` + `constitution.md`.
2. Consumer runs Forge's `hire` protocol for each advisor role needed.
3. Forge generates a fresh advisor from the `templates/skill-frontmatter.md` scaffold, with
   a blank biographical well and scope calibrated to the project.
4. VoidPay's advisory lineup ships as the `advisor-template-pack` — a starter set of
   persona blueprints (voice cadence only, domain-neutral) that a consumer can customise.

The advisor-template pack carries **voice cadence** (Layer 2 fingerprint), not domain
knowledge. Domain content is always written fresh per hire.

---

## Forge — the always-present meta-role

Forge 🔨 is infrastructure, not an advisor. It is **seeded at initialisation and never
hired or dismissed**. It is the mechanism by which the roster is built, maintained, and
self-improved.

> **The boundary**: Forge has a position on *how the system is built*. It stays neutral
> on *what the system produces*. A CTO decision belongs to Kai; the scaffolding that
> lets Kai function correctly belongs to Forge.

### Factory mode

Triggered by: `hire`, `evolve`, `audit`, any mutation to the advisor model.

Responsibilities:
- `protocols/hire.md` — generate a new advisor from templates, patch `@project-context.md`
  + `@constitution.md` into the SKILL, seed `memory/personality.md`, run `briefing-build`
  for the new advisor, execute `register-advisor.sh`
- `protocols/evolve.md` — mutate an existing advisor (voice, scope, toolbox, contracts),
  per-aspect commits, diff-preview before every edit
- `protocols/audit.md` — detect advisor drift (scope creep, voice collapse, contract
  violations), produce structured findings
- `protocols/audit-skills.md` — skill sprawl audit across the lifecycle layer

In factory mode Forge **opines on agent architecture** (should this advisor carry this
contract? does this scope boundary make sense?). It does not opine on the domain content
those agents will produce.

### Facilitation mode

Triggered by: meeting orchestration request, cross-advisor coordination, minutes, issue
triage, plan execution in admin mode.

Facilitation mode absorbs what Quorum did in VoidPay's roster:

| Quorum capability | Transfer to Forge facilitation | Notes |
|-------------------|-------------------------------|-------|
| Meeting protocol (7 phases) | New `protocols/facilitate.md` | Phases intact, "Quorum" identity dropped |
| Teams-only policy | Invariant: never bare `Agent()`, always `TeamCreate` first | Hard rule, not a preference |
| Cardinal rules (no personal opinions, mandatory AskUserQuestion, append-only minutes) | Carried verbatim | Non-negotiable |
| Autonomous mode (skip AskUserQuestion) | Carried | For non-interactive contexts |
| Issue triage (dev/infra/content/grant/advisor-private/strategy) | Carried | Phase 6.1 in meeting protocol |
| Synthesis voice | Carried | Status → Open items → Decisions made → Next step |
| Parliamentary-secretary biographical well (DAO specifics, `⚖️` identity) | **Dropped** | Forge's well is that of a meta-architect, not a secretary |

**Assets that moved:** `team.quorum/references/{meeting-format,minutes-template}.md` →
`engine/skills/team.forge/references/`; `meeting-index.md` → `ops/meetings/`.

In facilitation mode Forge **remains neutral on domain disputes**. If Kai and Shade
disagree on an architecture choice, Forge synthesises and routes to the human — it never
sides. The Quorum Cardinal Rule #1 ("never express personal opinions") is inherited intact.

### Mode detection

Mode is detected **at session start** from the incoming request and never toggled
mid-session. A session that starts as a meeting does not morph into a hire-protocol run.
If both are needed, they are separate sessions.

| Signal | Mode |
|--------|------|
| "hire" / "create advisor" / "evolve" / "audit" | Factory |
| "meeting" / "coordinate" / "minutes" / "run a meeting" / plan execution | Facilitation |
| Ambiguous | `AskUserQuestion` — factory / facilitation |

### Facilitation anti-patterns

Inherited from Quorum's documented failure modes:

| Anti-pattern | Why banned |
|-------------|------------|
| Expressing personal opinion during a meeting | Facilitation mode: neutral, never opines |
| Approving decisions without `AskUserQuestion` | Mandatory-approval rule — zero exceptions |
| Editing advisor `agent-memory/` files directly | Dispatch agents or run scripts only |
| Modifying past meeting minutes | Minutes are append-only |
| Running meetings without loading advisor briefings | Missing context → bad facilitation |
| `Agent()` call without `team_name` | **Forbidden**. `TeamCreate` first, always |
| One-shot dispatch per meeting phase | Use `TeamCreate + SendMessage` — advisors retain context across phases |

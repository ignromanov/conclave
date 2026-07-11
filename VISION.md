# Conclave — Vision

> **One-liner**: A portable operating system for a **self-improving multi-agent advisory team** —
> personas with a lifecycle, a shared memory, and a feedback loop that **closes its own items
> and rewrites its own agents**.
>
> **Status**: **founding vision capture · 2026-06-11 · PRE-CORRECTION.** This document records the
> original intent. It was **not** swept by the 2026-06-11 research-correction pass — where it
> conflicts with `docs/architecture/` or `docs/product/`, **those corrected docs win** (e.g. the
> loop does not yet "ship"/"close its own items" — C-006 is complete-but-starved; v1 learning is
> L1 human-gated only; nominations rewire to L1, not 090; live index = 339 rows / 18 open). It is
> no longer the canonical mechanism definition — it is the founding capture.
> **Relationship**: VoidPay (`~/code/vl/`) is the *proving ground*, not the parent. Conclave is its own project.

---

## 1. What Conclave is

Conclave is the engine that runs a **team of AI advisors and executors** as a coherent organization:

- **Advisors** — persona-driven roles (CEO, CTO, CISO, CMO, Secretary) that opine, decide, and route,
  each with a distinct voice signature, memory, and scope boundary.
- **Executors** — task-scoped workers (implementer, quality-gate, scout, ranker, critic, judge) dispatched
  per job, with strict file-ownership and skill discipline.
- **A lifecycle** — every session begins, processes, and ends through the same mandatory ritual
  (`start → processing → work → done → handoff`), so work never drifts from its record.
- **A memory** — auto-generated briefings (a cache) sitting over an append-only source of truth
  (issues, decisions, sessions, mentions), so agents resume with full context and nothing is lost.
- **A self-improving feedback loop** — the differentiator (§3). The team observes its own mistakes,
  closes the ones already fixed, and promotes the recurring ones into durable changes to its own
  skills and contracts.

The thesis: most "multi-agent" systems are orchestration. Conclave is **governance + learning** —
the part that makes a team of agents get *better* over time instead of merely *busier*.

---

## 2. Why it deserves its own project

Three forces converged:

1. **The roster engine was always designed to spin out.** Spec 091 (deontic duty model) states plainly:
   *"the whole `roster/` engine is built to spin out as a standalone product (Track B)."*
2. **The "productize-the-team" vision recurs.** It surfaced ≥7 times in feedback as a high-severity idea:
   *"внедрить в наш /team.forge обратную связь… сделать её активной → система могла сама себя чинить →
   Voyager-style lifelong skill mutation → агенты сами исправляли свои ошибки."*
3. **Separate context is now a constraint, not a luxury.** The agent system has grown to a scale where
   it competes for context budget with the product it serves. It needs its own home, its own CLAUDE.md,
   and its own roadmap.

Conclave is that home. VoidPay keeps dogfooding the system; Conclave owns the design, the extraction
plan, and the productization path.

---

## 3. The full loop (the differentiator)

```
                          ┌──────────────────────────────────────────────┐
                          │                                              ▼
  emit ──► index ──► triage ──► VERIFY ──► { auto-close | propose | nominate } ──► forge-evolve
 (per     (jsonl)   (weekly   (NEW:        │            │            │              (mutate skill/
  session)          cadence)  hybrid       │            │            │               contract,
                              check)       ▼            ▼            ▼               human-gated)
                                        resolved+    approval     nominations/          │
                                        archived     digest       queue                 ▼
                                        (drains      (Quorum      (→ 090 L2/L3     lesson distilled
                                         backlog)    batch-ok)     consumes)       → briefing inject
                                                                                   → better next agent
                                                                                        │
                                                                                        ▼
                                                              089 oracle falsifies wrong lessons
                                                              (demote, never silent-delete)
```

**Two outputs from one verification signal:**

- **Closing loop** (ships now, cheap signal): "did the world change to match this feedback?"
  → yes for a single item → **close it** (drain `accepted → resolved → archived`).
- **Learning loop** (heavier, oracle-gated): same pattern recurs and *holds* under the external signal
  → **nominate a durable mutation** to a skill/contract/briefing → agent self-rewrites.

The closing loop attacks a concrete, measured failure: **71 `accepted` items vs only 21 `resolved`**
in the live 339-row index (2026-06-11) — accepted work isn't closing because the only path to
`resolved` is a manual `--set`. Much of that 71 is *already fixed on disk*, never marked. The loop
automates the "verify-before-fold" pass a human does by hand.

---

## 4. Module map (current implementation lives in VoidPay's `.ai/`, extraction target = Conclave)

| Module | Spec | What it owns | Status |
|--------|------|-------------|--------|
| **Notebook** | 086 | emit → index → weekly triage → archive (`/team.feedback`, `/team.feedback-triage`) | done |
| **Briefings** | 084 | auto-generated per-advisor briefing cache + ≤500-word eager lesson injection slot | done |
| **Forge** | 049 | agent factory — hire / evolve / audit; applies promoted lessons to SKILL.md/contracts | done |
| **Lifecycle** | 085 | `team.start / processing / done / handoff` — the mandatory session ritual | done |
| **Memory** | 051 | briefings (cache) + sessions / decisions / mentions (source) + GH issues (truth) | done |
| **Oracle** | 089 | autonomous pipeline + external verifier/verdict signal (the falsification signal) | in progress |
| **Roster / Duties** | 091 | deontic duty registry + **L1** learning (reflexion → human-approved norm-diff → self-write); the spin-out unit | design-locked |
| **Learning L2/L3** | 090 | oracle-falsified auto-acquisition of lessons (importance-threshold reflection + auto-extract) | stub (blocked on 089+091) |
| **Closing loop** | **093** | **unified verify/close loop — drains backlog + produces nominations** | **proposed (this session)** |

The dependency-weight split is deliberate and worth preserving in Conclave:
- **Cheap, ships now**: notebook (086), closing loop (093), L1 human-gated learning (091).
- **Heavy, needs external signal**: L2/L3 auto-acquisition (090) — gated on the oracle (089).
  The science is unambiguous: durable self-improvement requires an external verifier; intrinsic
  self-correction degrades. Conclave must never promote a lesson without an external signal.

---

## 5. The agents (the team)

Conclave ships **one always-present meta-role**; the domain roster is **hired fresh per project**.

**Always present** (seeded, never hired, `model: opus`):

| Agent | Emoji | Role |
|-------|-------|------|
| Forge | 🔨 | The meta-role. **Factory mode** — hires / evolves / audits the team itself. **Facilitation mode** — runs meetings, records minutes, routes cross-advisor work, gates approvals. Opines on *how the system is built*; stays neutral on *what it produces*. |

The former dedicated Secretary (Quorum ⚖️) is **absorbed into Forge's facilitation mode** in the
base roster — one meta-role owns both the factory and the chair. Mode is detected at session start.

**Domain advisors** (full lifecycle, persona-driven, `model: opus`) are **hired fresh** for each
instance via the factory. VoidPay's reference roster — Kai 🔷 (CTO), Nexus 🔮 (CEO), Spark ⚡ (CMO),
Shade 🛡️ (CISO) — ships separately as the first **advisor-template pack**, not baked into the engine.

**Executors** (task-scoped, dispatched per job, `model: sonnet`):

| Agent | Wraps | Purpose |
|-------|-------|---------|
| Atlas | implementer | file-ownership-respecting, parallel-safe implementation (stack-profile config: fsd/generic/nextjs) |
| Iris | reviewer + debugger | quality gate (pipeline + 3-mode spec/prod/UX review + structured verdict) |
| Scout · Ranker · Critic · Judge | 089 pipeline | research · best-of-N filter · red-team refutation · binding verdict |

Each persona carries a **voice signature** (sentence rhythm, vocabulary tells, pet phrases, a
biographical "well" to hallucinate colour from) and **hard scope boundaries** (a CISO never opines
on growth; Forge never sides on a domain dispute). Personas are not decoration — they are the
mechanism that keeps roles from collapsing into one undifferentiated assistant.

> Roster, persona, and the Forge two-mode design: `docs/architecture/roster-and-forge.md`.

---

## 6. Architecture principles (carry these into Conclave)

1. **File-as-message-bus.** LLMs write per-template files; scripts aggregate frontmatter. No live
   `gh`/`git` calls outside dedicated snapshot writers. The bus is auditable and replayable.
2. **Cache over source of truth.** Briefings are a regenerable dashboard; GH issues + append-only
   decisions/sessions are truth. When they conflict, truth wins, cache rebuilds.
3. **Mandatory lifecycle.** No session skips `start`/`done`. Skipping `done` = drift. The ritual is
   what makes the memory trustworthy.
4. **Spec-driven work.** brainstorm → spec → plan → build (subagent-driven) → review → done. Every
   structural change traces to a spec.
5. **Confidence-graduated authority.** Deterministic signal → auto-act; fuzzy signal → propose for
   human approval; high-stakes mutation (skill/contract edit) → always human-gated.
6. **Never silent-delete.** Wrong lessons and wrongly-closed items are demoted/re-opened with a
   reversal path (`re-occurred`), never erased. Provenance on every automated action.
7. **Guardrails as first-class.** Memory-poisoning (provenance + rerank), lesson-bloat (cap +
   Ebbinghaus decay: 30d unreinforced → step down), local-minima (re-occurred → lesson-failed →
   revise/retire), scope per-task-type.

---

## 7. Productization path (Track B)

Conclave's long arc, from internal engine to adoptable framework:

1. **Capture** (now) — this vision + architecture, separate context, separate repo.
2. **Extract** — lift the lifecycle + feedback + roster engine out of VoidPay's `.ai/` into Conclave
   as the canonical home (codec precedent 056: build in-place, extract at maturity).
3. **Generalize** — strip VoidPay-specific assumptions (FSD, the specific 5-advisor roster, the dual-repo
   git dance) behind config; the engine should run any roster on any project.
4. **Package** — a way for others to adopt: a template, a CLI, or a plugin that scaffolds a roster +
   lifecycle + self-improving loop into their own repo.
5. **Self-host the loop** — Conclave should dogfood its *own* self-improvement loop on *itself*.

Open question for later brainstorming: what is the **minimal adoptable unit**? (a) the persona +
lifecycle skeleton, (b) the feedback + self-improvement loop, or (c) the whole roster. Each is a
different product.

---

## 8. First concrete step — Spec 093

The closing loop is the smallest shippable slice that proves the thesis and pays for itself
immediately (drains the 71-item accepted backlog). It is specced in `docs/specs/093-self-healing-feedback-loop.md`
(dogfooded in VoidPay, where the feedback scripts live), and tracked here as Conclave's component-zero.

See `docs/specs/093-self-healing-feedback-loop.md` for the design.

---

## 9. Provenance

This vision was distilled in a single Quorum session (2026-06-11) while the full VoidPay agent-system
canon was in context: specs 086 / 089 / 090 / 091 / 049 / 084 / 085 / 051, the live feedback index
(re-measured 2026-06-11 = 339 rows, 18 open; the "321 / 29" figure cited at capture time was superseded),
and the lifecycle skills. The trigger was a feedback-triage cadence that surfaced
the closing-loop gap and the recurring productize-the-team idea. Decisions are recorded in the
session's minutes under VoidPay `.ai/ops/`.

# Conclave — Capability Catalog

> **Scope**: What the system does end-to-end, from an operator view. For each capability:
> what it does, which module/skill provides it, how it is invoked.
> Implementation detail (script counts, maturity) → [`docs/implementation.md`](../implementation.md).
> Architecture breakdown → [`architecture/engine-modules.md`](architecture/engine-modules.md).

---

## 1. Run a Session (Lifecycle)

**What it does:** Enforces a mandatory open/close ritual for every advisor session. Without
the ritual, GH issues drift, session artifacts go unfiled, and knowledge is lost. With it,
every session produces a machine-readable record, briefings stay current, and reflexion
sentences feed the next session as priors.

**Module:** C-004 Lifecycle
**Skills:** `team.start` → `team.processing` → [work] → `team.done` → `team.handoff` (conditional)

**Invocation:**

```
/team.start
```

1. Runs `lifecycle/session_init.py --advisor <advisor>` in a single call. Orchestrates: GH
   snapshot (TTL=900s from `gh-cache/`; no live calls from briefing), briefing mtime-guard
   (>24h triggers `briefing/regen.py`), resume scan (`ops/handoffs/*-<advisor>-*.md`),
   reflexion extract (last 3 session frontmatter `reflexion:` fields injected as priors),
   overlay scan, feedback cadence check.
2. Reads `agent-memory/advisors/briefings/<advisor>.md` + `agent-memory/hot.md` into context.
3. Detects tier (Quick / Feature / Epic), presents the ▍-framed session-start block,
   confirms via `AskUserQuestion`.

```
/team.processing
```

Mode detection, skill chain routing (e.g. brainstorming → writing-plans → workflow.dev-lifecycle
for a feature; systematic-debugging for a bug fix). Creates TaskList entries including
`/team.done` as the final mandatory task.

```
/team.done
```

Phases in execution order:

| Phase | What happens |
|-------|-------------|
| Feedback emission | `feedback_emit.py` scaffolds review; agent fills `items[]`; `--finalize` validates + flips `_draft: false`; emission gate (`emission-gate.sh`) blocks if missing |
| Study | `study_phase.py`: 6-step wiki graduation (capture-suggest → promote-decision → bridge-rebuild → audit-stale → hot-sync → link-check); P0 exit blocks `close-session.sh` |
| Infra | `runlog-summary.sh`: surfaces script exit codes from `run-log/`; row omitted if all clean |
| Lifecycle Retrospective | 5 lenses (broke / unexpected / script-improvement / automation / context-reduction); findings filed as `/team.feedback` items; cap 5 per session |
| Reflexion | One sentence ≤280 chars; persisted to `session.md` frontmatter; read back for 3 sessions |
| hot.md reconciliation | Resolve `[!contradiction]` markers (Quorum/Forge only, to avoid race conditions) |
| `close-session.sh` | Files session record + decisions + mentions + optional handoff; single aggregate commit to `agent-memory/advisors/` + `ops/handoffs/` |

```
/team.handoff    # conditional — when session incomplete
```

Creates structured `ops/handoffs/YYYY-MM-DD-<advisor>-<slug>.md` with skill chain, current
state, and next action. Picked up by `session_init.py` resume scan on next open.

---

## 2. Hire / Evolve / Audit an Advisor (Forge)

**What it does:** Factory operations for the advisor model. Hire creates a new advisor from
template; evolve mutates one aspect (voice, responsibilities, toolbox, model-version, overlay,
contract); audit detects drift between SKILL.md, agent.md, briefing, and contracts.

**Module:** C-003 Forge
**Skill:** `team.forge` (router → protocol file on demand; never loads all three at once)

**Invocation:**

```
/team.forge
```

Signal routing:

| Signal | Protocol | Key scripts |
|--------|----------|------------|
| "hire" / "create advisor" / "нанять" | `protocols/hire.md` | `create-advisor.sh`, `register-advisor.sh` |
| Mutation phrase for existing advisor | `protocols/evolve.md` | `apply-overlay.sh`, `bump-model-version.sh`, per-aspect scripts |
| "audit" / "check drift" | `protocols/audit.md` | `audit-agent-configs.sh`, `audit-overlays.sh`, `audit-versions.sh` |
| "audit skills" / skill sprawl | `protocols/audit-skills.md` | `audit-skills.sh`, `audit-phantom-skills.sh`, `skill-stocktake.sh` |
| Ambiguous | `AskUserQuestion` | — |

Shared invariants across all protocols: diff-preview before every Edit; `AskUserQuestion` at
every commit boundary; per-aspect commits to `.ai/`; no `--force`, no `--no-verify`.

Forge's facilitation mode (Conclave base, absorbed from Quorum): meeting convene, agenda,
turn-taking, minutes filing, cross-advisor routing. Mode is detected at session start and
never toggled mid-session.

---

## 3. Run a Meeting (Facilitation)

**What it does:** Convenes a structured multi-advisor discussion. Handles agenda, turn-taking,
synthesis, and files machine-readable minutes. Supports autonomous mode (Forge runs the full
agenda; user reads minutes asynchronously).

**Module:** C-003 Forge (facilitation mode) / `team.quorum` (reference instance)
**Skill:** `team.quorum` in the reference instance; Forge facilitation protocol in Conclave

**Invocation:**

```
/team.quorum   # reference instance
```

1. Loads all 5 advisor briefings into context for cross-advisor synthesis.
2. Sets agenda from user prompt or open GH issues.
3. Routes turns by advisor lane; Quorum stays neutral on domain (never opines).
4. Files `ops/meetings/YYYY-MM-DD-<slug>.md` (minutes).
5. Sends cross-advisor mentions via `mention.sh --from quorum --to <advisor>`.
6. Resolves `[!contradiction]` markers in `hot.md` at close.

Autonomous mode: Quorum runs agenda, files minutes, sends mentions — user reads results
without round-trips. Invoked: `"Run a team meeting about X, I'll read the minutes later"`.

---

## 4. Dispatch an Executor

**What it does:** Spawns a bounded task worker — implementation, testing, research, ranking,
red-teaming, or verdict — with strict file-ownership and skill discipline. Advisors never
implement code directly; they dispatch Atlas. Advisors never run tests; they dispatch Iris.

**Module:** Executor layer
**Skills:** `exec.atlas-dev`, `exec.iris-test`, `exec.scout`, `exec.ranker`, `exec.critic`, `exec.judge`

### Atlas (implementation)

Dispatched when a spec is locked and code placement is needed.

```python
TeamCreate(team_name="atlas-<task-slug>")
Agent(team_name=..., name="atlas", subagent_type="exec.atlas-dev",
      model="opus", prompt=task_brief)
```

Required input: `candidate_id`, `file_ownership` (explicit paths Atlas may mutate),
`do_nots[]`, `ac_contract_ref` (path to acceptance criteria). Vague briefs without
`file_ownership` → Atlas emits `inconclusive + stall_reason` and stalls rather than guessing.
Commits: named files only — never `git add -A`.

### Iris (quality gate)

Dispatched to validate an implementation, run the test pipeline, or review against spec/prod/mobile.

```python
TeamCreate(team_name="iris-<task-slug>")
Agent(team_name=..., name="iris", subagent_type="exec.iris-test",
      model="opus", prompt=task_brief)
```

Auto-detects mode from dispatch keywords:

| Keyword | Mode | What runs |
|---------|------|-----------|
| "DoD" / "spec acceptance" / "conformance" | v1 | Spec-conformance review |
| "production screenshot" / "parity" / "live render" | v2 | v1 + production visual baseline comparison |
| "mobile" / "UX" / "phone" / "accessibility" / "HIG" | v3 | Mobile-UX standards review (WCAG / HIG / Material) |
| "lint" / "type-check" / "tests" / "build" / "coverage" | pipeline | 4+1 pipeline; structured YAML verdict |

Override with explicit `--mode v1|v2|v3|pipeline|all`. Iris is also the deterministic floor
in the P6 oracle pipeline (produces `oracle-signal.yaml` for Judge to consume).

### Oracle pipeline executors

Dispatched in sequence by the autonomous pipeline (P1–P6 spine):

```python
# P1 research wave
Agent(subagent_type="exec.scout", prompt=research_brief)
# → ranked cited options + scope_questions[]

# P6 rank sub-phase (N>1 candidates)
Agent(subagent_type="exec.ranker", prompt=rank_brief)
# → rank-<slug>-<ts>.yaml

# P6 concurrent branch (run in parallel)
Agent(subagent_type="exec.critic", prompt=critic_brief)
# → critic-refutation.yaml (one-way; Socra exits after writing)
# Iris dispatched as deterministic floor
# → oracle-signal.yaml

# P6 verdict (after floor + critic seals)
Agent(subagent_type="exec.judge", prompt=verdict_brief)
# → verdict-<slug>.yaml
```

Judge constraint D18.1: the same model-run that generated an artifact cannot judge it —
producer ≠ evaluator is a hard invariant.

---

## 5. Feedback Cadence (emit → triage → archive)

**What it does:** Structured end-of-session signal capture and weekly dedup/triage pipeline.
Creates a machine-readable record of every agent's friction and ideas; routes accepted items
to GH issues; archives resolved reviews. This is the Notebook module (C-001).

**Module:** C-001 Notebook
**Skills:** `team.feedback` (emit), `team.feedback-triage` (cadence)

### Emit (mandatory, every session end)

Every agent emits exactly one review per session. Invoked by `/team.done` — or directly:

```bash
uv run --project .claude/skills/team.forge/scripts/feedback \
  python .claude/skills/team.forge/scripts/feedback/feedback_emit.py \
  --agent <slug> --agent-type advisor|executor|other \
  --session-ref <id> --skill-version sha256:<12hex>
# fill items[] in scaffolded file, then finalize:
feedback_emit.py --finalize ops/feedback/<today>/<file>.md
```

Schema enforces: `items[]` cap 3–5; `evidence` mandatory on every item (restatements
rejected); closed enums for `category`, `layer`, `frequency`. `_draft: false` set only by
`--finalize` after schema validation passes. Files skipped by aggregator while `_draft: true`.

### Triage (weekly cadence)

Triggered by `session_init.py` when `now − last_triage > 7 days` OR new reviews ≥ 15:

```bash
python .claude/skills/team.forge/scripts/feedback/feedback_triage.py --digest
```

Five-step pipeline:

1. **Validation gate** — schema-invalid `_draft:false` reviews abort triage immediately.
2. **Dedup digest** — fingerprint dedup; duplicates increment `hit_count`.
3. **Cluster classify** — group by category/layer; surface high-`hit_count` clusters.
4. **Status-write** — set `status: accepted | rejected | deferred` on each review file.
5. **GH issues + archive** — open GH issue per `accepted` item; archive `resolved` reviews.

---

## 6. Self-Healing Closing Loop (093)

**What it does:** Automates the gap between `accepted` and `resolved`. The live reference-instance index
(2026-06-11, 339 rows) shows **71 `accepted` vs 21 `resolved`** — accepted work isn't closing
because the only path to `resolved` is a manual `--set`. Much of that 71 is already fixed on
disk, never marked. The closing loop automates the verify-before-fold pass.

**Module:** C-006 Closing Loop
**Script:** `feedback_verify.py` (~150 LOC, **complete but starved** — active spec 093). The
code exists; what's missing is *inputs*: no `verify:` predicates are authored and `hit_count`
is never written, so on live data it yields 0 auto-closes and 0 nominations. The migration
task is to **feed** it (author predicates, wire `hit_count`), not to build it.
**Conclave role:** Component-zero — smallest shippable slice proving the self-improvement thesis

**Two outputs from one verification pass:**

| Output | Trigger | Action |
|--------|---------|--------|
| Closing signal | Item verified as fixed on disk | Status → `resolved`; drains into archive on next triage |
| Nomination signal | Same pattern recurs across N items AND holds under oracle check | Nominated as skill/contract mutation candidate → human-gated Forge evolve |

**Verification approach (hybrid):**

Deterministic check first (file existence, pattern match, script exit code). LLM sampling only
where deterministic check is insufficient (e.g. "output shape drift"). Confidence-graduated:
deterministic signal → auto-act; fuzzy signal → propose for human approval; skill/contract
mutation → always human-gated.

The closing loop drains the backlog; the nomination branch feeds the learning loop.
Both run from a single default `feedback_verify.py` invocation (the scan is the no-flag default; `--apply` performs the write-back). There is no `--scan-accepted` flag.

---

## 7. Memory and Briefing Recall

**What it does:** Provides every advisor with full session context at open — current focus,
open issues, pending decisions, recent reflexions — without re-reading raw history. Briefings
are the cache; sessions/decisions/GH issues are the truth.

**Module:** C-002 Briefings + C-005 Memory
**Scripts:** `briefing/regen.py`, `lifecycle/session_init.py`

**Two-layer architecture:**

| Layer | Storage | Who writes | Freshness |
|-------|---------|-----------|-----------|
| Source of truth | `agent-memory/advisors/{sessions,decisions,mentions}/` + GH issues | Scripts via `close-session.sh`, `file-decision.sh`, `mention.sh` | Append-only, never overwritten |
| Cache (briefings) | `agent-memory/advisors/briefings/<advisor>.md` | `regen.py` | Regenerated if mtime >24h (mtime-guard in `session_init.py`) |
| Cross-agent live | `agent-memory/hot.md` (≤500 words) | Lifecycle scripts; reconciled by Quorum/Forge | Updated per session; three sections: Now / Recent decisions / Watch |

Briefing structure: eager layer ≤6000 chars (current focus, open issues, recent decisions,
personality, reflexion buffer) + archival sections (full session history, full decision log).
Eager layer is what advisors actually load at session start; archival on demand.

Reflexion buffer: last-3-session `reflexion:` frontmatter sentences injected as priors via
`session_init.py`. Inspired by Shinn et al. NeurIPS 2023 (Reflexion) — episodic verbal
feedback improves next-session accuracy without retraining.

---

## 8. Wiki Capture (Knowledge Graduation)

**What it does:** Promotes durable understanding from session artifacts to the team wiki —
the long-term knowledge layer. Distinct from memory (records *what happened*); wiki encodes
*why it works* (concepts, patterns, decisions, architecture explanations).

**Module:** C-004 Lifecycle (study phase) + wiki scripts
**Triggered by:** `/team.done` Study phase (mandatory for spec/research sessions)

**Invocation:**

```bash
python3 .claude/skills/team.forge/scripts/lifecycle/study_phase.py --advisor <advisor>
```

Six steps in order:

1. `wiki-capture-suggest.sh --since HEAD~5` — suggest wiki-capture candidates from recent diffs
2. `promote-decision.sh --id <id>` — graduate each candidate decision to wiki (per candidate)
3. `wiki-bridge-rebuild.sh` — rebuild `_bridges/ops-bridge.md` (runs only if ≥1 promoted)
4. `wiki-audit-stale.sh` — flag stale entries; **P0-blocking** on contradictions (exit 3 = must triage before `close-session.sh`)
5. `wiki-hot-sync.sh` — sync `hot.md` signals to wiki entries
6. `wiki-link-check.sh --quiet` — validate wikilinks across vault

Exit semantics: 0 = clean (Study row omitted from session summary); 2 = non-blocking findings
(⚠ row); 3 = P0 blocking (✗ row, must triage before close commit). Non-blocking failures
follow ADR-0003 `wiki_failure_policy: defer`.

For Conclave, the team-wiki (the reference instance's knowledge vault) maps to a top-level
`knowledge/` directory beside `engine/` (not inside it). The reference instance's concept pages
carry across as `instances/<instance>/knowledge-seed/` — not as engine assets.

---

## 9. Autonomous Pipeline / Oracle (089)

**What it does:** Runs a full autonomous research → generate → rank → verify → verdict cycle
without round-trips to the user. Produces the external falsification signal required by the
learning loop. Intrinsic self-correction degrades; without an external verifier, promoted
lessons are unreliable.

**Module:** C-007 Oracle
**Status:** ~30% built — design-locked; ranker/judge/critic scripts exist; pipeline not fully wired

**Pipeline (P1–P7):**

| Phase | Executor | Output artifact |
|-------|----------|----------------|
| P1 — research | Scout | Ranked cited options + `scope_questions[]` for GATE#1 |
| P2 — scope correction | (advisor) | Locked AC-contract |
| P3 — plan | (advisor / Atlas) | `plan.md` |
| P4 — spec | (advisor) | `spec.md` with locked acceptance criteria |
| P5 — generate | Atlas (×N candidates) | `execute-manifest.yaml` |
| P6 rank | Ranker | `rank-<slug>-<ts>.yaml` (3-stage: diversity guard → ORM prune → PRM step-score) |
| P6 floor | Iris | `oracle-signal.yaml` (deterministic; sycophancy-immune) |
| P6 critic | Socra (concurrent with floor) | `critic-refutation.yaml` (5 red-team techniques, one-way) |
| P6 verdict | Themis (Judge) | `verdict-<slug>.yaml` (calibrated; citation-grounded) |
| P7 — lesson | Forge | Nominated mutation candidate → human-gated evolve run |

**Key design invariants:**

- Judge ≠ producer (D18.1): same model-run cannot both generate and judge an artifact.
- Critic is one-way (D35): Socra writes `critic-refutation.yaml` and exits; never messages
  Judge directly. Prevents debate collapse (ColMAD finding: collaborative one-way +19% vs
  competitive interactive).
- Iris as floor: deterministic pipeline output is structurally independent of the LLM judge;
  provides a falsification surface that cannot be argued away.
- Wrong lessons are demoted, never silent-deleted. Reversal path: `re-occurred →
  lesson-failed → revise/retire` with provenance on every automated action.

**Lesson promotion gating (learning loop):**

A pattern from the closing loop (C-006) reaches the oracle only when it recurs across N items
with sufficient `hit_count`. The oracle then either confirms it holds (→ nominate for
Forge evolve) or falsifies it (→ demote, keep in index with `lesson-failed` status).
Human approval is required before any skill or contract is mutated. This is the confidence-
graduated authority principle: deterministic signal → auto-act; oracle-confirmed recurring
pattern → propose; skill/contract edit → always human-gated.

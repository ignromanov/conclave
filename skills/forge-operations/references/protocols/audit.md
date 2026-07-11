---
protocol: audit
version: 1.0.0
description: |
  Detects drift across the agent model. Read-only by default. --fix delegates to Evolve.
  Also runs as sub-call from Evolve Stage 7.
---

# Audit protocol

## Modes
- `read-only` (default): prints findings.
- `--fix`: groups findings and delegates to Evolve with computed args.

## Categories

| # | Category | Script | Severity |
|---|----------|--------|----------|
| 1 | Version alignment | `engine audit versions` | WARN (MINOR gap) / CRIT (MAJOR) |
| 2 | Phantom skills | `engine audit phantom-skills` | WARN |
| 3 | Bloat | `engine audit bloat` | WARN / CRIT (>2× cap) |
| 4 | Missing required sections | inline grep | WARN |
| 5 | Registry consistency | `engine audit registry-consistency` | CRIT |
| 6 | Overlay health | `engine audit overlays` | WARN / INFO |
| 7 | Contract integrity | inline | INFO |
| 8 | Config safety | `engine audit agent-configs` | CRIT (secret/injection) / WARN (--no-verify, --force) |
| 9 | Skill stocktake | `engine skill stocktake` | INFO (Improve/Retire/Merge verdicts) — advisory only |
| 10 | Skills/plugins sprawl | `engine audit skills` → `protocols/audit-skills.md` | INFO (S1-S10 defect categories, advisory) |
| 11 | Scope collision (spec 089) | `engine audit scope-collision` | CRIT (overlapping `owns:` across agents) |
| 12 | Phantom-skill pre-gate (spec 089) | `engine audit phantom-skills` (BLOCKING — mirrors hire.md G1) | CRIT (blocks register/promote) |
| 13 | Judge incentive + calibration floor (spec 089) | inline grep + `current.yaml` read | WARN (D19 phrase missing) / **CRIT** (calibration absent/stale/below-floor, D32) |

## Run

```
for name in versions phantom-skills bloat registry-consistency overlays agent-configs skills; do
  engine audit "$name"
done
```

Aggregate findings by (category, severity, target).

## Fix-mode delegation

| Category | Delegation |
|----------|-----------|
| version_alignment | `evolve(target=<advisor>, aspects=[<missing>])` |
| phantom_skills | `evolve(target=<advisor>, aspect=toolbox, action=remove-skill)` |
| bloat | `evolve(target=<advisor>, aspects=[identity,responsibilities], action=thin-refactor)` |
| overlay_drift | `evolve(target=<advisor>, aspect=contract-overlays, action=update-overlay)` |
| registry | `python -m engine register advisor --rebuild` |

**ARCHITECTURE.md maintenance hook** — when any of these architectural categories triggers a fix (i.e. evolve is delegated above), the same prompt as `protocols/evolve.md` Stage 6 fires: review `ARCHITECTURE.md` §A/§B/§C for impact, or annotate `architecture-impact: none — <rationale>` in the propagation commit. Mechanical staleness is covered by `engine audit architecture-doc`; this gate covers conceptual currency.

## Missing required sections (Category 4)

For each advisor, check:
- frontmatter has `forge:` block with 3 fields
- body has `## Identity`, `## Scope`, `## Contract Overrides`

## Cat 11 — Scope collision (spec 089, D8/R6) — CRIT

Two distinct agents must never claim the same `owns:` artifact (e.g. two executors both owning
`p1-research-artifact`; a new scout overlapping an existing researcher — round-10 N2). Run:

```bash
python -m engine audit scope-collision
# exit 0 = OK · exit 3 = collision(s) found (CRIT) · exit 1 = error (no agents dir)
```

Read-only. On a collision, file a drift entry and delegate to `evolve` to re-scope one agent's
`owns:` (the role-bounded one keeps it; the overlapping one drops it or is rejected at hire).

## Cat 12 — Phantom-skill pre-gate (spec 089) — CRIT, BLOCKING

The same `engine audit phantom-skills` check `hire.md` G1 runs, enforced post-hoc as a **blocking**
category (not advisory like Cat 2). Any agent whose Toolbox lists a skill that `engine skill verify`
cannot resolve → **block register/promote** until fixed. This is the audit-time backstop for the
hire-time G1 gate.

## Cat 13 — Judge incentive + calibration floor (spec 089, D19/D32)

Two sub-checks on `exec-themis-judge.md` / `exec-socra-critic.md` / `exec-metron-rank.md` agent-defs (keyed by filename — no `role:` frontmatter field exists in exec-*.md):

**13a — D19 incentive phrase (WARN).** The judge agent-def MUST carry the verbatim D19 phrase
("Rigorous rejection is the path of least resistance …"). Missing → WARN + delegate to `evolve`
to inject it (hire.md §3a.7).

```bash
grep -qF "Rigorous rejection is the path of least resistance" .claude/agents/exec-themis-judge.md \
  || echo "Cat13a WARN: D19 incentive phrase absent from judge agent-def"
```

**13b — calibration floor (CRIT, D32).** Each of `exec-themis-judge` / `exec-socra-critic` / `exec-metron-rank` MUST have
`.conclave/agent-memory/executors/themis-judge/calibration/current.yaml` (judge), `socra-critic/calibration/current.yaml` (critic), or `metron-rank/calibration/current.yaml` (ranker) with **all three** true, else **block
register/promote/dispatch** (`advisory` permits dispatch-with-note but blocks promotion):

- `threshold_met: true` (FPR ≤0.10, FNR ≤0.15, ECE ≤0.15, κ ≥0.60 — themis floors)
- `run_at` within 30 days
- `agent_model_version` matches the agent's current `forge:` model-version

Absent / stale (>30d) / version-mismatch → verdicts become `inconclusive` + `calibration_note`,
no promotion, no gating role. This check also runs as a **pre-P6 guard** inside `workflow.autopilot`
(spine.md) and in `forge evolve` Stage 7.

## Quality loop
Before emitting findings, apply `contracts/quality-loop.md`. Report skipped items with reason.

## Drift rules for spec 051 memory layout

| Check | Severity |
|-------|----------|
| `.claude/skills/team.<a>/memory/BRIEFING.md` exists | ERROR |
| `.claude/skills/team.<a>/memory/topics/{inbox,decisions,sessions}.md` exists | ERROR |
| `.claude/skills/team.<a>/memory/topics/*.md` exists (legacy) | ERROR |
| `memory/personality.md` contains facts also in `.ai/product.md`/`progress.md` | WARN (grep-based) |
| `.ai/agent-memory/advisors/briefings/<a>.md` not regenerated > 7 days | WARN (mtime check) |
| Mention in `.ai/agent-memory/advisors/mentions/<a>/open/` older than 14 days | WARN (frontmatter.created) |
| Mention `ref_session` points to non-existent session file | ERROR |
| Session `decisions` list references non-existent decision slug | ERROR |
| Same mention id in both `open/` and `archive/` | ERROR |

## How to run

```bash
for name in versions phantom-skills bloat registry-consistency overlays agent-configs skills; do
  engine audit "$name"
done
```

(`--fix` is protocol-level, not a CLI flag: Audit delegates categorized findings to `evolve` per
the Fix-mode delegation table above — `engine audit <name>` itself has no `--fix` option. This
runner loop itself is out of spec 051 scope — implemented as part of `team.forge` evolution; this
doc describes the rules, not the runner.)

## Risk Register (proactive — absorbed from project-delivery/project-manager.md)

> Beyond drift detection: track open risks across the agent system before they become drift events.

### Format

`.ai/agent-memory/advisors/risk-register.md`:

```markdown
---
updated: YYYY-MM-DD
---

# Risk Register

| ID | Risk | Likelihood | Impact | Owner | Mitigation | Status |
|----|------|-----------|--------|-------|-----------|--------|
| R001 | agent-teams plugin breaks | M | H | kai | Version-pin agent-teams plugin in `.claude/settings.json`; agent-teams contract documented in executor-protocol.md so a runtime fallback can be implemented if needed; register-executor.sh provides scaffolding independence (forge can create executor SKILL.md files without the plugin running). audit_trigger: Run after each agent-teams plugin version bump. | active |
| R002 | hot.md write contention | L | M | quorum | atomic mv + 10-retry verify loop (no flock — macOS bash 3.2 compat). Compaction guarded by mtime check or single-caller invariant (Quorum at /conclave:done). | mitigated |
| R003 | Voice schema retro-update damages established advisor voices | L | M | kai | Grandfathered path documented in hire.md §3a.5; retroactive populate is opt-in per advisor; voice axis assertions are non-prescriptive. audit_trigger: Run forge audit after each forge evolve session that touches voice schema. | monitored |
```

### Audit phase

In each `audit.md` run, Quorum:
1. Reads current risk-register.md
2. For each `active` risk: ask owner advisor "Status changed?" (manual gate)
3. Append new risks surfaced during audit (drift events that suggest systemic risk)
4. Mark mitigated risks as `mitigated` (not deleted — preserved for retro)

## Drift Prediction (absorbed from interview-assist/interview-strategist.md)

> Predict-Prepare-Validate methodology applied to advisor drift.

### Predict

For each advisor, list 3 most likely drift modes (where they typically deviate from intended behavior):

```markdown
## Predicted drift — <advisor>

1. **<Drift mode>** — likelihood: M | example: <past instance> | early signal: <behavioral marker>
2. ...
3. ...
```

### Prepare

For each predicted drift, define a behavioral test:

```markdown
- Drift R001-A (Kai over-engineers small fixes):
  - Test: review last 5 PR-feedback sessions; count cases where Kai added abstraction not requested
  - Threshold: ≥3 cases / 5 = drift confirmed
```

### Validate

Run the prepared tests during audit. If threshold exceeded, file drift entry + dispatch Kai for `/conclave:forge evolve` adjustment.

### Audit cadence

- Quick audit: every 5th `/conclave:done` — quick risk review
- Full audit: monthly — full predict-prepare-validate cycle for all advisors
- Triggered audit: on founder report of drift symptom

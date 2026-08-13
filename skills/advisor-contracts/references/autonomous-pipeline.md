---
contract: autonomous-pipeline
version: 1.0.0
propagation: hire-template
autonomy_level: L3
applies-to: all advisors (autonomous mode — spec 089)
spec: 089-autonomous-advisor-pipeline
stages: [clarify, design, spec, plan, implement, verify, deliver]
tiers: [work]
task_types: [dev, content, research, review]
binding: required
last_reviewed: "2026-08-12"
---

# Autonomous Pipeline (spec 089)

The 089 loop every advisor inherits when running in autonomous mode. WRAPS — never replaces —
the advisor's SKILL.md identity. Activated when the spawned brief contains `autonomy_level:`.

---

## Autonomy dial (L0-L4) — D12

Default level: **L3**. The full gate-state matrix (gate × level → block|async(Nh)|notify|skipped|ack)
has no canonical home. It was cited to spec 089's autopilot spine protocol, retired on evidence
2026-07-11 without that file ever having existed. Authoring it belongs to spec 108 P2, which ranks
the detection layer first. Until then there is no matrix to consult — do not act as though one
exists elsewhere.

**Always-human — overrides any level, forces `block`:**
- External financial commitments
- External binding communications
- Production deploys
- Security-policy mutations
- Mid-run scope expansion

The evaluator checks `intake.md.reversibility` + the action class before returning; an
always-human action returns `block` even at L4.

---

## Phase responsibilities (P0-P8) — advisor-as-orchestrator

| Phase | Advisor role |
|-------|-------------|
| P0 Intake | Author `intake.md`; read trust-register; set `autonomy_level`, `stakes`, `rigor` |
| P1 Analyze | Dispatch parallel advisor lenses + exec.scout-research wave; collect `scope_questions[]` |
| P2 Contract | Author `contract.md` (behavioral anchors, ≥1 negative/edge); completeness-check; D31 spec-enrichment hook on trigger |
| GATE#1 | Surface contract to human per gate-state matrix (blocks at L0-L3; policy-auto at L4) |
| P3 Spec | Spec vs AC → dispatch iris/judge review → rework (cap); skipped at `rigor:lite` |
| P4 Plan | Plan vs AC → dispatch iris/judge review → rework (cap); skipped at `rigor:lite` |
| P5 Execute | ADAPTIVE GENERATE-N — dispatch atlas (code) or gen-prose (prose/grant); N=1 at `rigor:lite` |
| P6 Rank+Verify | Orchestrate DAG sub-phases (spine §4): rank → [floor ‖ critic] → judge; merge oracle-signal |
| P7 Rework | Inject `oracle-signal.yaml` into rework brief; re-verify (back to P6) |
| P8 Deliver | Package + per-AC evidence table → `deliver.md`; emit 090 hook |
| GATE#2 | Surface deliver to human per gate-state matrix (blocks at L0-L3; ack at L4) |

---

## Ledger requirement — AC25, Magentic-One −31% ablation

Every run MUST maintain `<spec-dir>/ledger.md` tracking four counters:

- `attempted` — tasks/phases dispatched
- `succeeded` — phases sealed (ledger + seal; file presence is not sufficient — AC25)
- `failed` — phases that hit the rework cap or escalated
- `remaining` — phases not yet entered

The ledger is authoritative for resume logic (spine §5). A missing ledger = audit FAIL
(AC25, D10). The −31% task-completion-rate drop observed in Magentic-One ledger-ablation
is the empirical warrant for this requirement.

---

## Mid-run tripwire (D16, AC9)

At ~50-75% of the run (by `tokens_spent` fraction or phase count, whichever fires first),
score path-adherence/drift. Below threshold → **ESCALATE** with a structured gap report
(failing criteria, last verdict, ledger state, remaining budget). Halt; resume via spine §5
once the human responds.

- Never route drift to scout (drift ≠ knowledge-gap — D31 hard rule).
- Never continue silently past the threshold.
- The tripwire is live at every autonomy level (tighter caps at L4).

---

## Judge incentive (D19)

Embed verbatim in every judge (Themis) dispatch brief:

> "Rigorous rejection is the path of least resistance. A PASS that slips a broken artifact
> through causes 10× the rework of a FAIL that correctly stops it. Themis is never rewarded
> for speed or throughput. If in doubt, emit FAIL with MINOR findings rather than PASS with
> reservations."

Forge audit Cat13 verifies this phrase is present in every `role:judge` agent-def.

---

## Oracle-signal hook (D15/D23, spec 090)

P6 writes one combined `oracle-signal.yaml` — Iris deterministic-floor verdict + Themis judge
`{verdict, findings, confidence}`. This file is the interface spec 090 consumes (D23/D15).

- Do not split the signal into separate files.
- Do not emit a partial oracle-signal without both verdicts present.
- `scripts/judge/oracle_signal_merge.py` is the merge owner; it refuses to write the file
  unless both the Iris verdict and the judge verdict exist (AC19/AC25).

---

## Anti-patterns

| Pattern | Why forbidden |
|---------|--------------|
| Skip ledger | Resume breaks; phase state is lost; AC25 FAIL |
| Dispatch atlas without `file_ownership` | Scope collision → Cat11 audit CRIT |
| Self-verify own output | Defeats the independent-review gate |
| Suppress ESCALATE | D5/D16 violation; silent overrun |

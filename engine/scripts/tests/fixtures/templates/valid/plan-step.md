---
type: plan-step
schema_version: 1
tags: [op/plan-step, status/open]
plan_id: 076-lifecycle-bash-extraction
step_id: 03-templates
created_at: "2026-05-16T11:00:00Z"
depends_on: []
---

# Plan Step — 076-lifecycle-bash-extraction / 03-templates

**Goal**: Author 6 op-type templates + schema-validation bats (T3 of spec 076 plan).

**Executor**: exec.atlas-dev

**Acceptance criteria**:
- [ ] 6 template files exist under `templates/` with `schema_version: 1`
- [ ] `schema-validation.bats` passes (GREEN)
- [ ] 12 fixtures created (6 valid + 6 invalid)

**Notes**: Independent of T1/T2; can run in parallel with those tasks.

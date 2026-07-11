---
type: plan-step
schema_version: 1
tags: [op/plan-step, status/open]
plan_id: <plan-slug>
step_id: <NN-step-slug>
created_at: <ISO-8601 timestamp>
depends_on: []
---

# Plan Step — {{plan_id}}/{{step_id}}

## Schema

| Field | Type | Required | Description |
|---|---|---|---|
| type | string | yes | Always `plan-step` |
| schema_version | integer | yes | Always `1`; consumers reject unknown versions |
| tags | list | yes | `[op/plan-step, status/open]` initially; transitions to `in-progress`, `done`, or `blocked` via tag-change |
| plan_id | string | yes | Slug of the parent plan, e.g. `076-lifecycle-bash-extraction` |
| step_id | string | yes | Zero-padded step number + slug, e.g. `01-snapshot-lib`, `02-run-log` |
| created_at | string | yes | ISO-8601 UTC timestamp when the step was created |
| depends_on | list | yes | List of `step_id` values that must reach `done` before this step starts; empty list `[]` if none |

## Producer

Agent (Working Session mode) running `subagent-driven-development` — the plan-execution skill
that decomposes a spec into enumerated steps and writes one file per step. Future plan-execution
scripts (T7+) will also produce these files programmatically when converting `plan.md` tasks into
machine-readable step files.

Resolution: when a step is completed, the executor (or lifecycle script) transitions
`status/open` → `status/done` via tag-change. Blocked steps carry `status/blocked` with a
`blocked_by` note in the body.

## Path

`agent-memory/plans/<plan-id>/steps/<step-id>.md`

Example: `agent-memory/plans/076-lifecycle-bash-extraction/steps/03-templates.md`

## Example

```markdown
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

**Notes**: Independent of T1/T2; can run in parallel. Template = doc-as-contract.
```

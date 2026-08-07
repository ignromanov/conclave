---
protocol: evolve
version: 1.0.0
description: |
  Mutates existing agent model. Scope-flexible (single advisor / multi / all / lifecycle / architectural).
  Composable aspects. Diff-preview → approve → edit → commit loop.
---

# Evolve protocol

## Stages

### Stage 1 — Parse request
Extract:
- **targets** (discovery-based): single / multi / all / lifecycle / architectural
  (resolution table: spec 049 §7.3)
- **aspects** (keyword → `references/aspects/<aspect>.md` via spec 049 §7.4 table)
- **hints**: specific sections, overlay ops, version intent

Ambiguous → AskUserQuestion with multi-select.

### Stage 2 — Load aspect references
Read each `references/aspects/<aspect>.md`. Each aspect declares cross-aspect deps
in its frontmatter (`depends_on: [<aspect>, ...]`).

For each dependency not yet included → AskUserQuestion: "Include <dep>? reason: <from frontmatter>".

### Stage 3 — Build blast-radius plan
For each (target, aspect) pair:
- `python -m engine find references <pattern-from-aspect>` → concrete files
- Produce plan row: target × aspect × files × operation kind

### Stage 4 — Present plan, get approval
Show: affected files count, aspects touched, expected commits.
AskUserQuestion: proceed / revise / abort.
One-shot. No automatic split.

### Stage 5 — Execute per-aspect loop
For each aspect in plan:
1. Show diffs for all files in this aspect.
2. AskUserQuestion per aspect: approve / request-edit / skip / abort.
3. Apply edits (batched within aspect).
4. Commit: `chore(forge/evolve/<aspect>): <description>`.

### Stage 6 — Propagation check
For each touched aspect with `propagation: hire-template`:
- Update `protocols/hire.md` + `templates/` as needed.
- Bump `references/agent-model-version.md` (MAJOR/MINOR/PATCH per change kind).
- `python -m engine model bump --all` to stamp every advisor.
- Commit: `chore(forge/evolve): bump agent-model to X.Y.Z (<reason>)`.

For any protocol file changed (aspect = lifecycle touching `protocols/*`):
- Bump protocol version in its frontmatter.
- Add CHANGELOG entry.

**ARCHITECTURE.md maintenance hook** — if any touched aspect ∈ {`lifecycle`, `contract-overlays`, `agent-frontmatter`, `memory-structure`}:
  - Prompt: "ARCHITECTURE.md likely affected (§A / §B / §C). Review now or annotate commit?"
  - Options:
    1. Open `ARCHITECTURE.md` and update affected section + bump `last-reviewed:` frontmatter.
    2. Annotate the propagation commit body with `architecture-impact: none — <one-line rationale>`.
    3. Defer with TODO: file a forge follow-up issue.
  - Why a human gate (not a script): architecture updates require judgment about what changed *conceptually*. Mechanical staleness is handled by `audit-architecture-doc.sh` (T13.4); this prompt covers conceptual currency.
  - The same prompt fires from `protocols/audit.md` fix-mode when an architectural-class finding is being resolved.

### Stage 7 — Post-change audit
Invoke `protocols/audit.md` in read-only mode.
Report: new drift, phantom overlays, registry issues.

### Stage 8 — Summary
Commits | advisors affected | versions bumped | follow-ups.

## Cross-aspect dependencies (quick ref)

| Aspect changed | Likely cascades |
|----------------|-----------------|
| `toolbox` | `responsibilities` |
| `shared-rules` | all advisors via overlay check |
| `agent-frontmatter` | `hire` |

## Aspects

Each mutation to the advisor model happens via a named aspect. Load the aspect ref before coding.

| Aspect | Scope |
|--------|-------|
| `aspects/identity.md` | Mutate voice/character; affects `memory/personality.md` |
| `aspects/references.md` | Add/update domain reference in `memory/references/<domain>.md` |
| `aspects/forge-scripts.md` | Modify the Python engine in `engine/scripts/` (enginelib-first, thin adapters; gate: ruff + mypy + pytest, core I/O-free) |
| `aspects/lifecycle-skill.md` | Modify `team.{start,processing,done,handoff}/SKILL.md`; contract-changing, requires end-to-end smoke test |

## Blocked mutations (spec 051)

- `Edit` on `.claude/skills/team.*/memory/BRIEFING.md` — file must not exist
- `Edit` on `.claude/skills/team.*/memory/topics/*` — structure deprecated
- Direct `Edit` on `.ai/agent-memory/advisors/**` — scripts only

### Changing an advisor id

`engine advisor rename --from <old> --to <new>` is the script for this. Never do it by hand:
the id appears in live config, in the record, in derived caches and in dated evidence, and each
wants different treatment — the record keeps its prose, the caches are dropped rather than
carried forward, and `ops/archive/` + `ops/proof/` must keep naming the id that existed then.

Dry-run is the default and prints the whole plan; mutation needs `--apply --confirm`. Read the
plan before confirming — in particular the `unclassified` and `prose-only` sections, which list
what the command deliberately did not touch.

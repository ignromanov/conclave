---
kind: commit-conventions
version: 1.0.0
---

# Commit message conventions

| Context | Format |
|---------|--------|
| Hire — advisor created | `feat(team/<id>): hire — <role>` |
| Hire — registry rebuilt | `chore(forge/hire): rebuild CLAUDE.md + quorum registry` |
| Evolve — per aspect | `chore(forge/evolve/<aspect>): <description>` |
| Evolve — model bump | `chore(forge/evolve): bump agent-model to X.Y.Z (<reason>)` |
| Audit — fix | `fix(forge/audit/<category>): <target> — <what>` |
| Skeleton / structure | `feat(forge): <area> — <what>` |

## Rules
- Lowercase, imperative, no trailing period.
- `<id>` = advisor short id (kai, nexus, shade, spark, vox).
- `<aspect>` ∈ { identity, responsibilities, toolbox, memory-structure, lifecycle, shared-rules, agent-frontmatter, contract-overlays }.

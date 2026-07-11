---
aspect: shared-rules
version: 1.0.0
depends_on: []
propagation: hire-template
files:
  - .claude/rules/*.md (universal)
  - ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/*.md (advisor-only)
  - .claude/CLAUDE.md (project-level)
find-pattern: |
  "rules/" OR "contracts/" OR "CLAUDE.md"
---

# Aspect: shared-rules

Cross-cutting rules living in `.claude/rules/` (universal, all agents) and
`${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/` (advisor-only).

## Decision: rule or contract?
- **Rule**: applies to every agent invocation (even non-advisor). → `.claude/rules/`
- **Contract**: applies only to advisor sessions. → `${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/`

## Audit implication
Any shared-rules change triggers overlay re-check across every advisor.

---
aspect: agent-frontmatter
version: 1.0.0
depends_on: []
propagation: hire-template
files:
  - .claude/agents/team.*.md (frontmatter only)
external-skill: plugin-dev:agent-development
find-pattern: |
  ".claude/agents/team\\..*\\.md"
---

# Aspect: agent-frontmatter

Frontmatter discipline for `.claude/agents/team.*.md`.

## Why this is its own aspect
- Field set evolves (description, color, tools, model).
- Format is shared across ALL advisors — touching it is architectural.

## Delegate to
- `plugin-dev:agent-development` skill for validation.

## Mutations often
- New field added (e.g., `model: sonnet-4-6`).
- Description format update (emoji prefix policy).

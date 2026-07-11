---
aspect: identity
version: 1.0.0
depends_on: []
propagation: hire-template
files:
  - skills/team.<id>/memory/personality.md
  - skills/team.<id>/SKILL.md (## Identity section)
  - .claude/agents/team.<id>.md (tone hint in description)
find-pattern: |
  "## Identity" OR "memory/personality.md" OR tone: field in agents/*.md frontmatter
---

# Aspect: identity

## What it covers
Role, language, philosophy, tone, domain anchors, pet peeves. The "who is this advisor" layer.

## Where it lives
1. `memory/personality.md` — long-form prose (philosophy, values, working style, origin).
2. `SKILL.md ## Identity` — concise block (role + anchors + language).
3. `agents/team.<id>.md` frontmatter — tone hint for Task tool delegation.

## Typical mutations
- "Сделай Kai жёстче / мягче"
- "Переосмысли философию Nexus"
- "Смени tone у Spark на более аналитичный"

## What NOT to touch
- `.ai/agent-memory/advisors/briefings/<id>.md` (auto-generated shared briefing, spec 051)
- Toolbox / Skills
- Lifecycle protocol stanzas

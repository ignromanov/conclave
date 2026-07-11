---
aspect: contract-overlays
version: 1.0.0
depends_on: [shared-rules]
propagation: none
files:
  - skills/team.<id>/contracts/<contract-name>.md
external-command: engine overlay apply
find-pattern: |
  "contracts/.*\\.md" scoped to skills/team.<id>/
---

# Aspect: contract-overlays

Per-advisor overrides of default contracts.

## Overlay shapes

| Type | Meaning |
|------|---------|
| `constraint` | tightens the default (Kai never edits code) |
| `extension` | adds to the default (Nexus reads cross-advisor issues) |
| `replacement` | full substitute (rare) |

## Frontmatter required
- `contract: <base-name>`
- `advisor: <id>`
- `overrides-base-version: X.Y.Z`
- `type: constraint | extension | replacement`

## Also update
- Advisor SKILL.md `## Contract Overrides` human-readable list
  (declaration is documentation only; discovery is filename match).

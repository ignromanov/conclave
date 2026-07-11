---
name: team.${ID}
description: |
  Use when the operator wants a ${ROLE} advisory session about ${PROJECT_NAME}.
  Triggers: ${TRIGGERS_PLACEHOLDER}
forge:
  model-version: ${MODEL_VERSION}
  hired-by: ${HIRE_VERSION}
  last-evolve: "-"
color: ${COLOR}
tone: ${TONE}
---

@../../../${PROJECT_CONTEXT_PATH}

# team.${ID} — ${ROLE}

## Identity
Role: ${ROLE}
Language: ${TEAM_LANGUAGE}
Philosophy: _(filled at first launch)_
Domain anchors: _(filled at first launch)_

## Scope
Can answer: _(filled at first launch)_
Boundaries: _(computed via discovery — see `${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/session-lifecycle.md`)_

## Domain Chains
_(role-specific skill chain)_

## Contract Overrides
_(none at creation — overlays added later via Evolve aspect=contract-overlays)_

@memory/personality.md

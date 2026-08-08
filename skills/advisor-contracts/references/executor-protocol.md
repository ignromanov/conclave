---
contract: executor-protocol
version: 1.1.0
applies-to: exec-*.md agent-defs (+ optional exec.* script dirs)
---

# Executor Protocol

> Cardinal rules for the Executor agent category. Peer to advisor-protocol and lifecycle-skill.

## Definition

An **Executor** is an agent worker dispatched by advisors (or directly by founder) to perform bounded execution tasks. Executors:

- Have their own self-chosen identity (name, emoji, color, 4-axis voice)
- Have their own minimal flaky-ledger memory (`MEMORY.md` ≤50 lines, append-only)
- Are NOT participants in advisory meetings
- Do NOT file decisions, sessions, or mentions
- Do NOT have a briefing
- Do NOT participate in `/conclave:start` / `/conclave:processing` / `/conclave:done` lifecycle

## Folder structure

```
agents/exec-<chosen-name>-<role>.md    # the agent-def: frontmatter + inline Voice + contract
                                       # (registers the conclave:exec-<name>-<role> agent type)

engine/skills/exec.<chosen-name>-<role>/   # OPTIONAL — role scripts only, no SKILL.md wrapper
└── scripts/
    └── <helper>.py
```

```
.conclave/agent-memory/executors/<chosen-name>-<role>/
├── MEMORY.md                  # ≤50 lines, append-only flaky-ledger
└── runs/                       # Optional per-run artifacts
    └── <date>-<task-slug>.md
```

## Naming convention

The stable slug is `<chosen-name>-<role>`; each surface adds its own prefix:

| Surface | Form | Why |
|---------|------|-----|
| Agent-def (flat `agents/`) | `exec-<chosen-name>-<role>.md` | hyphen `exec-` prefix disambiguates from advisor defs in the flat dir |
| Script dir (`engine/skills/`) | `exec.<chosen-name>-<role>/` | dotted skill-loader dir convention |
| Memory dir (`executors/`) | `<chosen-name>-<role>/` | bare — the `executors/` parent already scopes it |
| Dispatch `subagent_type` | `conclave:exec-<chosen-name>-<role>` | plugin agent-type reference |

- `<chosen-name>` is self-chosen at bootstrap (any unicode-safe identifier)
- `<role>` is one of: `dev`, `test`, future roles TBD

## Agent-def protocol

Each executor agent-def (`agents/exec-<chosen-name>-<role>.md`) must:
1. Declare `tools:` frontmatter — the executor's tool scope stated, never inferred from silence
2. Include `## Identity` block + an inline `## Voice` section (persona anchor — the roster
   convention is inline voice; NO separate `personality.md`)
3. Include `## Dispatch protocol` describing how callers invoke the executor
4. Include `## Output contract` (sentinel `<!-- exec:<chosen-name> v1 -->`; e.g. structured verdict for `*-test`)
5. Stay role-minimal — heavy domain logic lives in the plugin or `engine/skills/exec.*/scripts/`

## Memory model

- `MEMORY.md` is **flaky-ledger** style — append-only log of "what burned me / what worked"
- ≤50 lines hard cap; on overflow, oldest entries archived to `runs/` or dropped
- Written by executor itself (manual edit during run), NOT by scripts
- Read at executor session start (loaded into context once)

## Lifecycle

- **Bootstrap** (one-time): `engine register executor` scaffolds the agent-def + memory + asks self-introduction
- **Dispatch** (per-task): caller spawns executor via `agent-teams` Agent tool with task brief
- **Run** (during task): executor performs work, optionally appends to MEMORY.md, produces output
- **Cleanup** (post-task): executor exits; no minutes, no decisions filed

## Output contract

Every executor response MUST start with `<!-- exec:<chosen-name> v1 -->` HTML comment for tracing.

## Anti-patterns

- Executor participating in meetings → REJECTED (it's an advisor if it does)
- Executor filing decisions → REJECTED (use mention to advisor instead)
- Executor with briefing → REJECTED (briefing implies advisor)
- Hardcoded role suffix in chosen-name (e.g., `exec.atlas-dev-coder`) → REJECTED (one role only)
- Multiple executors sharing chosen-name → REJECTED (collision; bootstrap script must reject)

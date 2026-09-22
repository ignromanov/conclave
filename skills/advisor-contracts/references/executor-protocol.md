---
contract: executor-protocol
appliers: [all executors]
version: 1.1.0
stages: [implement, verify]
tiers: [work]
task_types: [dev, content, research, review, advisory]
binding: required
last_reviewed: "2026-08-12"
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
1. Carry the canonical frontmatter, in this order (pinned by
   `tests/test_executor_defs.py::test_executor_frontmatter_is_canonical`):
   `name · description · tools · model · tier · chosen-name · emoji · color · created`.
   Harness-recognized fields come first; `tools:` is stated, never inferred from silence, and
   `model: sonnet` lives in the file rather than in a dispatch string someone must remember
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

### Delivery is a file, and the caller names it

A long final message is not a delivery mechanism. Four consecutive dispatches returned reports
truncated mid-sentence, each costing a round-trip to recover the tail, and the one that worked
was the one told to put its result on disk (#185). Six agents in a separate run returned empty
and all six recovered the moment an output path was named for them.

So, per dispatch:

- **The caller names the output path in the brief.** Not "write it somewhere" — the exact path.
  A destination the executor invents is a destination the caller has to go looking for.
- **The executor writes the artefact there and returns a path plus a one-line verdict**, not the
  artefact. Anything over roughly two thousand words belongs in the file in every case.
- **Create the file with whatever tool the dispatch actually granted.** Five of the seven shipped
  executors are granted neither `Write` nor `Edit`; the only tools all seven share are `Read`,
  `Grep` and `Bash`, and none of those three is a file-writing tool by name. A rule written
  as "use `Write`" is a rule most executors cannot follow. Check the granted set, do not assume
  it. `test_a_contract_prescribes_tools_the_agent_has.py` fails this contract if it ever
  prescribes a tool the agent definitions withhold.

**There is no message channel out of an executor.** No shipped executor definition grants
`SendMessage`, `ListAgents` or any other messaging tool — measured across all seven `tools:`
lists — so an executor cannot message its caller, and a caller cannot recover a lost tail by
asking for it. That asymmetry is why the file is not a convenience: it is the only durable
return path an executor has. Messaging is the *caller's* capability and belongs to the peer
protocol in `session-lifecycle.md`, never to the dispatch.

### Wait or own the file — never both

If the caller is going to read a file the executor writes, the caller does not also write it,
and does not poll for it while the executor is still running. Pick one owner per path for the
duration of the dispatch. A poll-then-write pattern races, and the loser is silent: the file
exists, is the wrong version, and nothing reports a conflict.

### A dispatch that may run long checkpoints to disk

The harness terminates a dispatch that exceeds its ceiling, and a terminated dispatch returns
nothing at all — not a partial result, not an explanation. Work whose length is uncertain writes
its partial state to the named output path as it goes, so that a termination costs the tail
rather than the whole run. Do not discover the ceiling by hitting it; assume it exists and
write early.

### DONE means the tree says so

An executor reporting DONE states the commit, or states plainly what it left uncommitted.
`git status --short` is the check, and it is cheap. A report of completion over a dirty tree is
the single failure mode that survives every other rule here, because the caller has no way to
see it and the next session inherits the mess without knowing it was left.

## Anti-patterns

- Executor participating in meetings → REJECTED (it's an advisor if it does)
- Executor filing decisions → REJECTED (use mention to advisor instead)
- Executor with briefing → REJECTED (briefing implies advisor)
- Hardcoded role suffix in chosen-name (e.g., `exec.atlas-dev-coder`) → REJECTED (one role only)
- Multiple executors sharing chosen-name → REJECTED (collision; bootstrap script must reject)

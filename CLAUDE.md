# CLAUDE.md — Conclave

> Separate-context seed for the Conclave project. This is **not** a VoidPay product — it is its own
> project at `~/code/conclave/`. VoidPay (`~/code/vl/`) is the dogfooding origin.

## What this project is

Conclave is the engine for a **self-improving multi-agent advisory team**: persona-driven advisors +
task-scoped executors + a mandatory lifecycle + an append-only memory + a feedback loop that closes
its own items and rewrites its own agents. It ships as a **clean, general-purpose distribution** —
the engine + the always-present meta-role (Forge); the domain roster is **hired fresh per project**.

Read [`VISION.md`](VISION.md) first, then [`project-context.md`](project-context.md) (project
identity, loaded by every agent at session start) and [`constitution.md`](constitution.md) (binding
governance principles). The full doc-set — architecture, implementation, functionality, product,
migration — lives under [`docs/`](docs/) (index in [`README.md`](README.md)); the R1–R5 research
digest is [`docs/research/migration-bootstrap.md`](docs/research/migration-bootstrap.md).

## Where things live (during the in-place phase)

The implementation is **still inside VoidPay's `.ai/`** and is being captured here before extraction
(codec precedent 056: build in-place, extract at maturity).

| Concern | Current home (VoidPay `.ai/`) | Conclave target |
|---------|-------------------------------|-----------------|
| Lifecycle skills | `.claude/skills/team.{start,processing,done,handoff,forge}` | `engine/lifecycle/` |
| Advisor/executor personas | `.claude/skills/{team,exec}.*/` | `engine/roster/` |
| Feedback substrate | `.claude/skills/team.forge/scripts/feedback/` | `engine/feedback/` |
| Memory | `.ai/agent-memory/` | `engine/memory/` |
| Specs (049/051/084/085/086/089/090/091/093) | migrated — no longer in `.ai/` | **`docs/specs/` (self-contained)** |

## Origin specs (read for canon before redesigning anything)

- **086** unified feedback (notebook) · **084** briefings · **049** forge (agent factory)
- **085** lifecycle simplification · **051** memory architecture
- **089** autonomous pipeline + oracle/verifier signal
- **090** self-improvement L2/L3 (oracle-falsified lesson acquisition) — stub
- **091** deontic duty model (roster engine, Track-B spin-out unit) — design-locked
- **093** self-healing closing loop — proposed (first Conclave component)

## Working principles

Carry the seven architecture principles from `VISION.md` §6: file-as-message-bus · cache-over-truth ·
mandatory lifecycle · spec-driven · confidence-graduated authority · never-silent-delete ·
guardrails-as-first-class.

## Canon-first

This project has dense prior art in VoidPay's specs. Before designing any "new" component, check the
origin specs above and `~/code/vl/ai/ops/specs/`. Execute canon; do not redesign blank-slate.

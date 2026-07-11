# CLAUDE.md — Conclave

> Separate-context seed for the Conclave project. This is **not** a VoidPay product — it is its own
> project at `~/code/conclave/`. VoidPay (`~/code/vl/`) is the dogfooding origin.

## What this project is

Conclave is the engine for a **self-improving multi-agent advisory team**: persona-driven advisors +
task-scoped executors + a mandatory lifecycle + an append-only memory + a feedback loop that closes
its own items and rewrites its own agents. It ships as a **clean, general-purpose distribution** —
the engine + the always-present meta-role (Forge); the domain roster is **hired fresh per project**.

Read [`VISION.md`](VISION.md) first, then `.conclave/project-context.md` (this instance's identity
— DATA, scaffolded by `/conclave:init`) and [`constitution.md`](constitution.md) (binding
governance principles). The shipped doc-set — descriptive architecture — lives under
[`docs/architecture/`](docs/architecture/) (index in [`README.md`](README.md)).

## Where you write things — CODE vs DATA (spec 103)

This checkout is **two repos**. The split is by *audience*, not by language:

| | CODE — this repo | DATA — `.conclave/` (separate repo) |
|---|---|---|
| **Holds** | the engine, skills, agents, commands, tests, and descriptive `docs/architecture/` | everything this instance *works on and remembers* |
| **Audience** | anyone who installs Conclave | the operator |
| **You write here** | code, tests, shipped docs | **specs, plans, research, decisions, feedback, handoffs, memory** |

**Specs and plans go in DATA. Always.**

- Spec → `.conclave/ops/specs/<NNN-slug>/spec.md`
- Its plan → `.conclave/ops/specs/<NNN-slug>/plan.md` (beside the spec — *not* a separate plans tree)
- Its research → `.conclave/ops/specs/<NNN-slug>/research.md`
- Every spec must be listed in [`.conclave/ops/specs/REGISTRY.md`](.conclave/ops/specs/REGISTRY.md)
  the moment it exists, or `engine audit specs-registry` reports it untraced.

This **overrides the `superpowers:writing-plans` default** of `docs/superpowers/plans/`. That skill
does not know about this project's two-repo split; when it tells you to save a plan under `docs/`,
save it beside its spec in DATA instead. `docs/` in CODE holds `architecture/` and nothing else —
`tests/test_gates.py::test_working_docs_not_in_code` fails the suite if a working doc lands there.

## Origin specs (read for canon before redesigning anything)

All of them live in `.conclave/ops/specs/<NNN-slug>/spec.md`; the full list with statuses is
[`REGISTRY.md`](.conclave/ops/specs/REGISTRY.md).

- **086** unified feedback (notebook) · **084** briefings · **049** forge (agent factory)
- **085** lifecycle simplification · **051** memory architecture
- **089** autonomous pipeline + oracle/verifier signal
- **090** self-improvement L2/L3 (oracle-falsified lesson acquisition) — stub
- **091** deontic duty model (roster engine, Track-B spin-out unit) — design-locked
- **093** self-healing closing loop — in-progress (P1 + P2 merged; the first Conclave component)
- **103** two-repo CODE/DATA split — in-progress (the layout this file describes)
- **104** constitution protocol — proposed (P0 efficacy gate planned, unbuilt)

## Working principles

Carry the seven architecture principles from `VISION.md` §6: file-as-message-bus · cache-over-truth ·
mandatory lifecycle · spec-driven · confidence-graduated authority · never-silent-delete ·
guardrails-as-first-class.

## Canon-first

This project has dense prior art in VoidPay's specs. Before designing any "new" component, check the
origin specs above and `~/code/vl/ai/ops/specs/`. Execute canon; do not redesign blank-slate.

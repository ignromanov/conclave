---
protocol: compose-roster
version: 1.0.0
description: |
  Facilitation protocol for deriving a fit-for-domain advisor roster from a foreign
  project-context. Forge reasons about what advisory roles a product *needs* and emits a
  justified role-manifest (≥3 roles, each with a project-context-cited rationale). The
  operator approves the manifest; per-role creation then runs via hire.md.
  Invoked by the team.forge router on "compose roster" / "bootstrap a team for <project>" /
  "which advisors does <project> need" signals.
related:
  - hire.md          # downstream: creates one advisor per approved manifest role
  - audit.md         # drift detection over the resulting roster
note: |
  Net-new in spec 097 (C-proof). Role *selection* is a Forge judgment layer, distinct from
  091's deontic norms-composition (validate-norms.py) — the decoupling is by layer, not by
  build-state, so compose-roster is usable whether or not 091 ships.
---

# team.forge — Compose Roster

> Turns a foreign `project-context.md` + `constitution.md` into a **role-manifest** — the set of
> advisors a domain actually needs, each justified from the context. This is the bootstrap step
> *before* hiring: it answers **which** roles, where `hire.md` answers **how** to build one.

## When to Use

- Standing up an advisory team for a **new instance** (a project the engine has not staffed yet).
- The operator says "compose a roster for <project>", "which advisors does <project> need", or
  "bootstrap a team from this project-context".
- NOT for adding a single advisor to an existing roster — that is a direct `hire.md` call.
- NOT for composing deontic norms within hired roles — that is the separate 091 layer.

## What this is (and is not)

| | compose-roster (this protocol) | NOT this |
|---|---|---|
| Layer | **role selection** — which advisors a domain needs | 091 norms-composition (obligation/permission within a role) |
| Mode | Forge **facilitation / judgment** — reasoned derivation from context | a mechanical validator or a copied template roster |
| Output | a `role-manifest.yaml` (proposal) + per-role rationale | hired advisors (that is hire.md, run per manifest row) |
| Authority | proposes; the operator **approves** | the operator does **not** author the content |

## Input

1. **`project-context.md`** — the instance's domain context (what it does, domain concepts, stack,
   constraints, audience). For a foreign target this is **Scout-distilled from the real repo**,
   operator-reviewed for accuracy only — never authored as advisor briefings.
2. **`constitution.md`** — the instance's shared principles (transfers cleanly across domains when
   the value-system is shared, e.g. privacy-first; every *domain anchor* is still new).

> These two files are the **only** inputs. If the manifest cannot be re-derived from them alone,
> the composition is not reproducible — fail the reproducibility check (see Phase 4).

## Phase 1 — Reason about domain needs (facilitation, not validation)

Forge reads the two inputs and reasons, in the open, about the work the product generates:

- **What work does THIS product generate that needs an advisor?** (e.g. a ZIP-schema parser that
  changes when the upstream export format changes → an advisor owns format-resilience.)
- **Which concerns dominate?** Privacy? i18n/community? Client-side perf at scale? Domain
  correctness (e.g. social-graph set math)? Product/UX? Distribution?
- **Where is the risk concentrated?** A concern with high blast-radius or recurring change earns a
  dedicated role; an incidental concern folds into an adjacent one.

This is judgment, not a checklist. The role-set is **genuinely open** — it may not map 1:1 to any
prior instance's roster. Resist re-skinning a known team; derive from *this* context.

## Phase 2 — Derive the role-manifest (≥3 roles)

Produce `role-manifest.yaml`. **≥3 roles.** Each role carries:

```yaml
# role-manifest.yaml — Forge-composed proposal (operator-approved, not operator-authored)
project: <instance name>
derived_from:
  - project-context.md
  - constitution.md
roles:
  - id: <slug>                      # ^[a-z0-9-]+$ (engine advisor create contract)
    role: "<C-level / advisory title>"
    purpose: "<one line: what this advisor owns>"
    domain_anchors:                 # cited FROM project-context — the on-domain grounding
      - "<concept> (project-context.md §<section>)"
    voice_cadence: "<template pack assignment — voice, not body>"
    rationale: |                    # THE PROOF ARTIFACT — why this role, grounded in the context
      <2-4 sentences citing the project-context: what work/concern/risk justifies this role,
       and why it is a distinct seat rather than folded into another.>
  # … ≥2 more roles …
```

Rules:
- **`domain_anchors` must cite the project-context** (section or concept), never generic boilerplate.
- **`rationale` is the proof artifact** — it must be falsifiable against the context, not aspirational.
- **`voice_cadence` is doc-only** — a template assignment ("voice, not body"); the personality well
  is filled at first launch, not here.
- No domain terms borrowed from another instance unless they genuinely appear in *this* context
  (zero-bleed begins at the manifest).

## Phase 3 — Operator approval gate (approval ≠ authoring)

Present the manifest — roles + rationales — to the operator via **AskUserQuestion** (Cardinal
mandatory-approval). The operator **gates** the content (approve / revise / reject per role); the
operator does **not** write the roles, anchors, or rationale. That distinction preserves the
"non-operator-authored" property the composition proof depends on.

- Approve → proceed to Phase 4.
- Revise → Forge re-derives the flagged rows from the context (not from operator-supplied content).
- Reject → stop; the context may be too thin to staff (surface what is missing).

## Phase 4 — Hand off to hire + verify

1. **Per approved role**, run `hire.md` Phase 3 onward:
   `engine advisor create` → `engine register advisor` → `python -m engine briefing build <id>`.
   Point the roster/`CONCLAVE_AI_ROOT` at the instance. Note that `hire.md` Phase 3 defers the
   briefing build until after the advisor's First Launch — building it earlier overwrites the
   `AWAITING_FIRST_LAUNCH` sentinel and silently skips First Launch entirely.
2. **Zero-bleed check** — each advisor's first-session opening is judged on-domain with **zero
   foreign-instance bleed** by `exec.themis-judge` (judge ≠ producer — a different run than whatever
   generated the openings).
3. **Reproducibility check** — re-run Phase 1–2 from `project-context.md` + `constitution.md`
   alone; confirm an **equivalent** role-manifest rationale. A one-off that cannot be reproduced
   is not a composition.

## Honesty commitments

- **Approval ≠ authoring.** The operator gates; Forge composes. If the operator dictates the roles,
  the proof is void.
- **The role-set is genuinely open.** A real domain may want a data-privacy advisor, a frontend/PWA
  architect, an i18n/community advisor, a product advisor — or cuts that match no prior roster. The
  proof is the cited rationale + zero-bleed, **not** matching a known shape.

## Anti-Patterns

| Pattern | Why Bad | Fix |
|---------|---------|-----|
| Copying a prior instance's roster | Re-skin, not composition — fails the proof | Derive each role from *this* context |
| Rationale without a project-context citation | Unfalsifiable; not a proof artifact | Cite the concept/section that justifies the role |
| Operator authoring the manifest | Voids "non-operator-authored" | Operator approves/revises; Forge composes |
| Treating this as a validator | It is judgment, not a pass/fail gate | Reason in the open about domain needs |
| Pulling in 091 norms-composition | Wrong layer; blocks needlessly | Role selection only; norms are downstream |
| <3 roles | Below the composition floor | Re-examine concerns; a real product needs ≥3 seats |

## Protocol changelog

### 1.0.0 — spec 097 (C-proof)
- Net-new facilitation protocol: foreign project-context → justified role-manifest → approval → hire.
- Establishes the role-selection layer, decoupled by-layer from 091 norms-composition.
- Two honesty commitments (approval ≠ authoring; role-set genuinely open) + zero-bleed/reproducibility gates.

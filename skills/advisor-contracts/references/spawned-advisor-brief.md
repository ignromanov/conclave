---
contract: spawned-advisor-brief
version: 1.0.0
propagation: runtime-inject
applies-to: advisors in autonomous mode (spec 089)
---

# Spawned Advisor Brief

Context packet injected via `prompt=` at spawn. Replaces `/conclave:start` for an advisor running
in autonomous mode. The orchestrator assembles this packet programmatically before dispatch.

## Required fields (orchestrator fills)

| Field | Type | Notes |
|-------|------|-------|
| `task` | string | One-sentence task statement |
| `autonomy_level` | L0-L4 | From intake.md trust-register read (spine §1) |
| `ac_contract_ref` | path | Path to the AC contract for this run |
| `hot_md_slice` | string ≤100w | Relevant excerpt from `agent-memory/hot.md` |
| `briefing_focus` | string ≤50w | Key context from advisor briefing (pre-extracted) |
| `gh_ref` | string | GH issue or PR reference for this task |
| `phase_artifacts` | path[] | Artifacts produced so far (phase seals + outputs) |
| `candidate_id` | string | Stable ID for this candidate (e.g., `T1-a`) |
| `file_ownership` | path[] | Files the advisor may mutate this run |
| `do_nots` | string[] | Explicit exclusions for this dispatch |

## Omit rule

Do NOT include full `product.md`, architecture files, or spec text in the packet. Use refs
only (`ac_contract_ref`, `gh_ref`, `phase_artifacts`). The orchestrator assembles from refs —
it never copies full documents into the packet.

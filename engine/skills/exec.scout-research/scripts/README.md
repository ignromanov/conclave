# exec.scout-research hook-evaluator scripts (spec 089, D31)

Python 3.13 · pydantic v2 + ruamel (reuse the 084/086 substrate). These make the D31 research
triggers **machine-checkable** — without them the triggers are un-evaluable prose. The spine
(`workflow.autopilot/protocols/spine.md` § 7) calls them at the P2/P6/P7 hooks; the scout role
calls the saturation/validate ones internally (round8 § 5).

| Script | Phase / caller | Input | Output | Purpose |
|--------|----------------|-------|--------|---------|
| `scout-verify-citations.py` | P6 citation-grounding hook | scout output YAML (`candidates[].evidence[]`) | per-claim `{veracity: settled\|contested\|unknown}` + exit code | Confirms each cited claim is reachable + claim-present; phantom/unreachable → `unknown` (a BLOCKER `unknown` triggers the bounded web-fetch, AC23). |
| `scout-saturation-check.py` | P7 futility hook + scout STOP rule | last-N findings (text) | `{saturated: bool, max_ngram: float}` + exit | n-gram overlap >0.80 over last 2-3 findings → saturated; hard-stops a wave / arms the P7 hook (AC24). |
| `scout-output-validate.py` | P1/P2/P6 — before any consumer reads scout output | scout output YAML | `{valid: bool, stripped: [...]}` + exit | Injection-hardening (AC27/R4): strips instruction-override patterns from the advisor-writable-wiki-sourced artifact before planner/judge consume it. |
| `scout-ac-blocking-detector.py` | P2 spec-enrichment hook | `contract.md` AC entries + scout `contested[]`/`unknown[]` | `{ac_blocking: [tokens]}` + exit | A P1 contested/unknown item is **AC-blocking** when it is referenced by an unsealed AC entry → fires the P2 scout lookup (AC22). |
| `scout-criterion-absent-matcher.py` | P7 futility hook | failing criterion id + P1 scout artifact | `{absent: bool}` + exit | Criterion **absent from the P1 artifact** = knowledge-gap candidate (not execution-gap) — one of the four P7-hook conditions (AC24). |

## Exit-code convention (ADR-0003)

`0` = predicate FALSE / clean (no action) · `3` = predicate TRUE / finding (fire hook) ·
`1` = usage/IO/validation error · `2` = missing required input.

This lets the spine wire a hook as `script … ; if [ $? -eq 3 ]; then fire_hook; fi` without
parsing stdout — the same file-as-message-bus discipline as the lifecycle scripts.

## "Non-mechanical" proxy

The P7 hook's "non-mechanical" condition is operationalized in the spine (spine.md § 8): a failing
finding with `category ∈ {lint, format, syntax}` is **mechanical** (no re-research); any other
category is a re-research candidate. `scout-criterion-absent-matcher.py` + the finding `category`
field are both machine-readable, so the full P7 predicate is evaluable without human judgment.

## Status

Core logic (n-gram, citation-presence, injection-pattern strip, AC-reference match) is implemented
and runnable. The pydantic models for scout I/O are shared with `scripts/scout/scout-schema-validate.py`
(round8 § 5) — the Phase-0 plan consolidates them into one `scout/schema.py`.

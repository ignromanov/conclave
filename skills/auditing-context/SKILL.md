---
name: auditing-context
description: Use when you need to know what occupies an agent's context window before trimming or debugging it — questions like "why is context so full", "what's using my tokens", auditing skills/agents/MCP servers/memory files after adding or removing any of them, or explaining a /context percentage. Also use instead of estimating hook, skill, or agent token cost by hand, eyeballing a rounded percentage, or grepping a transcript for markers.
---

# Auditing Context

## Overview

`audit_context.py` combines two sources of truth to show exactly what occupies
a session's context, with paths: the harness's own `/context` token counts
(authoritative, per skill/agent/MCP-tool/memory-file) and the transcript JSONL
(per-message detail, calibrated against `/context`'s `Messages` figure, not
guessed). Never estimate context cost by hand when this tool exists — run it.

## Getting `/context` into a file

The transcript does NOT persist `/context` output — it only records that the
command ran, never the table. You must capture it yourself, one of two ways:

| Method | How | Tradeoff |
|---|---|---|
| **Interactive (preferred)** | User runs `/context` in the live session; you write that block verbatim to a file | Live numbers, real `Messages` count, real attached MCP servers |
| **Headless** | `claude -p "/context" --output-format text > baseline.md` | Fresh session (`Messages` is trivial) — good for A/B comparing config changes. MCP servers attach non-deterministically: two identical runs can differ by tens of thousands of tokens of MCP schemas, one showing none at all. Never treat a headless baseline as complete for MCP coverage |

## Usage

```bash
python3 audit_context.py --context /path/to/context.md --transcript /path/to/session.jsonl --format terminal
```

`--format` is `terminal` (default), `markdown`, or `html`. `--out FILE` writes
to a file instead of stdout; `--top N` caps the item list. Run `--help` for
the rest.

Without `--context`, only the conversation breaks down (no per-skill,
per-agent, per-MCP-tool, or per-memory-file numbers, cruder ratio) — the
tool warns about this itself.

## Common Mistakes

| Mistake | Why it's wrong |
|---|---|
| Reaching for the `context-management` skill instead | It reports one aggregate percentage; its own docs reference paths and function names that no longer match the real API |
| Estimating hook cost from the transcript's JSON envelope | Only `hookSpecificOutput.additionalContext` (or non-JSON stdout) is actually injected — the envelope overstates cost by ~14x |
| Estimating skill/agent cost from the truncated skill-listing text | Per-item costs come from `/context` only — the listing view undercounts (seen 3.7x low) |
| Grepping the transcript for a marker string | Any search matches your own grep command, echoed back in the transcript |
| Assuming `/context` output lives in the transcript | It doesn't — capture it explicitly per the table above; this is why `--context FILE` is required for full detail, and why this tool never re-adds transcript scraping |
| Summing rounded per-row values (`< 20`, `~50`) as an exact total | Row values are upper bounds; the category total from `/context` is truth — row sums can exceed it |
| Trusting one headless `/context` run as complete | MCP schemas can attach non-deterministically; a silent omission looks identical to "no MCP servers configured" |

## Reading the output

Deferred rows (categories ending "(deferred)", e.g. "MCP tools (deferred)")
are listed but are NOT part of used context — they load only if a tool is
actually fetched. Don't add them to the used total.

The category rows won't reconcile exactly to the header total either: each row
is independently rounded to one decimal in "k" units, so they can sum a few
thousand tokens over. Report categories as measured; don't derive per-category
percentages from the header total and present them as shares of a whole.

Individual row values are buckets (`< 20`, `~50`), not measurements. Removing one
skill labelled `< 20` moved a 41k header to 40.9k — the two granularities cannot
be reconciled, so the cost of a single entry is unknowable from `/context` alone.
State the bucket, or measure a before/after delta on something large enough to
clear the rounding. Don't convert a description's character count to tokens and
present that as the cost either.

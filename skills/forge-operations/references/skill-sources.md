---
kind: skill-allowlist
version: 1.0.0
---

# Allowed skill sources

`engine skill install` will fetch a skill package **only** if its `owner/repo` appears below.
Everything else is refused, and the refusal names the manual command so the decision comes back
to the operator instead of disappearing.

This file is the enforcement surface, not a guideline: `enginelib.skill_install.is_allowed`
reads it, and no agent is asked to remember its contents. An empty list is valid and means
refuse everything — the safe default, and what a fresh install ships with until an operator
decides otherwise.

## Allowed sources

- `anthropics/*`
- `vercel-labs/agent-skills`
- `obra/superpowers`

## Entry format

| Form | Matches |
|---|---|
| `owner/repo` | exactly that repository |
| `owner/*` | every repository of that owner, and nothing else |

`owner/*` is an owner match, not a prefix match — an `anthropics/*` entry does **not** admit
`anthropics-evil/x`. A package spec is `owner/repo` or `owner/repo@skill`; anything carrying
whitespace, extra path segments or shell syntax fails the shape check before membership is
even considered, and `install_command` builds an argv list rather than a shell string.

Pinned by `tests/enginelib/test_skill_install.py::test_shipped_allowlist_entries_are_well_formed`.

## Changing this list

Adding an owner here grants every future package under it, installed without asking. Prefer a
specific `owner/repo` over a wildcard unless the owner is one you already trust with arbitrary
code on this machine.

> **2026-08-09 (spec 112 T2).** Initial three, chosen by the operator: Anthropic's own skills,
> the Vercel Labs collection, and superpowers — the sources already present in this environment.

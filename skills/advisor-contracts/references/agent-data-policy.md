---
contract: agent-data-policy
appliers: [all advisors]
version: 2.0.0
propagation: hire-template
stages: [implement, deliver]
tiers: [work]
task_types: [dev, content, research, review, advisory]
binding: required
last_reviewed: "2026-08-12"
---

# Agent Data Policy

> **Purpose**: Where data lives and how agents read/write it.
> **Approved**: 2026-03-17 (Meeting #6). **v2.0** 2026-05-22 — spec 085: stripped
> sections obsoleted by spec 051 (auto-generated briefings) and spec 074
> (foundations + domain knowledge migrated to the wiki).

---

## Where data lives

| Data | Home | Access |
|------|------|--------|
| Dev tasks, bugs, features, strategy, grants, ops | GitHub Issues (both repos) | per `github-issues-protocol.md` |
| Advisor briefings | `agent-memory/advisors/briefings/<id>.md` | **auto-generated** by `engine briefing build` — read-only, never hand-edited (spec 051) |
| Sessions / decisions / mentions | `agent-memory/advisors/{sessions,decisions,mentions}/` | written only via `engine session close` / `engine file decision` / `engine mention create` |
| Cross-agent live state | `agent-memory/hot.md` | `engine memory hot-append` (the wiki mirror was retired with spec 099 and has no replacement) |
| Architecture registries | `.ai/architecture/*.md` | code-coupled — edited directly after code changes |
| Process artifacts | `.ai/ops/` (specs, meetings, decisions, handoffs) | edited directly |
| Domain knowledge (architecture trade-offs, strategy, security findings, competitive analysis) | **wiki** (the knowledge wiki, `knowledge.wiki_path` in roster.yaml) | `/wiki:capture`, `/wiki:browse`, `/wiki:query` |

**Rule**: domain knowledge belongs in the wiki, not `.ai/`. `.ai/` holds only process
artifacts + code-coupled architecture registries. Writing research / strategy / security
narratives into `.ai/` is an anti-pattern (see CLAUDE.md).

---

## `.ai/` Repository Privacy

`.ai/` (the private ops repo, `github.ai_repo` in roster.yaml) is a **private**
repository. Strategic, competitive, and grant information can live here safely.

**Never in `.ai/` (regardless of repo visibility)**:
- API keys, RPC endpoint URLs with auth tokens, private keys
- Exploit PoC code, decompression bomb payloads
- Bypass technique details → use GitHub Security Advisories (GHSA)
- PII (wallet addresses linked to real identities)

---

## Architecture Staleness Detection

Every file in `.ai/architecture/` carries a header on line 3:

```markdown
> **Last updated**: YYYY-MM-DD — [what changed]
```

After code changes, the validation workflow checks:
- Component added/removed → `ui-index.md` update required
- Slice added/removed → `fsd-registry.md` update required
- Store added/modified → `data-flow.md` update required

Flag if an architecture file's `Last updated` is older than the current commit.
Non-blocking, but visible in the `/conclave:done` checklist (item 5).

---

## INDEX.md Convention

Every top-level `.ai/` directory has an `INDEX.md`:
- Adding a file → update INDEX.md. Removing a file → update INDEX.md.
- INDEX.md = lightweight table of contents, not documentation.
- The owner of the directory owns its INDEX.md.

---

## KB Updates routing (post-meeting)

After writing meeting minutes, the facilitator role appends a `## KB Updates Required`
section tagging the responsible advisor:

```markdown
## KB Updates Required
- [ ] architecture/data-flow.md — [decision summary] ← @<advisor-id>
- [ ] wiki: strategy/positioning — [decision summary] ← @<advisor-id>
```

On the next session, the tagged advisor executes the update — architecture registries
directly, domain knowledge via `/wiki:capture`. The operator confirms via commit.

---

## Rules that fire on a command, not on a file

Every lane above routes a piece of knowledge to a **file** — a registry, an issue, the wiki.
All of them are reached by opening something. A rule about how to *run a command* has no such
moment: nobody opens a file before typing `gh issue create`, so a rule that lives in a document
arrives only for the sessions that happened to read the document.

The only carrier that fires on a command is a **`PreToolUse` hook**. What follows is measured
against the installed CLI (2.1.280) with a scratch hook on `Bash`, because a contract that
asserts a mechanism it has not executed is the defect GH#315 exists to close — and the fix
first proposed for it prescribed exactly such an assertion.

| what the hook returns | what reaches the agent |
|---|---|
| plain text on stdout, exit 0 | **nothing** |
| `hookSpecificOutput.additionalContext`, exit 0 | **nothing** |
| `hookSpecificOutput.permissionDecision: "deny"` + `permissionDecisionReason` | the command does **not** run, and the reason is delivered verbatim: `PreToolUse:Bash hook error: <reason>` |

The hook itself ran in all three cases — it wrote the payload it received to disk — so the two
empty rows are about delivery, not about firing. The payload carries the command as
`tool_input.command`.

**Consequence for anyone building one:** the enforcing channel is the only channel. There is no
measured way to whisper a note to an agent from a `PreToolUse` hook; a rule worth a hook is a
rule worth denying on, and one not worth denying on belongs in a contract with **no** claim of
enforcement attached. Both halves of that were got wrong at once in
`github-issues-protocol.md`, which claimed a blocking hook that no generation ever shipped.

**The matcher is the hard part, and command text is not a command.** The one hook of this kind
that has been in service anywhere logged three false positives, each paid for by a wasted run:
the word it was matching appeared as a path segment, as a filename being `cat`-ed, and inside a
`grep` pattern — where an escaped `\|` in a BRE alternation was read as a shell pipe, which is
how that last one survived its own first repair. Match on invocation shape (command position,
after `npm run`, and so on), never on vocabulary, and keep the scenarios in a test beside the
hook.

# Conclave memory schema (`ops/` + `agent-memory/`)

> Generic, project-agnostic taxonomy of the page types Conclave reads and writes in a
> consumer project's DATA root (`.conclave/`). The authoritative, machine-checked source is
> `engine/scripts/briefing/schema.py` (pydantic v2 models) — this document is its human-readable
> mirror. When the two disagree, `schema.py` wins.

## Conventions

- **Frontmatter is the source of truth.** Every page carries YAML frontmatter; directory location is
  advisory only (it is lost when a page is promoted or copied into the wiki), so `type` is **required**
  on every page.
- **snake_case keys** throughout (no hyphens in frontmatter keys).
- **`schema_version`** is a strict integer (`1`) — an internal iteration counter, not a public SemVer.
  String coercion (`"1"`) is rejected.
- **`created`** is a full timestamp (`YYYY-MM-DDTHH:MM:SS`) where same-day ordering matters
  (`session`, `handoff`, `meeting`) and a date (`YYYY-MM-DD`) otherwise.
- `brief` is intentionally **not** a schema'd type — it is a compiled artifact with no frontmatter
  contract.

## Page types

| `type` | Location | Mutability | Required fields (beyond `type` + `schema_version`) |
|--------|----------|------------|-----------------------------------------------------|
| `spec` | `ops/specs/###-*/spec.md` | mutable (`updated`) | `status`, `id`, `created`, `updated`, `owner` |
| `session` | `agent-memory/advisors/sessions/` | immutable (no `updated`) | `owner`, `created` |
| `decision` | `agent-memory/advisors/decisions/` | mutable | `status`, `owner`, `created`, `confidence`, `contested` |
| `mention` | `agent-memory/advisors/mentions/` | mutable (`status`) | `source_session`, `target_advisor`, `status`, `created` |
| `feedback` | `agent-memory/advisors/feedback/` | mutable (`status`) | `severity`, `target`, `status`, `created` |
| `handoff` | `ops/handoffs/` | mutable (`status`) | `from`, `to`, `created`, `priority`, `status` |
| `retro` | `ops/retros/` | mutable | `spec`, `owner`, `created` |
| `open-question` | `ops/open-questions/` | mutable (`status`) | `status`, `opened`, `owner` |
| `meeting` | `ops/meetings/` | immutable | `attendees`, `created` |

### Enumerations

- `spec.status`: `proposed` · `approved` · `in_progress` · `done` · `archived` · `cancelled`
- `decision.status`: `proposed` · `approved` · `promoted` · `superseded` · `rejected`
- `mention.status`: `open` · `resolved`
- `feedback.status`: `open` · `resolved` · `archived` · `wontfix`
- `open-question.status`: `open` · `answered` · `abandoned` · `superseded`

### Common optional fields

Most types also accept: `related` (list of links), `tags`, `aliases`, `sources`, `retention`.
Type-specific optionals include `decision.promoted_to`, `handoff.state_at_handoff`,
`retro.what_worked`/`retro.what_didnt`, `open-question.answered_by`, and `meeting.agenda`/`meeting.outcomes`.

## Notes

- `handoff.from` is serialized as `from` but is a reserved word in some loaders — the model aliases it
  as `from_` internally (`populate_by_name`).
- This schema is shipped with the plugin and scaffolded into each consumer's `.conclave/` by
  `/conclave:init`; advisors and executors read it at session start to validate the pages they emit.

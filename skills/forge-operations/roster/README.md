# `roster/` — the engine-owned duty base (spec 091)

The deontic duty registry's **base layer**: JSON-Schemas, the KAD duty template, and the
domain-agnostic missions and norms every Conclave instance inherits. Composed at projection time
with each agent's self-written duties (which live in DATA, never here).

**This tree ships to every consumer.** It is engine, not instance. Nothing instance-specific may
land here — no advisor ids, no repo slugs, no product names. That constraint is a test, not a
convention: `tests/test_gates.py::test_roster_base_is_domain_agnostic` fails the suite on a hit.

Norms attach to abstract roles (`all`, `kind:advisor`, `kind:executor`); concrete roles inherit
them. Specialisation is self-written by the agent that holds the role.

| Path | Holds |
|------|-------|
| `schema/*.schema.json` | generated from `enginelib/roster/model.py` — do not hand-edit |
| `templates/DUTY.md` | KAD scaffold for a self-written duty |
| `missions.base.yaml` | universal missions |
| `norms.base.yaml` | universal norms on abstract roles |

Logic lives in `engine/scripts/enginelib/roster/`; the CLI is `python -m engine duty`.

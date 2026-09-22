"""status/words.py — every human word this projection prints, in one module. Pure.

Rule 10 says the surface speaks the operator's language and that the language is
**instance configuration**. Rule 11 says one model feeds three printers. Until this
module existed the two rules contradicted each other in the code: `SectionResult`
carried finished Russian prose (`noun="фидбек-записей resolved"`, assembled in the
gathering adapter), so the "language of the surface" was welded into the read-model and
a second printer could not have chosen differently. `render_terminal.quantity` even
documented itself as "the ONLY place it is worded" while receiving a noun that had
already been worded one layer down.

So the model now carries `Phrase` — a catalog key plus its parameters — and every word
lives here. English is the canonical catalog and the fallback; an instance that wants
another language selects one with `roster.yaml: project.language`.

**Why English is canonical rather than merely available.** A key absent from `EN` is a
programming error and raises; a key absent from a translation is translation lag and
silently falls back to English. That asymmetry is what makes an untranslated phrase a
readable row instead of a crash, and a mistyped key a test failure instead of a row
that quietly says nothing.

Identifiers, paths, commands and registry status literals are NOT translated — rule 10
splits by token class, and `PR`, `done`, `resolved`, `ls-remote` stay as written in
every catalog. `proof.literal` exists for a proof string that is nothing but such
tokens, so it can pass through without being copied into each catalog and drifting.
"""
from __future__ import annotations

from collections.abc import Mapping

from enginelib.status.model import Phrase

#: The canonical catalog. Every key the projection can emit appears here, and
#: `tests/enginelib/test_status_words.py` fails if a `Phrase(...)` in the tree names one
#: that does not. Templates use `str.format` fields; a `{name}` here must match a
#: parameter the builder actually passes, which the same test checks by rendering.
EN: dict[str, str] = {
    # --- slot names -------------------------------------------------------
    # The join between the glance row and its work section (state-report §Shape).
    "slot.handoffs": "handoffs",
    "slot.feedback": "feedback",
    "slot.specs": "specs",
    "slot.queue": "queue",
    "slot.p0": "p0",
    "slot.branches": "branches",
    "slot.ci": "CI",
    # --- what each count counts -------------------------------------------
    # Rule 5: a bare number is noise, so every `Count` names its unit. `resolved` and
    # `p0` are registry literals and stay put in every language.
    "noun.handoffs": "handoffs open",
    "noun.feedback": "feedback records resolved",
    "noun.specs": "specs with computable acceptance",
    "noun.queue": "issues open instance-wide{floor}",
    "noun.p0": "p0 blockers instance-wide{floor}",
    "noun.branches": "branches need action",
    "noun.measured_total": "across measured sections",
    #: An incomplete mosaic states the incompleteness in the noun, where the number is
    #: read — not in the glyph, which means content severity (rules 7a/7b).
    "suffix.floor": " (floor, not total)",
    # --- rule 6: an instrument that did not run says so, in words ----------
    "absent.handoffs_dir": "no such directory: {dir}/",
    "absent.feedback_index": "index not built (ops/feedback/_index/index.jsonl is missing)",
    "absent.mosaic_none": "not one snapshot was taken ({keys})",
    "absent.roster_empty": "the roster is empty",
    "absent.branches_gh": (
        "gh did not answer — without PR state the join does not exist, and Step 4 "
        "names every remaining signal wrong on its own"
    ),
    "absent.branches_git": "not a git repository, or no default branch: {root}",
    "absent.specs_dir": "no such directory: ops/{dir}/",
    "absent.specs_short_scan": (
        "the scanner returned {scanned} of {on_disk} specs on disk — the ratio would "
        "be taken over an undeclared subset"
    ),
    "absent.ci": "not wired — statusCheckRollup, nothing projects it (plan 057 T11)",
    "shard.no_snapshot": "no snapshot taken: agent-memory/gh-cache/{advisor}.md",
    # --- rule 5: every count is one hop from its source --------------------
    #: A proof made of nothing but identifiers. It is not translated because there is
    #: nothing in it to translate, and copying it per catalog is how it would drift.
    "proof.literal": "{text}",
    "proof.handoffs": "ops/handoffs/*.md — frontmatter status not in the terminal set",
    "proof.mosaic": (
        "union agent-memory/gh-cache/{{{keys}}}.md — {count} snapshots, "
        "oldest {stamp}{tail}"
    ),
    "proof.mosaic_missing": "; without a snapshot: {keys}",
    "proof.branches": (
        "git for-each-ref refs/heads × gh pr list --state all --limit {limit} "
        "× git ls-remote --heads origin{tail}"
    ),
    "proof.branches_no_remote": (
        " (ls-remote did not answer — branch state on the server was not read)"
    ),
    #: The partition in full, zeros included: rule 3 states success in words, and
    #: "0 with no acceptance block" is what tells a reader the instrument looked.
    "proof.specs": (
        "ops/specs/*/spec.md — acceptance block: {measured} computable · "
        "{no_checkboxes} without checkboxes · {no_acceptance} without an acceptance "
        "block · {unowned} without an owner field"
    ),
    "proof.measured_total": "derived: sum of this projection's measured sections",
    # --- the printer's own connective tissue -------------------------------
    "quantity.measured": "{value}{denominator} {noun}{freshness}",
    "quantity.denominator": " of {of}",
    "quantity.absent": "— {reason}",
    "work.proof": "→ proof: {proof}",
    "surface.state": "state",
    # --- rule 7: age renders beside the verdict, as evidence ---------------
    # One phrase per axis: the axis is what makes the two readable as different facts
    # rather than as one number printed twice.
    "freshness.snapshot.stale": "snapshot {age} old",
    "freshness.movement.stale": "queue has not moved for {age}",
    "freshness.snapshot.unknown": "snapshot undated",
    "freshness.movement.unknown": "movement not recorded",
    "age.hours": "{count}h",
    "age.days": "{count}d",
    # --- warnings, which go to stderr and are not part of the object -------
    "warn.glance_overflow": (
        "[status] WARNING: {count} sections against a ceiling of 12 lines — "
        "they must be grouped, not cut"
    ),
    "warn.cluster_budget": (
        "[status] WARNING: {count} deviations against a cluster budget of {cap} "
        "(rule 2) — they must be grouped"
    ),
}

#: One instance's language. A key missing here falls back to `EN` on purpose: an
#: untranslated row is legible, and a translation that must be complete before it can
#: ship is a translation that never ships.
RU: dict[str, str] = {
    "slot.handoffs": "хендофы",
    "slot.feedback": "фидбек",
    "slot.specs": "спеки",
    "slot.queue": "очередь",
    "slot.branches": "ветки",
    "noun.handoffs": "хендофов открыто",
    "noun.feedback": "фидбек-записей resolved",
    "noun.specs": "спек с вычислимой приёмкой",
    "noun.queue": "issue открыто по инстансу{floor}",
    "noun.p0": "p0-блокеров по инстансу{floor}",
    "noun.branches": "веток требуют действия",
    "noun.measured_total": "по измеренным секциям",
    "suffix.floor": " (пол, не итог)",
    "absent.handoffs_dir": "каталога нет: {dir}/",
    "absent.feedback_index": "индекс не собран (ops/feedback/_index/index.jsonl нет)",
    "absent.mosaic_none": "ни один снимок не снят ({keys})",
    "absent.roster_empty": "ростер пуст",
    "absent.branches_gh": (
        "gh не ответил — без состояния PR join не существует, а каждый оставшийся "
        "сигнал Step 4 называет неверным поодиночке"
    ),
    "absent.branches_git": "не git-репозиторий или нет дефолтной ветки: {root}",
    "absent.specs_dir": "каталога нет: ops/{dir}/",
    "absent.specs_short_scan": (
        "сканер вернул {scanned} из {on_disk} спек на диске — доля считалась бы по "
        "необъявленному подмножеству"
    ),
    "absent.ci": "не подключено — statusCheckRollup, ничего его не проецирует (plan 057 T11)",
    "shard.no_snapshot": "снимок не снят: agent-memory/gh-cache/{advisor}.md",
    "proof.handoffs": "ops/handoffs/*.md — frontmatter status не в терминальном наборе",
    "proof.mosaic": (
        "union agent-memory/gh-cache/{{{keys}}}.md — {count} снимков, "
        "старейший {stamp}{tail}"
    ),
    "proof.mosaic_missing": "; без снимка: {keys}",
    "proof.branches": (
        "git for-each-ref refs/heads × gh pr list --state all --limit {limit} "
        "× git ls-remote --heads origin{tail}"
    ),
    "proof.branches_no_remote": (
        " (ls-remote не ответил — состояние веток на сервере не снято)"
    ),
    "proof.specs": (
        "ops/specs/*/spec.md — блок приёмки: {measured} вычислимо · "
        "{no_checkboxes} без чекбоксов · {no_acceptance} без блока приёмки · "
        "{unowned} без поля владельца"
    ),
    "proof.measured_total": "производное: сумма измеренных секций этой проекции",
    "quantity.measured": "{value}{denominator} {noun}{freshness}",
    "quantity.denominator": " из {of}",
    "quantity.absent": "— {reason}",
    "work.proof": "→ пруф: {proof}",
    "surface.state": "состояние",
    "freshness.snapshot.stale": "снимку {age}",
    "freshness.movement.stale": "очередь не двигалась {age}",
    "freshness.snapshot.unknown": "снимок не датирован",
    "freshness.movement.unknown": "движение не зафиксировано",
    "age.hours": "{count}ч",
    "age.days": "{count}д",
    "warn.glance_overflow": (
        "[status] WARNING: {count} секций при потолке в 12 строк — "
        "их надо группировать, а не резать"
    ),
    "warn.cluster_budget": (
        "[status] WARNING: {count} отклонений при кластерном бюджете {cap} "
        "(rule 2) — их надо группировать"
    ),
}

Catalog = Mapping[str, str]

#: Spellings an operator plausibly writes in `roster.yaml`. Anything unrecognised —
#: including an empty or absent key — is English, because a surface that refuses to
#: render on a typo is worse than one that renders in the canonical language.
_CATALOGS: dict[str, Catalog] = {
    "english": EN,
    "en": EN,
    "russian": RU,
    "ru": RU,
    "русский": RU,
}


def catalog_for(language: str) -> Catalog:
    """The catalog for a configured language name. Unrecognised → the canonical one."""
    return _CATALOGS.get(language.strip().casefold(), EN)


def say(phrase: Phrase, catalog: Catalog = EN) -> str:
    """One phrase, worded.

    A parameter that is itself a `Phrase` is resolved first, which is what lets an
    optional tail ("; without a snapshot: …") or an optional suffix (" (floor, not
    total)") be a translatable phrase rather than a pre-worded string the builder
    smuggles in — the exact move this module exists to stop.
    """
    template = catalog.get(phrase.key)
    if template is None:
        template = EN.get(phrase.key)
    if template is None:
        raise KeyError(
            f"no phrase {phrase.key!r} in the canonical catalog — a key absent from EN "
            "is a typo or an unregistered phrase, never an operator condition"
        )
    resolved = {
        name: say(value, catalog) if isinstance(value, Phrase) else value
        for name, value in phrase.params.items()
    }
    return template.format(**resolved)

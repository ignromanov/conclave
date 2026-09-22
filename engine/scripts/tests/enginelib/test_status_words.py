"""Rule 10 — the surface speaks one language, and the default is English.

The projection printed Russian because the words were literals in the gathering
adapter: `noun="фидбек-записей resolved"` was assembled in `engine/cmd/status.py` and
handed to the printer already worded, so `roster.yaml: project.language: English` — a
key with no reader anywhere in the tree — could not have changed a character of it.

These tests pin both halves of the repair: that the model carries keys rather than
prose, and that the one place a language is chosen is the adapter's single read of the
roster. The completeness tests exist because a catalog is exactly the kind of artefact
that rots silently: a key nobody resolves and a template missing a parameter both
render as nothing going wrong until an operator sees a blank cell.
"""
from __future__ import annotations

import ast
import pathlib
import string
from datetime import timedelta

import pytest

from engine.cmd import status as status_cmd
from enginelib.status.model import Absent, Count, Freshness, Phrase, SectionResult
from enginelib.status.reduce import rank_sections
from enginelib.status.render_terminal import glance, work
from enginelib.status.words import EN, RU, catalog_for, say

ENGINE_SCRIPTS = pathlib.Path(status_cmd.__file__).resolve().parents[2]

#: Every module that may construct a `Phrase`. Tests are excluded on purpose: they
#: invent throwaway keys against a throwaway catalog, which is itself a property under
#: test (a printer that can render a catalog it does not ship).
PRODUCERS = (
    ENGINE_SCRIPTS / "enginelib" / "status",
    ENGINE_SCRIPTS / "engine" / "cmd" / "status.py",
)


def _phrase_keys_in(path: pathlib.Path) -> set[str]:
    """Every string literal passed as `Phrase`'s first argument in one file."""
    found: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
        if name != "Phrase" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.add(first.value)
    return found


def _produced_keys() -> set[str]:
    keys: set[str] = set()
    for target in PRODUCERS:
        files = sorted(target.rglob("*.py")) if target.is_dir() else [target]
        for path in files:
            keys |= _phrase_keys_in(path)
    return keys


def _fields(template: str) -> set[str]:
    return {
        name for _, name, _, _ in string.Formatter().parse(template) if name is not None
    }


# --------------------------------------------------------------------------
# The default, and how an instance changes it
# --------------------------------------------------------------------------


def test_the_default_language_is_english() -> None:
    """An instance that configures nothing gets the canonical catalog.

    `roster_get` returns its default for a missing file and a missing key alike, so
    this is the state of every fresh install — and the state this instance was in
    while the surface printed Russian.
    """
    assert catalog_for("") is EN
    assert catalog_for("English") is EN
    assert say(Phrase("slot.feedback")) == "feedback"


@pytest.mark.parametrize("spelling", ["Russian", "russian", "ru", "русский", " RU "])
def test_a_configured_language_is_recognised_however_it_is_spelled(spelling: str) -> None:
    assert catalog_for(spelling) is RU


def test_an_unrecognised_language_falls_back_to_english_rather_than_failing() -> None:
    """A typo in `roster.yaml` must not take the surface down.

    The alternative — raise on an unknown name — makes a status command that refuses
    to report the instance's state because of a setting that changes nothing
    measurable about it.
    """
    assert catalog_for("Klingon") is EN
    assert catalog_for("Ænglisc") is EN


def test_the_adapter_reads_the_language_from_the_roster(monkeypatch, tmp_path) -> None:
    """The one read, in the adapter, where the I/O belongs.

    Mutation: delete the `roster_get` call and default `words` to `EN` in the printer
    instead — this reddens, because the Russian instance stops being able to choose.
    """
    seen: list[str] = []

    def fake_roster_get(key: str, default: str = "") -> str:
        seen.append(key)
        return "Russian"

    monkeypatch.setattr("enginelib.roster.roster_get", fake_roster_get)
    monkeypatch.setattr("enginelib.paths.repo_root", lambda: tmp_path)
    monkeypatch.setattr(status_cmd, "_gh_sections", lambda root: ())
    monkeypatch.setattr(
        status_cmd,
        "_branches_section",
        lambda root: SectionResult(
            Phrase("slot.branches"),
            Absent(reason=Phrase("absent.branches_gh")),
            verdict="unknown",
        ),
    )

    args = type("Args", (), {"advisor": "", "glance": True})()
    assert status_cmd._status(args) == 0
    assert "project.language" in seen


# --------------------------------------------------------------------------
# One projection, two surfaces
# --------------------------------------------------------------------------


def _section() -> SectionResult:
    return SectionResult(
        name=Phrase("slot.queue"),
        measurement=Count(
            value=164,
            noun=Phrase("noun.queue", {"floor": ""}),
            proof=Phrase("proof.literal", {"text": "agent-memory/gh-cache/*.md"}),
        ),
        freshness=(
            Freshness(axis="snapshot", verdict="stale_warn", age=timedelta(days=5)),
        ),
    )


def test_one_model_renders_in_either_language_without_being_rebuilt() -> None:
    """Rule 11's actual promise, which the pre-`Phrase` model could not keep.

    The same `SectionResult` instance goes to the printer twice. Nothing about the
    projection is re-gathered, re-derived or re-worded between the two calls — which
    is only possible because no field of it holds a sentence.
    """
    section = _section()
    english = glance("engine", "🦉", Phrase("surface.state"), "22.09", [section], EN)
    russian = glance("engine", "🦉", Phrase("surface.state"), "22.09", [section], RU)

    assert "**queue**  164 issues open instance-wide · snapshot 5d old" in english
    assert "**очередь**  164 issue открыто по инстансу · снимку 5д" in russian


def test_the_work_layer_follows_the_same_catalog() -> None:
    """Both layers of the render, or the surface code-switches between them — which is
    the per-row mix rule 10 names as the thing code-switching research prices badly."""
    section = _section()
    assert "→ proof:" in work([section], EN)
    assert "→ пруф:" in work([section], RU)


def test_the_row_order_does_not_depend_on_the_language() -> None:
    """Rule 2 wants fixed positions. Ordering on the worded label would make the
    report's shape a property of the operator's locale.

    The three slots below are chosen so the two orders disagree: by key the sequence
    is branches · ci · queue, and by Russian word it would be CI · ветки · очередь.
    Sorting the rendered label therefore reddens this; sorting the key does not.
    """
    sections = [
        SectionResult(Phrase("slot.queue"), Absent(reason=Phrase("absent.ci"))),
        SectionResult(Phrase("slot.branches"), Absent(reason=Phrase("absent.branches_gh"))),
        SectionResult(Phrase("slot.ci"), Absent(reason=Phrase("absent.ci"))),
    ]
    expected = [s.name.key for s in rank_sections(sections)]
    assert expected == ["slot.branches", "slot.ci", "slot.queue"]

    surface = Phrase("surface.state")
    for catalog in (EN, RU):
        # The block is head + blank + one row per section, in that order (§Shape).
        rows = glance("e", "🦉", surface, "22.09", sections, catalog).splitlines()[2:]
        assert len(rows) == len(expected)
        for line, key in zip(rows, expected, strict=True):
            assert f"**{say(Phrase(key), catalog)}**" in line


# --------------------------------------------------------------------------
# The catalog does not rot
# --------------------------------------------------------------------------


def test_every_phrase_the_tree_builds_exists_in_the_canonical_catalog() -> None:
    """A mistyped key is a blank cell on the operator's surface, not an exception he
    can act on — unless something asserts the set. This is that something.

    It reads the producing modules' AST rather than the catalog, so a key added to
    `EN` and used nowhere does not satisfy it and a key used in code and never
    registered cannot hide behind one.
    """
    produced = _produced_keys()
    assert produced, "the scan found no Phrase at all — it is looking in the wrong place"
    missing = sorted(k for k in produced if k not in EN)
    assert missing == [], f"built but not in the canonical catalog: {missing}"


def test_the_keys_built_from_an_axis_name_are_registered_too() -> None:
    """`freshness_suffix` spells its key from the axis (`freshness.{axis}.stale`), so
    the AST scan above cannot see it. Both axes, both verdicts, named explicitly —
    an axis added to `Freshness` without catalog entries reddens here.
    """
    for axis in ("snapshot", "movement"):
        for state in ("stale", "unknown"):
            key = f"freshness.{axis}.{state}"
            assert key in EN, f"{key} has no canonical wording"


def test_a_translation_never_invents_a_key_of_its_own() -> None:
    """A key in `RU` and not in `EN` is unreachable: `say` looks it up in the selected
    catalog only for keys some builder actually emits, and every builder is checked
    against `EN`. Such a key is dead weight that reads like coverage."""
    orphans = sorted(k for k in RU if k not in EN)
    assert orphans == [], f"in RU and reachable from nothing: {orphans}"


def test_a_translation_keeps_every_parameter_its_english_template_takes() -> None:
    """The drift that produces a blank where a number should be.

    `noun.queue` takes `{floor}`; a translation that drops it silently stops stating
    that the union is incomplete, and nothing else on the row says so. `str.format`
    would not complain — an unused keyword argument is legal — so the check has to be
    on the fields themselves.
    """
    for key, translated in sorted(RU.items()):
        assert _fields(translated) == _fields(EN[key]), (
            f"{key}: RU takes {sorted(_fields(translated))}, "
            f"EN takes {sorted(_fields(EN[key]))}"
        )


def test_a_lagging_translation_falls_back_instead_of_breaking_the_row() -> None:
    """Translation lag is normal; an untranslated row is legible and a crash is not."""
    sparse = {"slot.feedback": "фидбек"}
    assert say(Phrase("slot.feedback"), sparse) == "фидбек"
    assert say(Phrase("slot.branches"), sparse) == "branches"


def test_a_key_absent_from_the_canonical_catalog_raises() -> None:
    """The asymmetry that makes the fallback safe: `EN` is written beside the code, so
    a key missing there is a programming error and never an operator condition."""
    with pytest.raises(KeyError, match="canonical catalog"):
        say(Phrase("slot.invented"))


def test_a_nested_phrase_is_resolved_in_the_selected_catalog() -> None:
    """The optional clauses — the floor suffix, the missing-snapshot tail — are
    phrases, not strings the builder pre-worded. If nesting resolved against `EN` the
    Russian row would code-switch mid-cell, which is rule 10's named failure."""
    noun = Phrase("noun.queue", {"floor": Phrase("suffix.floor")})
    assert say(noun, EN) == "issues open instance-wide (floor, not total)"
    assert say(noun, RU) == "issue открыто по инстансу (пол, не итог)"

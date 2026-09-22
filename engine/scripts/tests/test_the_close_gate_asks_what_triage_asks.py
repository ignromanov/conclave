"""GH#310 — the mandatory close gate must fail on exactly what Step 0 will later reject.

THE PATH, EXECUTED

`commands/done.md` told every advisor: *"Fill `items[]` ... then set `_draft: false`."*
`commands/feedback.md` told them the opposite: *"Do not hand-edit. Finalize via
`--finalize` — it validates then flips to `false`."* `done.md` is the one that runs at the
end of every session, and the gate behind it — `engine session emission-gate`, AC12 — asked
only `re.search(r"^_draft: false", text)`. A review that never passed validation therefore
closed its own session green.

The cost is deferred and lands on somebody else. Measured on the safe-unfollow instance
2026-09-15: one review finalized by hand with two items missing `location` hard-aborted
triage Step 0 for **all three advisors**, as `feedback_triage.py --check exited 1` over the
whole index. The session that created it saw nothing.

WHY "`model_validate` RATHER THAN `re.search`" IS NOT THE FIX AS WRITTEN

The issue's suggested fix says to make the gate "run `Review.model_validate` rather than
`re.search`". Executed, that is a regression: `Review` carries
`draft: bool = Field(default=False, alias="_draft")`, so a review with `_draft: true`
validates **clean**. Measured — a schema-valid draft passes `model_validate` exactly as its
finalized twin does. Replacing the draft check with validation would switch AC12 off for
the case it was built for. The gate needs BOTH, and `test_a_valid_draft_still_blocks` is
here to keep the second one from being optimised away again.

WHY ONE PREDICATE AND NOT THREE

Before this change "is this review fileable" had three implementations: a regex in
`enginelib/filing.py`, `Review.model_validate(read_commented(...))` in `_finalize`, and
`Review.model_validate(fm_read(...))` in the indexer — two different YAML engines behind
two different readers. One of the three was a string search, and it is the one every
session ran. `schema.schema_errors` is now the single definition; these tests hold the
gate and the indexer to the same answer rather than checking each against a hand-written
expectation, which is how three copies agreed on paper and disagreed in production.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
CODE_ROOT = SCRIPTS_ROOT.parents[1]

sys.path.insert(0, str(SCRIPTS_ROOT))
sys.path.insert(0, str(SCRIPTS_ROOT / "feedback"))

ADVISOR = "atlas-cto"
SESSION = "s310"
TODAY = "2026-09-21"

_NOW = datetime.now(tz=UTC).isoformat()

_COMPLETE_ITEM = """\
- id: "i1"
  category: script-defect
  layer: infra
  location:
    file: engine/scripts/x.py
  observation: the thing did the thing
  interpretation: because of the other thing
  suggested_fix: stop it
  severity: medium
  frequency: occasional
  evidence: measured twice
"""

# The exact shape from the incident: author-complete to the eye, missing `location`.
_ITEM_WITHOUT_LOCATION = """\
- id: "i2"
  category: script-defect
  layer: infra
  observation: this one has no location
  interpretation: and nobody noticed
  suggested_fix: add one
  severity: medium
  frequency: occasional
  evidence: measured twice
"""


def _review(items: str, *, draft: str) -> str:
    return (
        "---\n"
        "feedback_id: fb-310-fixture\n"
        f"agent: {ADVISOR}\n"
        "agent_type: advisor\n"
        f"session_ref: {SESSION}\n"
        f"created: '{_NOW}'\n"
        f"updated_at: '{_NOW}'\n"
        "skill_version: sha256:000000000000\n"
        "summary: a session happened\n"
        "items:\n"
        f"{items}"
        "below_threshold_count: 0\n"
        f"_draft: {draft}\n"
        "---\n\n# body\n"
    )


def _emit(root: Path, text: str) -> Path:
    path = root / "ops" / "feedback" / TODAY / f"{ADVISOR}-{SESSION}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _gate(root: Path) -> list[str]:
    from feedback.emission import blockers

    return blockers(root, ADVISOR, SESSION, TODAY)


def _triage_would_reject(path: Path) -> bool:
    """The downstream question, asked with the downstream instrument.

    Deliberately re-implemented from `feedback_index`'s own two lines rather than shared
    with the code under test: a gate that calls the same helper as the thing it grades
    agrees with it by construction and measures nothing.
    """
    from pydantic import ValidationError

    from briefing.frontmatter_io import read as fm_read
    from feedback.schema import Review

    meta, _ = fm_read(path)
    if meta.get("_draft", False):
        return False  # drafts are skipped by the indexer, not rejected
    try:
        Review.model_validate(dict(meta))
    except ValidationError:
        return True
    return False


# ---------------------------------------------------------------------------
# Anti-vacuity
# ---------------------------------------------------------------------------


def test_the_fixtures_are_what_they_claim_to_be(tmp_path):
    """Two fixtures, opposite verdicts from the indexer — or nothing below measures.

    If the "complete" review were secretly invalid, every gate assertion would pass for
    the wrong reason; if the "incomplete" one were secretly valid, the reproduction would
    be of nothing.
    """
    good = _emit(tmp_path / "a", _review(_COMPLETE_ITEM, draft="false"))
    bad = _emit(tmp_path / "b", _review(_COMPLETE_ITEM + _ITEM_WITHOUT_LOCATION, draft="false"))
    assert not _triage_would_reject(good), "the complete fixture is not actually valid"
    assert _triage_would_reject(bad), "the incomplete fixture is not actually invalid"


# ---------------------------------------------------------------------------
# The defect
# ---------------------------------------------------------------------------


def test_a_hand_finalized_invalid_review_does_not_close_the_session(tmp_path):
    """#310 itself: `_draft: false` set by hand on a review Step 0 will drop.

    Before the fix the gate answered PASS here, which is what let the defect leave the
    session that produced it.
    """
    _emit(tmp_path, _review(_COMPLETE_ITEM + _ITEM_WITHOUT_LOCATION, draft="false"))
    reasons = _gate(tmp_path)
    assert reasons, "a review that triage will drop closed the session green"


def test_the_gate_names_the_field_so_the_agent_can_act(tmp_path):
    """A refusal that does not say what is wrong sends the agent back to guess.

    The incident cost three advisors a triage run because the failure surfaced as a bare
    `exited 1` two days later. A gate that repeats that shape at close time has moved the
    silence, not removed it.
    """
    _emit(tmp_path, _review(_COMPLETE_ITEM + _ITEM_WITHOUT_LOCATION, draft="false"))
    blob = "\n".join(_gate(tmp_path))
    assert "location" in blob, f"the refusal does not name the missing field:\n{blob}"
    # The item's OWN id, not `items.1`. Written as a disjunction first — `"i2" in blob or
    # "items.1" in blob` — which probe M4 passed while reporting a bare index, because the
    # surviving half satisfied it. An assertion with an escape hatch measures the hatch.
    assert "i2" in blob, (
        f"the refusal locates the fault by pydantic index only; an author reading a file "
        f"whose ids run i1, i2, i4, i5 has to count to find it:\n{blob}"
    )


def test_a_valid_draft_still_blocks(tmp_path):
    """Validation does NOT subsume the draft check — the issue's own wording would.

    `Review.draft` is an ordinary optional field with a default, so `_draft: true`
    validates clean. Swapping `re.search` FOR `model_validate`, as suggested, would make
    the gate wave through every unfinished review. This fixture is schema-valid on
    purpose: only the draft check can block it, so the assertion cannot be satisfied by
    the validator doing the work.
    """
    _emit(tmp_path, _review(_COMPLETE_ITEM, draft="true"))
    reasons = _gate(tmp_path)
    assert reasons, "an unfinished draft closed the session"
    assert any("draft" in r.lower() for r in reasons), reasons


def test_a_finalized_valid_review_passes(tmp_path):
    """The other side. A gate that refuses everything is not a gate."""
    _emit(tmp_path, _review(_COMPLETE_ITEM, draft="false"))
    assert _gate(tmp_path) == []


def test_a_missing_emission_still_blocks_and_names_the_path(tmp_path):
    """The original AC12 behaviour, kept: no file at all is the commonest failure."""
    (tmp_path / "ops" / "feedback").mkdir(parents=True)
    reasons = _gate(tmp_path)
    assert reasons
    assert f"{ADVISOR}-{SESSION}.md" in "\n".join(reasons)


# ---------------------------------------------------------------------------
# One predicate, two callers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,items,draft",
    [
        ("valid-final", _COMPLETE_ITEM, "false"),
        ("invalid-final", _COMPLETE_ITEM + _ITEM_WITHOUT_LOCATION, "false"),
        ("invalid-only", _ITEM_WITHOUT_LOCATION, "false"),
    ],
)
def test_the_gate_agrees_with_triage_on_every_finalized_review(tmp_path, label, items, draft):
    """The property the incident needed and nobody held: same question, same answer.

    Stated as an equivalence rather than as per-case expectations. Three hand-written
    expectations can all be wrong in the same direction — which is exactly what happened
    when three implementations of "fileable" were each tested against their own idea of
    it.
    """
    path = _emit(tmp_path, _review(items, draft=draft))
    assert bool(_gate(tmp_path)) == _triage_would_reject(path), (
        f"[{label}] the close gate and triage disagree about the same file"
    )


def test_the_gate_runs_through_the_shipped_cli(tmp_path):
    """`blockers()` being right is not the same as `engine session emission-gate` being right.

    The adapter is what `commands/done.md` actually invokes, and a section that is correct
    in isolation but unwired from its entry point refuses nothing at all.
    """
    _emit(tmp_path, _review(_COMPLETE_ITEM + _ITEM_WITHOUT_LOCATION, draft="false"))
    proc = subprocess.run(
        [sys.executable, "-m", "engine", "session", "emission-gate"],
        cwd=SCRIPTS_ROOT, capture_output=True, text=True,
        env={
            "PATH": "/usr/bin:/bin", "PYTHONPATH": str(SCRIPTS_ROOT),
            "CONCLAVE_AI_ROOT": str(tmp_path), "ADVISOR_NAME": ADVISOR,
            "SESSION_ID": SESSION, "TODAY": TODAY,
            "CONCLAVE_ENGINE_ROOT": str(SCRIPTS_ROOT.parent),
        },
    )
    assert proc.returncode != 0, f"the shipped CLI passed an invalid review:\n{proc.stdout}"
    assert "location" in (proc.stdout + proc.stderr)


# ---------------------------------------------------------------------------
# No surface teaches the bypass
# ---------------------------------------------------------------------------

_SURFACES = ("commands", "skills", "agents", "docs")

#: Any instruction to SET the flag. Case-insensitive, and tolerant of the punctuation a
#: re-wording would use, because the first version of this gate was a tuple of three
#: literal sentences and probe M5 walked straight through it by capitalising one word.
#: A gate that only recognises the wording already removed from the tree protects the
#: tree it was written against, not the tree it ships in.
#:
#: IMPERATIVES ONLY — `set`/`sets`, never the gerund. `commands/feedback.md` carries an
#: anti-pattern table whose row reads "Setting `_draft: false` before filling items", and
#: that row is the warning, not the instruction. A gerund NAMES an action; an imperative
#: PRESCRIBES one, and no lexical window can tell use from mention here because the
#: negation in that row is structural (it is in a table of mistakes) rather than in the
#: sentence. The limit this accepts: "Setting `_draft: false` is how you finish" would
#: teach the bypass and pass. That is tolerable only because the doc gate is the SECOND
#: line — the first is `feedback.emission.blockers`, which now refuses the file itself.
_SETS_DRAFT = re.compile(r"\bsets?\b[^.\n]{0,20}?_draft", re.I)

#: A prohibition contains the imperative it prohibits. `Do **not** set \`_draft\` by hand`
#: has to survive the same scan that forbids `then set \`_draft: false\``, so the window
#: before the match is checked for a negation rather than the sentence being whitelisted.
_NEGATED = re.compile(r"\b(not|never|n't|without|avoid)\b[^.\n]{0,30}$", re.I)


def _bypass_hits(text: str) -> list[str]:
    """Every instruction in *text* to set `_draft`, minus the ones that forbid it."""
    hits = []
    for m in _SETS_DRAFT.finditer(text):
        if _NEGATED.search(text[max(0, m.start() - 40):m.start()]):
            continue
        line = text[text.rfind("\n", 0, m.start()) + 1:]
        hits.append(line.split("\n", 1)[0].strip()[:90])
    return hits


def _teaches_the_bypass(text: str) -> bool:
    return bool(_bypass_hits(text))


def _shipped_markdown() -> list[Path]:
    files: list[Path] = []
    for surface in _SURFACES:
        files.extend(sorted((CODE_ROOT / surface).rglob("*.md")))
    return files


def test_the_surface_scan_reaches_the_documents_it_claims_to(tmp_path):
    """A scan over zero files is a green test that measured nothing (#104).

    Both halves are pinned: the sweep must find files, and the matcher must fire on the
    historical sentence. A gate against a wording nobody ever wrote is a gate against
    nothing, so the pre-fix text of `commands/done.md:35` is the control.
    """
    files = _shipped_markdown()
    assert len(files) > 20, f"the surface sweep found {len(files)} files"

    # Fires on the sentence that was in the tree, on the re-wordings a later author would
    # reach for, and NOT on the prohibition that replaced it. All three directions are
    # pinned: a matcher that only knows the historical string is a gate against the past,
    # and one that also flags the prohibition forces the fix to be silence.
    must_flag = (
        "Fill `items[]` (cap 3-5, `evidence` mandatory), then set `_draft: false`.",
        "The agent fills items[] honestly, then sets `_draft: false`.",
        "Then set `_draft` to false when you are done.",
    )
    must_not_flag = (
        "Do **not** set `_draft` by hand.",
        "never set `_draft` yourself — finalize instead",
        # The live anti-pattern row in commands/feedback.md. It is the warning; flagging
        # it would force the correct document to stop naming the mistake it warns about.
        "| Setting `_draft: false` before filling items | Submits an incomplete review |",
    )
    for line in must_flag:
        assert _teaches_the_bypass(line), f"matcher misses a bypass wording: {line!r}"
    for line in must_not_flag:
        assert not _teaches_the_bypass(line), f"matcher flags a prohibition: {line!r}"


def test_no_shipped_surface_tells_an_agent_to_hand_set_the_draft_flag():
    """`commands/feedback.md` was right and `commands/done.md` was wrong, and done.md is
    the one every advisor runs at the end of every session.

    A contradiction between two documents is resolved by whichever one is open at the
    time. This holds the losing wording out of the tree entirely, because the previous
    arrangement — one correct document and one incorrect one — read as consistent to
    anyone who had only opened the first.
    """
    offenders = [
        f"{path.relative_to(CODE_ROOT)}: {hit}"
        for path in _shipped_markdown()
        for hit in _bypass_hits(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, "a shipped surface still teaches the bypass:\n" + "\n".join(offenders)


def test_done_names_the_validating_path():
    """Removing the wrong instruction is not the same as supplying the right one.

    Left silent, `/conclave:done` would describe a mandatory gate and no way to satisfy
    it, and the agent would reach for the hand edit again — this time uninstructed.
    """
    text = (CODE_ROOT / "commands" / "done.md").read_text(encoding="utf-8")
    assert "--finalize" in text, "done.md demands a finalized emission and never says how"


def test_the_protocol_contract_agrees_with_the_command():
    """`feedback-protocol.md` is loaded as a contract by several commands, so a stale copy
    of the instruction there outlives its removal from any one command file."""
    text = (
        CODE_ROOT / "skills" / "advisor-contracts" / "references" / "feedback-protocol.md"
    ).read_text(encoding="utf-8")
    assert "--finalize" in text

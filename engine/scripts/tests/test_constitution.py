"""test_constitution.py — the engine charter binds itself (constitution.md, Principle 0).

No code has ever read `constitution.md` for what it *says*. Every principle in it was, at best,
`reviewed`; twelve `*Forbids*:` clauses had no check behind them at all. A governing document that
nothing reads teaches every agent that its strongest language is decorative — and that lesson
generalises to the rules where the strength was real (arXiv:2503.15512).

(A concurrent publication gate scans this file among the repo's public-surface files, looking for
leaked operator paths. That reads the bytes, not the principles.)

This gate enforces exactly one thing, the one thing a document *can* enforce about itself: that no
principle claims an enforcement it does not have.

  mechanical -> MUST name a `**Check**:` that resolves to a test function that exists on disk.
  reviewed   -> MUST name a `**Monitor**:`.
  declaratory-> MUST NOT use BCP 14 keywords; it has no standing to.

Per the charter's own amendment rule, a principle may not be tagged `mechanical` until its check has
been observed failing on a violation. This test cannot verify that history — but it can, and does,
refuse to let the tag point at a test that isn't there.
"""

from __future__ import annotations

import pathlib
import re

SCRIPTS_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CHARTER = REPO_ROOT / "constitution.md"

_VALID_TIERS = {"mechanical", "reviewed", "declaratory"}

# `### 0. Title` or `### IV. Title` — the principle headings of §2.
_PRINCIPLE_RE = re.compile(r"^### (0|[IVX]+)\. (.+)$")
_TIER_RE = re.compile(r"^\*\*Tier\*\*: `(\w+)`")
_CHECK_RE = re.compile(r"\*\*Check\*\*: `([^`]+)`")
_MONITOR_RE = re.compile(r"\*\*Monitor\*\*: (\S.*)")

# BCP 14 keywords carry force only in all caps (RFC 8174), so match them that way.
_BCP14_RE = re.compile(r"\b(MUST NOT|MUST|SHOULD NOT|SHOULD|REQUIRED|MAY)\b")


def _sections() -> dict[str, list[str]]:
    """Principle numeral -> its lines, up to the next heading of any level."""
    lines = CHARTER.read_text(encoding="utf-8").splitlines()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        m = _PRINCIPLE_RE.match(line)
        if m:
            current = m.group(1)
            sections[current] = []
            continue
        if line.startswith("## ") or line.startswith("### "):
            current = None
            continue
        if current:
            sections[current].append(line)
    return sections


def test_charter_exists_and_declares_principles():
    assert CHARTER.is_file(), f"engine charter absent: {CHARTER}"
    sections = _sections()
    # A gate that scans zero targets must fail loudly rather than pass vacuously
    # (the rule this suite already applies in test_gates.py).
    assert len(sections) >= 2, f"charter parsed {len(sections)} principles — heading format changed?"


def test_every_principle_declares_an_honest_tier():
    """The charter's Principle 0. Each tier tag must be backed by what it claims."""
    problems: list[str] = []

    for numeral, body in _sections().items():
        text = "\n".join(body)

        tier_match = next((_TIER_RE.match(ln) for ln in body if _TIER_RE.match(ln)), None)
        if not tier_match:
            problems.append(f"principle {numeral}: no `**Tier**:` line")
            continue

        tier = tier_match.group(1)
        if tier not in _VALID_TIERS:
            problems.append(f"principle {numeral}: unknown tier {tier!r}")
            continue

        if tier == "mechanical":
            check = _CHECK_RE.search(text)
            if not check:
                problems.append(f"principle {numeral}: tagged mechanical, names no **Check**")
                continue
            target = check.group(1)
            if "::" not in target:
                problems.append(f"principle {numeral}: check {target!r} is not path::test")
                continue
            rel_path, test_name = target.split("::", 1)
            path = SCRIPTS_ROOT / rel_path
            if not path.is_file():
                problems.append(f"principle {numeral}: check file absent: {rel_path}")
            elif f"def {test_name}(" not in path.read_text(encoding="utf-8"):
                problems.append(f"principle {numeral}: {rel_path} has no `def {test_name}(`")

        elif tier == "reviewed":
            if not _MONITOR_RE.search(text):
                problems.append(f"principle {numeral}: tagged reviewed, names no **Monitor**")

        else:  # declaratory
            # Strip the tier/ledger line itself: it legitimately says "MUST NOT use" when quoting
            # the rule. Only the principle's own normative prose is in scope.
            prose = "\n".join(ln for ln in body if not _TIER_RE.match(ln))
            for kw in _BCP14_RE.findall(prose):
                problems.append(
                    f"principle {numeral}: declaratory tier uses BCP 14 keyword {kw!r} — "
                    "a rule nothing checks has no standing to say MUST"
                )

    assert not problems, "charter tier claims are not honest:\n  " + "\n  ".join(problems)


def test_charter_never_uses_shall_outside_quotation():
    """`shall` drifts between obligation, permission, and future tense; BCP 14 prefers MUST.

    Use, not mention: quotations of regulatory text (blockquotes, footnote bodies) and the charter's
    own `*shall*`/`` `shall` `` — where the word is named rather than wielded — are all legitimate.
    """
    body, _, _footnotes = CHARTER.read_text(encoding="utf-8").partition("\n[^")
    used = re.compile(r"(?<![*`])\bshall\b(?![*`])", re.IGNORECASE)
    offenders = [
        f"{n}: {ln.strip()}"
        for n, ln in enumerate(body.splitlines(), start=1)
        if used.search(ln) and not ln.lstrip().startswith(">")
    ]
    assert not offenders, "charter uses 'shall' outside a quotation:\n  " + "\n  ".join(offenders)


# §7's ledger is the one part of this charter no test has ever read, and it is the one part that
# went stale: on 2026-09-15 it still called `re-occurred` unbuilt, 2 months after a writer for it
# shipped. Prose about code is a cache, and nobody invalidates a cache nobody reads.
_ABSENT_RE = re.compile(r"\*\*absent from engine code\*\*: (.+)")
_PRESENT_RE = re.compile(r"\*\*present in engine code\*\*: (.+)")
_TOKEN_RE = re.compile(r"`([^`]+)`")


def _non_test_engine_sources() -> list[pathlib.Path]:
    """Every shipped Python module — excluding tests, which may name a mechanism to assert it absent."""
    return [
        p
        for p in SCRIPTS_ROOT.rglob("*.py")
        if ".venv" not in p.parts and "tests" not in p.parts
    ]


def test_the_ledger_absence_claims_are_still_true():
    """§7 says which mechanisms the engine does not have. This runs the claim instead of trusting it.

    Both directions are graded, and that is the point. An absence claim verified by a scan is only
    as good as the scan: a broken perimeter, a typo'd root, a glob that matches nothing all return
    zero hits and *manufacture* the absence they were asked to check. So the ledger also names a
    mechanism it claims is present, and this gate fails just as loudly when that one is not found.
    The positive control is what makes the negative result evidence.
    """
    text = CHARTER.read_text(encoding="utf-8")

    absent_m, present_m = _ABSENT_RE.search(text), _PRESENT_RE.search(text)
    assert absent_m and present_m, (
        "§7 no longer states its absence claims in a form this gate can read — expected a line "
        "carrying `**absent from engine code**:` and one carrying `**present in engine code**:`, "
        "each followed by backticked tokens. Without both, this test grades nothing."
    )
    absent = _TOKEN_RE.findall(absent_m.group(1))
    present = _TOKEN_RE.findall(present_m.group(1))
    assert absent and present, f"§7 named no tokens to check (absent={absent}, present={present})"

    sources = _non_test_engine_sources()
    assert len(sources) > 50, (
        f"the scan perimeter collapsed to {len(sources)} files under {SCRIPTS_ROOT} — "
        "every absence below would be an artefact of an empty scan, not a measurement"
    )
    bodies = {p: p.read_text(encoding="utf-8", errors="replace") for p in sources}

    def carriers(token: str) -> list[str]:
        return sorted(str(p.relative_to(SCRIPTS_ROOT)) for p, b in bodies.items() if token in b)

    problems = []
    for token in absent:
        found = carriers(token)
        if found:
            problems.append(
                f"§7 calls `{token}` absent from engine code, and it is in: {', '.join(found)}"
            )
    for token in present:
        if not carriers(token):
            problems.append(
                f"§7 calls `{token}` present in engine code and this scan found it nowhere — "
                "either the mechanism was removed, or this scan is broken and every absence "
                "asserted above is worthless"
            )
    assert not problems, "§7's ledger asserts what the code does not do:\n  " + "\n  ".join(problems)


def test_every_path_the_charter_names_resolves():
    """The charter cites test files as its evidence. A path that has moved is evidence no longer.

    Exactly the defect two shipped surfaces carried until #327: twelve `scripts/…py` references
    that named nothing on disk, every one of them read by an agent as an instruction. A citation
    is checked by resolving it, never by reading it.

    Scoped to `.py` on purpose. Every code citation in this document resolves against
    `engine/scripts/`, while the one `.md` path it names — an instance's own charter, scaffolded
    per project — is a description of a file that is absent from this repo by design. Narrowing to
    the extension keeps the rule exception-free, which is why it is the rule.
    """
    text = CHARTER.read_text(encoding="utf-8")
    cited = sorted({
        tok.split("::", 1)[0]
        for tok in _TOKEN_RE.findall(text)
        if "/" in tok and tok.split("::", 1)[0].endswith(".py")
    })
    # Anti-vacuity backstop, and stated as one: no mutation reached it. Every way to empty this
    # list — no `mechanical` principle, a citation format without backticks, a path that lost its
    # directory — trips test_every_principle_declares_an_honest_tier first, with a clearer message.
    # It stays because the vacuous pass is the failure mode this suite keeps finding (#110, 116),
    # and it costs four lines; it is not evidence that the case is covered.
    assert cited, (
        "the charter cites no test path at all — either every citation went, or the backtick "
        "convention did, and the resolution below would pass over nothing"
    )
    missing = [t for t in cited if not (SCRIPTS_ROOT / t).is_file()]
    assert not missing, (
        "the charter names files that are not there:\n  "
        + "\n  ".join(f"{t} (expected at {SCRIPTS_ROOT / t})" for t in missing)
    )

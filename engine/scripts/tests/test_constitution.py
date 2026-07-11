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

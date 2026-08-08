"""arms.py — the three context conditions of the P0 eval.

  full    — constitution.md, verbatim, appended to the agent's system prompt.
  placebo — a length-matched, register-matched, domain-null document in the same position.
  absent  — nothing appended.

Arm (b) is what makes the result interpretable. With only full/absent, a positive delta cannot
distinguish "the charter's content steered the agent" from "a long authoritative block in context
steered the agent" — and the P1/P2 build decision must not rest on that ambiguity (spec 104 §2.1).

  content effect          = full − placebo
  presence/length effect  = placebo − absent

It also makes the verdict "shorter steers better" *reachable*, which a two-arm design structurally
cannot express.
"""
from __future__ import annotations

import re
from pathlib import Path

ARMS = ("full", "placebo", "absent")

PLACEBO_PATH = Path(__file__).resolve().parent / "placebo.md"

_BCP14_RE = re.compile(r"\b(MUST NOT|MUST|SHOULD NOT|SHOULD|REQUIRED|MAY)\b")


def system_prompt(arm: str, charter: Path) -> str:
    if arm == "absent":
        return ""
    if arm == "full":
        return charter.read_text(encoding="utf-8")
    if arm == "placebo":
        return PLACEBO_PATH.read_text(encoding="utf-8")
    raise ValueError(f"unknown arm: {arm!r}")


def approx_tokens(text: str) -> int:
    """Whitespace-delimited words. Exact tokenisation is model-internal and not reproducible from
    here; the arms need to be *matched*, not *counted*, and any monotone proxy applied to both
    documents does that. The metric is stated so the match is checkable, not authoritative.
    """
    return len(text.split())


def bcp14_count(text: str) -> int:
    return len(_BCP14_RE.findall(text))


def length_match_error(charter: Path) -> float:
    charter_n = approx_tokens(charter.read_text(encoding="utf-8"))
    placebo_n = approx_tokens(PLACEBO_PATH.read_text(encoding="utf-8"))
    return abs(charter_n - placebo_n) / charter_n

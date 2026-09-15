"""The agent-def render chain and its template say the same things (#134).

`engine advisor create` renders `agent-frontmatter.md` through a `str.replace` chain.
Executed against the template on the day this was written, the two disagreed in one
direction and by three tokens:

    substituted by create(): ${COLOR} ${DESCRIPTION} ${EMOJI} ${ID} ${PROJECT_NAME}
                             ${ROLE} ${TONE} ${TONE_HINT}
    present in template:     ${COLOR} ${DESCRIPTION} ${ID} ${PROJECT_NAME} ${ROLE}

`${EMOJI}` is the one that cost something. `create()` accepts `--emoji`, and the
output-formatting contract says the persona emoji is read from the agent-def's
`emoji:` frontmatter key — but the advisor template has no such key, so the replace
had nothing to hit and the value reached the file only as prose inside the generated
description. Seven shipped EXECUTOR defs carry the key, because the executor template
has it; the advisor ones did not.

A no-op `.replace()` is silent by construction. Nothing fails, nothing is logged, and
the chain reads exactly like a chain that works — which is why it survived long enough
for the contract that depends on it to be written against a key nobody emits.

This is #118's defect seen from the other side: there, the template held tokens the
chain did not substitute; here, the chain substitutes tokens the template does not
hold. One gate for both directions, so the pair cannot drift again whichever way it
goes.

Derived from the source and the template, never from a list kept here. A list is what
the chain already is, and what went stale.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from enginelib import paths

SCRIPTS = Path(__file__).resolve().parents[1]
ADVISOR_SRC = SCRIPTS / "enginelib" / "advisor.py"

#: `${TOKEN}` — the agent-def template's placeholder shape. The persona template uses
#: `{{token}}` and is gated separately by test_minted_persona_identity_is_filled.py.
SHELL_TOKEN = re.compile(r"\$\{[A-Z_]+\}")

#: The local name `create()` binds the rendered agent-def to. Scoping the scan to this
#: assignment keeps the persona chain in the same function out of the result.
RENDER_TARGET = "rendered"


def _chain_tokens() -> set[str]:
    """Every `${TOKEN}` the agent-def render chain substitutes.

    Read off the AST rather than by grepping the file, so the persona chain a few
    lines below — which legitimately substitutes `${PROJECT_NAME}` too — cannot leak
    into the set and make a dead token look live.
    """
    tree = ast.parse(ADVISOR_SRC.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        target = node.targets[0]
        if not (isinstance(target, ast.Name) and target.id == RENDER_TARGET):
            continue
        for call in ast.walk(node.value):
            if (isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "replace"
                    and call.args
                    and isinstance(call.args[0], ast.Constant)
                    and isinstance(call.args[0].value, str)):
                found.update(SHELL_TOKEN.findall(call.args[0].value))
    return found


def _template_tokens() -> set[str]:
    template = (
        Path(paths.templates_dir()) / "agent-frontmatter.md"
    ).read_text(encoding="utf-8")
    return set(SHELL_TOKEN.findall(template))


def test_both_scans_see_something():
    """Anti-vacuity, both sides. Two empty sets are equal, and an AST walk that
    matched no `.replace` call would report perfect agreement while reading nothing."""
    chain, template = _chain_tokens(), _template_tokens()
    assert len(chain) >= 4, f"the chain scan found {chain} — it is not reading create()"
    assert len(template) >= 4, f"the template scan found {template}"
    assert "${ID}" in chain and "${ID}" in template, (chain, template)


def test_the_chain_substitutes_nothing_the_template_does_not_hold():
    dead = sorted(_chain_tokens() - _template_tokens())
    assert not dead, (
        f"create() substitutes {dead}, which agent-frontmatter.md does not contain.\n"
        "A no-op `.replace()` reads exactly like one that works and fails nowhere. "
        "${EMOJI} was dead this way while the output-formatting contract specified "
        "the agent-def's `emoji:` key as the place the persona emoji is read from "
        "(#134)."
    )


def test_the_template_holds_no_token_the_chain_leaves_behind():
    unfilled = sorted(_template_tokens() - _chain_tokens())
    assert not unfilled, (
        f"agent-frontmatter.md holds {unfilled}, which create() never substitutes — "
        "they would ship verbatim into a hired advisor's agent-def (#118 is the same "
        "defect in the persona template)."
    )

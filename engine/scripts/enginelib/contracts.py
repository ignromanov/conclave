"""enginelib/contracts.py — who loads an advisor contract, and who enters it (#268).

Every file in `skills/advisor-contracts/references/` declares its scope in frontmatter,
and until this module existed nothing read that declaration: a grep for `appliers` or
`applies_to` across `engine/scripts` found zero production callers and zero tests. The
field drifted the way unread fields do — two spellings of the key, five contracts without
it, a free-text value, an applier naming a command that does not exist, and disagreement
with the import blocks in both directions.

I/O-free: every function takes text and returns a value. The tests walk the trees.
"""
from __future__ import annotations

import re

#: The scope value for a contract that binds wherever it is loaded, with no owning command.
#: Sixteen of the seventeen contracts are this: policy, style, or schema.
UNIVERSAL = "all advisors"

#: The audiences a contract may declare beside a lifecycle command. `all executors` is not
#: `all advisors`: `executor-protocol` binds exec-*.md agent-defs and no command loads it.
AUDIENCES = frozenset({UNIVERSAL, "all executors"})

#: The two retired spellings. Both shipped for months because nothing read either.
LEGACY_KEYS = ("applies_to", "applies-to")

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---", re.S)
_APPLIERS = re.compile(r"^(appliers|applies_to|applies-to):\s*(.*?)\s*$", re.M)

#: `!`cat …/advisor-contracts/references/<name>.md`` — the auto-import form a command uses
#: to put a contract in the session's context before its body runs.
_IMPORT = re.compile(r"advisor-contracts/references/([a-z0-9-]+)\.md`")

#: A contract is a BRANCH when it says what fires it and carries steps to run — the shape
#: a command has to enter at a point, as opposed to policy that binds by being in context.
#: Derived from the document rather than declared in frontmatter: measured over this tree a
#: hand-set `kind:` field would carry one non-default value in seventeen, and a field set
#: by hand on one file is a field nobody remembers to set on the second.
_TRIGGER = re.compile(r"^\s*>?\s*\*{0,2}(triggered|fires|invoked|entered) (when|at|by)",
                      re.I | re.M)
_STEPS = re.compile(r"^## Steps\s*$", re.M)


def frontmatter(text: str) -> str:
    m = _FRONTMATTER.match(text)
    return m.group(1) if m else ""


def legacy_key(text: str) -> str | None:
    """The retired spelling in use, or None.

    There were two, and the second was found only because the first scan reported four
    contracts as having *no* field at all: `applies-to:` (hyphen) carried untyped prose
    — `exec-*.md agent-defs (+ optional exec.* script dirs)`, `advisors+executors` — which
    no parser could have read even if one had existed.
    """
    for key in LEGACY_KEYS:
        if re.search(rf"^{re.escape(key)}:", frontmatter(text), re.M):
            return key
    return None


def parse_appliers(text: str) -> list[str] | None:
    """The declared scope, or None when the contract declares none.

    None and `[]` are different answers and are kept different: an empty list is a
    contract deliberately scoped to nothing, an absent field is a question never asked.
    """
    m = _APPLIERS.search(frontmatter(text))
    if not m:
        return None
    value = m.group(2)
    if not (value.startswith("[") and value.endswith("]")):
        return []          # prose where a list belongs — declared, unreadable
    return [e.strip() for e in value[1:-1].split(",") if e.strip()]


def contract_imports(text: str) -> list[str]:
    """Contract names a command auto-imports, in order, deduplicated.

    Read from the whole file rather than the header alone: an import placed below the
    body would still land in context, and a scan that only looked above the header would
    call it absent — which is the error class this module exists to stop repeating.
    """
    seen: list[str] = []
    for name in _IMPORT.findall(text):
        if name not in seen:
            seen.append(name)
    return seen


def command_body(text: str) -> str:
    """Everything from the `# ` title onward — the part a step can live in.

    The import block sits above it. Counting a name that appears only there as "the
    command names this contract" is exactly how a contract nothing enters looks wired up.
    """
    m = re.search(r"^# ", text, re.M)
    return text[m.start():] if m else text


def is_branch(text: str) -> bool:
    """True when the contract names what fires it AND carries steps to run."""
    return bool(_TRIGGER.search(text) and _STEPS.search(text))

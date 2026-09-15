"""frontmatter.py — line-based YAML frontmatter r/w. Port of lib/frontmatter.sh.
Values are simple strings; lists stored as "[a,b]". Intentionally NOT a yaml
round-trip — preserves byte-for-byte layout of untouched lines (parity contract)."""
import re
from pathlib import Path

from enginelib import records, template
from enginelib.snapshot import snapshot_write


class Raw(str):
    """A value that is ALREADY YAML and must be written through untouched.

    `render_record` serializes every value it puts inside a frontmatter fence. That is the
    right default — it is the default being absent that produced #255, #249 and #301 — but
    it is wrong for a caller that has built YAML on purpose: `as_flow_list("250,251")`
    returns the SEQUENCE `[250,251]`, and serializing it again would quote the brackets and
    turn a list into a string. The three serializers below return `Raw`, so those callers
    need no change and the exemption is something a value carries rather than something a
    key is listed for.
    """


def _plain_scalar_is_safe(text: str) -> bool:
    """True when one line of *text* reads back through a YAML parser as itself.

    The three hazards, in the order they were learned the hard way:
      `": "`      — a ScannerError, loud, found in a day (#255).
      leading `#` — a VALID document whose value is None; silent (#301).
      mid `" #"`  — a valid document whose value is TRUNCATED; silent and partial, the
                    worst of the three, and the one that cost five session reflexions.
    """
    return not (
        ": " in text
        or " #" in text
        or text.endswith(":")
        or text[0] in "#&*!|>'\"%@`-?:,[]{}"
    )


def fm_get(file: Path, key: str) -> str | None:
    p = Path(file)
    if not p.is_file():
        return None
    in_fm = False
    for line in p.read_text(encoding="utf-8").splitlines():
        if line == "---":
            if in_fm:
                break
            in_fm = True
            continue
        if in_fm and line.startswith(f"{key}:"):
            return line[len(key) + 1:].strip()
    return None


def fm_get_block(file: Path, key: str) -> str | None:
    """Read a frontmatter value that may be a `|` / `>` block scalar.

    fm_get() is line-based and returns the literal "|" for a block scalar —
    correct for the flat values it was written for, useless for a description,
    which is multi-line prose by design. Returns the dedented text, or None
    when the key is absent.
    """
    p = Path(file)
    if not p.is_file():
        return None
    lines = p.read_text(encoding="utf-8").splitlines()
    at, in_fm = None, False
    for idx, line in enumerate(lines):
        if line == "---":
            if in_fm:
                break          # closing fence reached without the key
            in_fm = True
            continue
        if in_fm and line.startswith(f"{key}:"):
            at = idx
            break
    if at is None:
        return None
    head = lines[at][len(key) + 1:].strip()
    if head not in ("|", "|-", "|+", ">", ">-", ">+"):
        return head or None
    body: list[str] = []
    for line in lines[at + 1:]:
        if line.strip() and not line.startswith((" ", "\t")):
            break
        body.append(line)
    while body and not body[-1].strip():
        body.pop()
    if not body:
        return None
    pad = min(len(ln) - len(ln.lstrip()) for ln in body if ln.strip())
    return "\n".join(ln[pad:] if ln.strip() else "" for ln in body)


def as_block(value: str, indent: int = 2, *, chomp: bool = False) -> Raw:
    """Render *value* as the right-hand side of a frontmatter key.

    Emits a `|` block scalar whenever the text cannot be a plain YAML scalar,
    and only then. Multi-line is the obvious case; the one that actually bites
    is a single line containing ": " — a description that says
    "Not for: engine architecture" is a ScannerError, not a description.

    *chomp* emits `|-` instead of `|`, so a multi-line value round-trips to
    exactly what was passed in rather than gaining a trailing newline. Callers
    writing a ledger field want it; the description renderers do not care, so
    it is opt-in and their output is unchanged.
    """
    text = value.strip()
    if not text:
        return Raw("")
    lines = [ln.rstrip() for ln in text.splitlines()]
    if len(lines) == 1 and _plain_scalar_is_safe(text):
        return Raw(lines[0])
    pad = " " * indent
    header = "|-" if chomp else "|"
    return Raw(header + "\n" + "\n".join(pad + ln if ln else "" for ln in lines))


def as_flow_list(csv: str) -> Raw:
    """Render a comma-separated string as a YAML flow sequence: "a,b" -> "[a,b]".

    Quotes only the elements that need it, so the shape most of the corpus already
    carries -- `issues: [250,251]` -- is emitted byte-identically and a migration has
    nothing to churn.

    The element that needs it is `#17`: `#` opens a YAML comment, so `[#17,#18]` is an
    unterminated flow sequence and the parser blames whichever key it reaches next.
    `--gh-issue` advertises that exact form in its own help text, so it arrives here
    routinely; 9 of 77 live session records were written this way (#255).
    """
    if not csv:
        return Raw("[]")
    out = []
    for raw in csv.split(","):
        item = raw.strip()
        if item and (item[0] in "#&*!|>%@`" or any(c in item for c in ":[]{}\"'")):
            item = "'" + item.replace("'", "''") + "'"
        out.append(item)
    return Raw("[" + ",".join(out) + "]")


def as_scalar(value: str) -> Raw:
    """Render *value* as one frontmatter scalar, in the least invasive form that is valid.

    Three tiers, chosen so the corpus does not churn: a value that is already a safe plain
    scalar is returned verbatim (the overwhelming majority — ids, dates, advisor names,
    `AI#297`), a single hazardous line is single-quoted, and only genuinely multi-line prose
    becomes a block. Quoting unconditionally would rewrite all 166 records on this instance
    and bury the handful that actually changed.

    A quoted scalar is preferred over a block for the single-line case because these fields
    are read by humans in a 12-line header, and because `fm_get` — still the reader in
    `memory/index.py` — returns the literal "|-" for a block and the text for a quote.
    """
    text = value.strip()
    if not text:
        return Raw("")
    if len(text.splitlines()) > 1:
        return as_block(text, chomp=True)
    if _plain_scalar_is_safe(text):
        return Raw(text)
    return Raw("'" + text.replace("'", "''") + "'")


# A frontmatter fence. `render_record` applies this with `.match`, which anchors at
# position 0 — the template must OPEN with the fence. `handoff.md` has no frontmatter and
# a `---` rule in its prose; a second rule would let an unanchored search claim the span
# between them as a header and serialize a paragraph.
_FENCE_RE = re.compile(r"---[ \t]*\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)


def render_record(tpl: Path, values: dict[str, str]) -> str:
    """Render a record template, serializing every value that lands in its frontmatter.

    This is the fix for a defect the engine shipped three times — #255 (reflexion),
    #249 (mention note), #301 (ref_issue) — because each repair was scoped to the writer
    the symptom appeared in. The value that decides whether a record parses is chosen by
    whoever calls the writer, so the check belongs where values meet the fence, not in
    each writer: a template that gains a field gets the guarantee without anyone
    remembering to ask for it.

    Serialization is per-REGION, not per-key. A key may legitimately appear both in the
    header and in the body, and a block scalar dropped into a sentence is nonsense. No
    template does that today (measured 2026-09-15: zero overlap across all four record
    templates) — which is a fact about the corpus, not an invariant, so the split is
    structural rather than trusted.

    Values already carrying YAML (`as_flow_list`, `as_block`, `as_scalar` — anything of
    type `Raw`) pass through untouched.
    """
    tpl = Path(tpl)
    if not tpl.is_file():
        raise FileNotFoundError(f"render_record: {tpl} not found")
    content = tpl.read_text(encoding="utf-8")

    fence = _FENCE_RE.match(content)
    if fence is None:
        return template.render(tpl, values)

    serialized: dict[str, str] = {
        k: v if isinstance(v, Raw) else as_scalar(v) for k, v in values.items()
    }
    head = template.substitute(fence.group(0), serialized)

    # Serializing is the fix; this is the verification of it, and it is not redundant.
    # `as_scalar` guards values it is given — it cannot guard a template edit, or a caller
    # that built a `Raw` by hand and got it wrong. #249 item 1 asks for a parse-check on
    # the written record, and the cheapest place to stand is before the write.
    lost = records.find_lost_values(head.split("---\n", 2)[1])
    if lost:
        raise ValueError(
            f"render_record: {tpl.name} would write a record that loses a value:\n  "
            + "\n  ".join(lost)
        )

    return head + template.substitute(content[fence.end():], values)


def fm_set(file: Path, key: str, value: str) -> None:
    """Replace (or append) `key:` in *file*'s frontmatter, writing *value* VERBATIM.

    Verbatim is the contract: callers pass tokens and timestamps, and quoting those
    would churn every record. It also means this function cannot make prose safe — a
    caller with free text must serialize it first with `as_block`, or it writes a
    document its own readers cannot parse (#249).
    """
    p = Path(file)
    if not p.is_file():
        raise FileNotFoundError(f"fm_set: {file} not found")
    out, in_fm, matched = [], False, False
    for line in p.read_text(encoding="utf-8").splitlines():
        if line == "---":
            if in_fm and not matched:
                out.append(f"{key}: {value}")   # append before closing fence
            in_fm = not in_fm
            out.append(line)
            continue
        if in_fm and line.startswith(f"{key}:"):
            out.append(f"{key}: {value}")
            matched = True
            continue
        out.append(line)
    snapshot_write(p, "\n".join(out) + "\n")


def fm_write(path: Path, kvs: list[tuple[str, str]], body: list[str]) -> None:
    lines = ["---"]
    lines += [f"{k}: {v}" for k, v in kvs]
    lines += ["---", ""]
    lines += body
    snapshot_write(path, "\n".join(lines) + "\n")

"""frontmatter.py — line-based YAML frontmatter r/w. Port of lib/frontmatter.sh.
Values are simple strings; lists stored as "[a,b]". Intentionally NOT a yaml
round-trip — preserves byte-for-byte layout of untouched lines (parity contract)."""
from pathlib import Path

from enginelib.snapshot import snapshot_write


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


def as_block(value: str, indent: int = 2) -> str:
    """Render *value* as the right-hand side of a frontmatter key.

    Emits a `|` block scalar whenever the text cannot be a plain YAML scalar,
    and only then. Multi-line is the obvious case; the one that actually bites
    is a single line containing ": " — a description that says
    "Not for: engine architecture" is a ScannerError, not a description.
    """
    text = value.strip()
    if not text:
        return ""
    lines = [ln.rstrip() for ln in text.splitlines()]
    needs_block = (
        len(lines) > 1
        or ": " in text
        or " #" in text
        or text.endswith(":")
        or text[0] in "#&*!|>'\"%@`-?:,[]{}"
    )
    if not needs_block:
        return lines[0]
    pad = " " * indent
    return "|\n" + "\n".join(pad + ln if ln else "" for ln in lines)


def fm_set(file: Path, key: str, value: str) -> None:
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

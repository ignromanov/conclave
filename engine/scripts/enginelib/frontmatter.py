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

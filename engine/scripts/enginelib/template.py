"""template — render {{key}} placeholders from a file.

render(tpl, values) reads the template file and substitutes every
{{key}} placeholder with the matching value from the dict.  Missing
keys are replaced with the empty string.  Special characters (& / | \\)
and newlines in values are preserved verbatim.
"""

import re
from pathlib import Path

_KEY_RE = re.compile(r"^[a-zA-Z0-9_]+$")
_PLACEHOLDER_RE = re.compile(r"\{\{([a-zA-Z0-9_]+)\}\}")


def render(tpl: Path, values: dict[str, str]) -> str:
    """Read *tpl* and substitute ``{{key}}`` placeholders from *values*.

    Raises:
        FileNotFoundError: if *tpl* does not exist.
        ValueError: if any key in *values* is not ``[a-zA-Z0-9_]+``.
    """
    tpl = Path(tpl)
    if not tpl.is_file():
        raise FileNotFoundError(f"render: {tpl} not found")

    for key in values:
        if not _KEY_RE.fullmatch(key):
            raise ValueError(f"render: invalid key: {key}")

    content = tpl.read_text(encoding="utf-8")

    def _sub(match: re.Match) -> str:
        return values.get(match.group(1), "")

    return _PLACEHOLDER_RE.sub(_sub, content)

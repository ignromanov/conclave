"""enginelib/roster.py — read one dotted key from roster.yaml.

I/O-free core: no stdout, no CLI argument parsing, no process exit. CLI lives in lib/roster.py (shim).

Resolution order (preserved from lib/roster.py):
  1. ROSTER_FILE env var
  2. CONCLAVE_AI_ROOT/VOIDPAY_AI_ROOT + /roster.yaml
  3. engine-relative fallback (../../roster.yaml from this file)

Missing file or missing key → default (empty string).
"""
import os

from ruamel.yaml import YAML

_MISSING = object()


def _resolve(key: str) -> object:
    """Return the raw node at dotted `key`, or `_MISSING` if the file/key is absent."""
    data_root = os.environ.get("CONCLAVE_AI_ROOT") or os.environ.get("VOIDPAY_AI_ROOT")
    path = os.environ.get("ROSTER_FILE") or os.path.join(
        data_root or os.path.join(os.path.dirname(__file__), "..", ".."), "roster.yaml"
    )
    if not os.path.exists(path):
        return _MISSING
    with open(path, encoding="utf-8") as fh:
        data = YAML(typ="safe").load(fh) or {}
    node = data
    for part in key.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return _MISSING
    return node


def roster_get(key: str, default: str = "") -> str:
    """Return the roster value at dotted `key`, or `default` if absent."""
    node = _resolve(key)
    return default if node is _MISSING or node is None else str(node)


def roster_get_list(key: str, default: list[str] | None = None) -> list[str]:
    """Return the roster value at dotted `key` as a list of strings.

    A YAML list → its items stringified; a bare scalar → single-item list;
    absent/null → `default` (empty list). Instances configure e.g.
    `github.sticky_labels: [grant]`; the engine core stays vocabulary-free.
    """
    node = _resolve(key)
    if node is _MISSING or node is None:
        return [] if default is None else default
    if isinstance(node, list):
        return [str(item) for item in node]
    return [str(node)]

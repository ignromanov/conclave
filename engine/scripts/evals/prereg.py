"""prereg.py — what makes P0 a kill-switch instead of a claim.

Spec 104 §2.2: a gate the builder grades themselves is not a gate. So a scored run refuses to
start unless:

  1. `preregistration.yaml` exists in the DATA repo AND is committed — a file you can still edit
     is not a commitment; and
  2. the fingerprints it recorded for the trap set and the scorer still match what is on disk.

(2) is the one that matters. It is what stops the predicate from being "clarified" after the
numbers come in, or a seventh trap from being added once six have disappointed. Without it,
"pre-registered" means "there is a yaml file".

Honest scope: this is tamper-EVIDENT, not tamper-proof. Anyone with the DATA repo can amend the
pre-registration commit and re-fingerprint. What it buys is that doing so leaves a trace, and the
operator signing the verdict (Task 13) is signing against a hash they can recompute. It is a
commitment device between honest parties, not a defence against a determined forger — and it is
labelled as one rather than sold as more.
"""
from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

PREREG_RELPATH = "eval/preregistration.yaml"

# How much of the design a run must actually cover before it is allowed to call itself a run —
# the fraction of (trap, arm, rep) cells holding a usable trial. Pre-registered, because "how much
# data loss invalidates this" is a stopping-rule parameter and must be fixed before the numbers
# exist; defaulted, because the rehearsal pre-registration predates the field and re-fingerprinting
# a committed pre-registration to add it would be exactly the amendment this module exists to make
# visible. rehearsal-n2e (2026-07-27) covered 0.27 and exited 0.
DEFAULT_MIN_OK_RATE = 0.90


class PreregError(RuntimeError):
    """The scored run must not start."""


@dataclass(frozen=True)
class Prereg:
    n: int
    mde: float
    rho: float
    power: float
    threshold: str
    stopping_rule: str
    traps_fingerprint: str
    code_fingerprint: str
    min_ok_rate: float = DEFAULT_MIN_OK_RATE


def fingerprint(paths: list[Path], base: Path | None = None) -> str:
    """sha256 over (relpath, bytes) of each file, sorted by that path. Order-independent, content-
    and membership-sensitive: adding a trap changes it, editing a predicate changes it.

    With `base`, each file enters under its posix path relative to `base`, so two files sharing a
    basename in different directories — or a file moved between directories — change the digest.
    Without `base` the basename is used; acceptable only for a flat single-directory set (the trap
    store), where the basename IS the relative path."""
    def _key(p: Path) -> str:
        return p.relative_to(base).as_posix() if base else p.name

    h = hashlib.sha256()
    for path in sorted(paths, key=_key):
        h.update(_key(path).encode())
        h.update(b"\0")
        h.update(path.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


def _is_committed(repo: Path, rel: str) -> bool:
    tracked = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--error-unmatch", rel],
        capture_output=True,
    )
    if tracked.returncode != 0:
        return False
    dirty = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain", "--", rel],
        capture_output=True,
        text=True,
    )
    return dirty.stdout.strip() == ""


def assert_preregistered(
    data_root: Path,
    traps_dir: Path,
    scorer_paths: list[Path],
    scorer_base: Path | None = None,
) -> Prereg:
    path = data_root / PREREG_RELPATH
    if not path.is_file():
        raise PreregError(f"pre-registration absent: {path} — no scored run may start")

    if not _is_committed(data_root, PREREG_RELPATH):
        raise PreregError(
            f"{PREREG_RELPATH} is not committed (or is dirty) in {data_root} — "
            "an editable pre-registration is not a pre-registration"
        )

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    pre = Prereg(
        n=int(raw["n"]),
        mde=float(raw["mde"]),
        rho=float(raw["rho"]),
        power=float(raw["power"]),
        threshold=str(raw["threshold"]),
        stopping_rule=str(raw["stopping_rule"]),
        traps_fingerprint=str(raw["traps_fingerprint"]),
        code_fingerprint=str(raw["code_fingerprint"]),
        min_ok_rate=float(raw.get("min_ok_rate", DEFAULT_MIN_OK_RATE)),
    )

    now_traps = fingerprint(sorted(traps_dir.glob("*.yaml")))
    if now_traps != pre.traps_fingerprint:
        raise PreregError(
            "traps_fingerprint mismatch — the trap set changed after pre-registration "
            f"(registered {pre.traps_fingerprint[:12]}, on disk {now_traps[:12]})"
        )

    now_code = fingerprint(scorer_paths, base=scorer_base)
    if now_code != pre.code_fingerprint:
        raise PreregError(
            "code_fingerprint mismatch — the scorer changed after pre-registration "
            f"(registered {pre.code_fingerprint[:12]}, on disk {now_code[:12]})"
        )

    return pre

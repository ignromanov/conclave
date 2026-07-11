"""Decouple gate: assert the plugin tree contains zero VoidPay literals.

Scope: agents/, commands/, skills/, hooks/ only.
engine/ is intentionally excluded — its residual VoidPay literals
(~11 files: tests/fixtures/historical decision docs) fall under spec 099's
decouple scope, not this gate.
"""
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]

# Directories covered by this gate.  Listed explicitly so test_gated_dirs_exist
# can assert they all exist — a missing dir makes grep produce empty stdout and
# the no-literals test passes vacuously.
_GATED_DIRS = ["agents", "commands", "skills", "hooks"]


def test_gated_dirs_exist():
    """Each dir in the gate must exist; a missing one lets grep pass vacuously."""
    for name in _GATED_DIRS:
        assert (ROOT / name).is_dir(), f"gated dir absent: {ROOT / name}"


def test_no_voidpay_strings_in_plugin_tree():
    # exclude the research mirror, which legitimately quotes VoidPay history
    r = subprocess.run(
        ["bash","-c",
         f"grep -rnE 'voidpay|ignromanov|/Users/ignat/code/voidpay' "
         f"'{ROOT}/agents' '{ROOT}/commands' '{ROOT}/skills' '{ROOT}/hooks' "
         f"--include='*.md' --include='*.py' --include='*.sh' --include='*.json' "
         f"| grep -v 'docs/research/_mirror' || true"],
        capture_output=True, text=True)
    assert r.stdout.strip() == "", r.stdout

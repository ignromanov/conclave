"""tests/cmd/test_audit_architecture_doc.py — integration tests for `engine audit architecture-doc`.

Ports the 3 bats cases from engine/scripts/tests/audit-architecture-doc.bats.
Uses bare tmp_path with explicit --arch/--scripts-dir/--contracts-dir flags throughout.
"""
from __future__ import annotations

import datetime
from pathlib import Path

from tests.cmd.helpers import run_engine


def _make_fixture(base: Path, today_str: str) -> tuple[Path, Path, Path]:
    """Build the forge/ fixture tree; return (arch_file, scripts_dir, contracts_dir)."""
    scripts_dir = base / "scripts"
    contracts_dir = base / "contracts"
    scripts_dir.mkdir(parents=True)
    contracts_dir.mkdir(parents=True)

    (scripts_dir / "dummy-a.sh").write_text("#!/usr/bin/env bash\n# dummy-a.sh\nset -euo pipefail\n")
    (scripts_dir / "dummy-b.sh").write_text("#!/usr/bin/env bash\n# dummy-b.sh\nset -euo pipefail\n")
    (contracts_dir / "contract-x.md").write_text("# contract-x.md\n")

    arch_file = base / "ARCHITECTURE.md"
    arch_file.write_text(
        f"---\n"
        f"title: Forge Architecture (As-Built)\n"
        f"last-reviewed: {today_str}\n"
        f"covers-as-of-commit: abc1234\n"
        f"pairs-with: ops/specs/049-team-forge/spec.md\n"
        f"---\n"
        f"\n"
        f"## §B — Where is X stored?\n"
        f"\n"
        f"| dummy-a.sh | invoked-by | reads | writes | side-effects |\n"
        f"| dummy-b.sh | invoked-by | reads | writes | side-effects |\n"
        f"\n"
        f"## §C — What breaks if I change X?\n"
        f"\n"
        f"```mermaid\n"
        f"graph TD\n"
        f"  contract-x --> SKILL\n"
        f"```\n"
    )
    return arch_file, scripts_dir, contracts_dir


def test_healthy(tmp_path):
    """Bats case 1: passes on healthy ARCHITECTURE.md."""
    today = datetime.date.today().isoformat()
    arch, scripts_dir, contracts_dir = _make_fixture(tmp_path / "forge", today)
    r = run_engine(
        "audit", "architecture-doc",
        "--arch", str(arch),
        "--scripts-dir", str(scripts_dir),
        "--contracts-dir", str(contracts_dir),
    )
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"


def test_missing_script_row_is_crit(tmp_path):
    """Bats case 2: fails when dummy-b.sh row is missing from §B table → exit 1, output has 'dummy-b.sh'."""
    today = datetime.date.today().isoformat()
    arch, scripts_dir, contracts_dir = _make_fixture(tmp_path / "forge", today)

    # Remove dummy-b.sh line from ARCHITECTURE.md
    text = arch.read_text()
    arch.write_text("\n".join(line for line in text.splitlines() if "dummy-b.sh" not in line) + "\n")

    r = run_engine(
        "audit", "architecture-doc",
        "--arch", str(arch),
        "--scripts-dir", str(scripts_dir),
        "--contracts-dir", str(contracts_dir),
    )
    assert r.returncode == 1, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "dummy-b.sh" in r.stdout, f"stdout={r.stdout!r}"


def test_stale_date_is_crit(tmp_path):
    """Bats case 3: fails when last-reviewed is 2025-01-01 (>30d stale) → exit 1, output has 'stale'."""
    today = datetime.date.today().isoformat()
    arch, scripts_dir, contracts_dir = _make_fixture(tmp_path / "forge", today)

    # Replace today's date with a stale date
    text = arch.read_text()
    arch.write_text(text.replace(f"last-reviewed: {today}", "last-reviewed: 2025-01-01"))

    r = run_engine(
        "audit", "architecture-doc",
        "--arch", str(arch),
        "--scripts-dir", str(scripts_dir),
        "--contracts-dir", str(contracts_dir),
    )
    assert r.returncode == 1, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "stale" in r.stdout, f"stdout={r.stdout!r}"


def test_an_empty_script_tree_is_reported_not_passed(tmp_path):
    """Check 1 grades `every shipped .sh appears in the doc`. With no .sh it grades nothing.

    This is the live state of the repository since spec 099 ported the shell layer: the check
    walks an empty tree, finds no violation, and would pass over any document at all — including
    one naming sixty-one scripts that no longer exist. A vacuous pass reported as cleanliness is
    the failure mode this suite keeps finding (#110, spec 116), so the audit states the denominator
    instead. It is a WARN, not a CRIT: nothing is broken, but nothing was measured either.
    """
    today = datetime.date.today().isoformat()
    arch, scripts_dir, contracts_dir = _make_fixture(tmp_path / "forge", today)
    for sh in scripts_dir.glob("*.sh"):
        sh.unlink()
    # Drop the rows too, so this case isolates the vacuity of check 1. Leaving them would make
    # check 1b fire instead — correctly, but that is the next test's subject, not this one's.
    arch.write_text("\n".join(ln for ln in arch.read_text().splitlines() if ".sh" not in ln) + "\n")

    r = run_engine(
        "audit", "architecture-doc",
        "--arch", str(arch),
        "--scripts-dir", str(scripts_dir),
        "--contracts-dir", str(contracts_dir),
    )
    # 0 clean / 1 crit / 2 warn, per the adapter's own contract — an empty tree is a warning,
    # not a failure: nothing is broken, and that is exactly what makes the silence dangerous.
    assert r.returncode == 2, f"expected the WARN exit, got {r.returncode}: stdout={r.stdout!r}"
    assert "graded 0 scripts" in r.stdout, (
        "the audit passed check 1 over an empty set without saying so — "
        f"stdout={r.stdout!r}"
    )


def test_a_script_the_document_names_but_the_tree_lacks_is_crit(tmp_path):
    """The direction check 1 cannot cover, and the only one that can fail today.

    Check 1 walks the tree and asks whether the document mentions each script. Since spec 099
    deleted the shell layer that tree is empty, so it grades nothing. The live defect runs the
    other way: `skills/forge-operations/ARCHITECTURE.md` names 57 scripts and none of them
    exist. A reader following such a row gets `command not found`, so it is a CRIT.
    """
    today = datetime.date.today().isoformat()
    arch, scripts_dir, contracts_dir = _make_fixture(tmp_path / "forge", today)
    arch.write_text(arch.read_text() + "\n| ghost-script.sh | invoked-by | reads | writes | fx |\n")

    r = run_engine(
        "audit", "architecture-doc",
        "--arch", str(arch),
        "--scripts-dir", str(scripts_dir),
        "--contracts-dir", str(contracts_dir),
    )
    assert r.returncode == 1, f"expected CRIT, got {r.returncode}: stdout={r.stdout!r}"
    assert "ghost-script.sh" in r.stdout, f"stdout={r.stdout!r}"


def test_a_row_that_marks_the_script_retired_is_not_a_violation(tmp_path):
    """Naming a dead script in order to say it is dead is the opposite of a stale claim.

    This is the trap that stopped a gate shipping in PR #338: `commands/feedback.md` mentions
    six shell paths, five inside an illustrative example and one explicitly retiring the path.
    A checker blind to that difference false-positives on the honest text and teaches people to
    silence it. ARCHITECTURE.md already carries the convention — two rows read
    `**deleted (spec 086)** — replaced by ...` — so the audit reads the document's own marker
    rather than inventing a second one.
    """
    today = datetime.date.today().isoformat()
    arch, scripts_dir, contracts_dir = _make_fixture(tmp_path / "forge", today)
    arch.write_text(
        arch.read_text()
        + "\n| ghost-script.sh | **deleted (spec 099)** — replaced by `engine audit bloat` | — | — | — |\n"
    )

    r = run_engine(
        "audit", "architecture-doc",
        "--arch", str(arch),
        "--scripts-dir", str(scripts_dir),
        "--contracts-dir", str(contracts_dir),
    )
    assert r.returncode == 0, (
        "a row that declares the script gone was read as a claim that it exists — "
        f"stdout={r.stdout!r}"
    )


def test_a_test_script_name_is_not_sliced_into_a_ghost(tmp_path):
    """`apply-overlay.test.sh` must not be read as a reference to a file called `test.sh`.

    The naive pattern `[A-Za-z0-9_-]+\\.sh` matches the tail of any dotted script name, so a
    document listing ten `*.test.sh` files would be reported as naming a `test.sh` that has
    never existed in this repository — an absence check manufacturing the absence it reports.
    The live document lists exactly ten such names, which is how this was found.
    """
    today = datetime.date.today().isoformat()
    arch, scripts_dir, contracts_dir = _make_fixture(tmp_path / "forge", today)
    (scripts_dir / "tests").mkdir()
    (scripts_dir / "tests" / "dummy-a.test.sh").write_text("#!/usr/bin/env bash\n")
    arch.write_text(arch.read_text() + "\ndummy-a.test.sh\n")

    r = run_engine(
        "audit", "architecture-doc",
        "--arch", str(arch),
        "--scripts-dir", str(scripts_dir),
        "--contracts-dir", str(contracts_dir),
    )
    assert "test.sh', which does not exist" not in r.stdout, (
        f"a dotted name was sliced into a ghost reference — stdout={r.stdout!r}"
    )
    assert r.returncode == 0, f"stdout={r.stdout!r}"

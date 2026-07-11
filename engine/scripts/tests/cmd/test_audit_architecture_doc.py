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

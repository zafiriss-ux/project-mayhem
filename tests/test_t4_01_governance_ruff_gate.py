from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

GOVERNANCE_FILES = (
    "titan/science/governance_contracts.py",
    "titan/science/governance_engine.py",
)


def test_governance_files_are_ruff_clean() -> None:
    ruff_bin = shutil.which("ruff")
    cmd = ["ruff", "check", *GOVERNANCE_FILES] if ruff_bin else [sys.executable, "-m", "ruff", "check", *GOVERNANCE_FILES]

    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )

    if proc.returncode == 127:
        pytest.skip("ruff is not installed in this environment")

    assert proc.returncode == 0, (
        "Governance lint gate failed for policy-critical files.\n"
        f"Command: {' '.join(cmd)}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )

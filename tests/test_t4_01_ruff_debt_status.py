from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest


DEBT_DOC = Path("TECHNICAL_DEBT.md")
T4_01_HEADER = "### T4-01 · Ruff debt burn-down (lint hygiene)"


def _ruff_error_count() -> int:
    ruff_bin = shutil.which("ruff")
    cmd = ["ruff", "check", ".", "--statistics"] if ruff_bin else [sys.executable, "-m", "ruff", "check", ".", "--statistics"]

    proc = subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
    )
    out = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode == 127:
        pytest.skip("ruff is not installed in this environment")

    match = re.search(r"Found\s+(\d+)\s+error[s]?", out)
    assert match, f"Could not parse Ruff statistics output (cmd={cmd!r}, rc={proc.returncode}):\n{out}"
    return int(match.group(1))


def test_t4_01_remains_open_until_ruff_findings_are_burned_down():
    doc = DEBT_DOC.read_text(encoding="utf-8")
    assert T4_01_HEADER in doc, "T4-01 section must exist in TECHNICAL_DEBT.md"

    t4_01_is_open = f"{T4_01_HEADER} 🟡" in doc
    findings = _ruff_error_count()

    if t4_01_is_open:
        assert findings > 0, (
            "T4-01 is marked open, but Ruff reports zero errors. "
            "Update TECHNICAL_DEBT.md status."
        )
    else:
        assert findings == 0, (
            "T4-01 appears closed, but Ruff findings still exist. "
            "Do not close T4-01 before burn-down execution."
        )

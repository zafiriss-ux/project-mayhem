from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"



def test_ruff_blocking_gate_is_config_only() -> None:
    content = WORKFLOW.read_text(encoding="utf-8")

    match = re.search(r"BLOCKING_FOLDERS=\((.*?)\)", content, flags=re.DOTALL)
    assert match, "BLOCKING_FOLDERS section is missing in CI workflow"

    blocking_section = match.group(1)
    folders = [line.strip() for line in blocking_section.splitlines() if line.strip()]
    assert folders == ["titan/config"], f"Expected config-only blocking gate, got: {folders}"



def test_titan_config_is_ruff_clean() -> None:
    if importlib.util.find_spec("ruff") is None:
        pytest.skip("ruff is not installed in this environment")

    cmd = [sys.executable, "-m", "ruff", "check", "titan/config"]

    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)

    assert proc.returncode == 0, (
        "Expected titan/config to be Ruff-clean for blocking CI gate.\n"
        f"Command: {cmd!r}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )

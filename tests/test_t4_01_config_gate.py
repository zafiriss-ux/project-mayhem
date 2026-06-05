from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/ci.yml"


def _get_blocking_targets() -> list[str]:
    content = WORKFLOW.read_text(encoding="utf-8")

    match = re.search(r"BLOCKING_TARGETS=\((.*?)\)", content, flags=re.DOTALL)
    assert match, "BLOCKING_TARGETS section is missing in CI workflow"

    blocking_section = match.group(1)
    return [line.strip() for line in blocking_section.splitlines() if line.strip()]


@pytest.mark.integration
@pytest.mark.governance
def test_ruff_blocking_gate_includes_promoted_targets() -> None:
    targets = _get_blocking_targets()
    assert targets == [
        "titan/config",
    ], f"Unexpected blocking targets: {targets}"


@pytest.mark.integration
@pytest.mark.governance
def test_blocking_targets_are_ruff_clean() -> None:
    if importlib.util.find_spec("ruff") is None:
        pytest.skip("ruff is not installed in this environment")

    targets = _get_blocking_targets()
    cmd = [sys.executable, "-m", "ruff", "check", *targets]

    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)

    assert proc.returncode == 0, (
        "Expected CI blocking Ruff targets to be clean.\n"
        f"Command: {cmd!r}\n"
        f"stdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )

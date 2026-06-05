import subprocess
from pathlib import Path

import pytest


@pytest.mark.integration
def test_gui_wizard_is_ruff_clean() -> None:
    target = Path("launcher/gui_wizard.py")

    result = subprocess.run(
        ["ruff", "check", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.integration
def test_wizard_is_ruff_clean() -> None:
    target = Path("launcher/wizard.py")

    result = subprocess.run(
        ["ruff", "check", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr

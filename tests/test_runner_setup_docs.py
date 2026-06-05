"""C-W12: verify docs/RUNNER_SETUP.md exists (self-hosted runner guide)."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.unit
@pytest.mark.governance
def test_runner_setup_docs_exists() -> None:
    assert Path("docs/RUNNER_SETUP.md").exists()

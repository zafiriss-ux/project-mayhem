"""C-W12: verify docs/RUNNER_SETUP.md exists (self-hosted runner guide)."""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
@pytest.mark.governance
def test_runner_setup_docs_exists() -> None:
    assert (REPO_ROOT / "docs/RUNNER_SETUP.md").exists()

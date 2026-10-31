"""D2 Alembic baseline freeze tests.

Verifies that the Alembic freeze documentation exists and env.py carries
the required notice to prevent accidental SQLite schema collision.
"""
from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_alembic_readme_freeze_exists():
    assert (REPO_ROOT / "alembic/README_FREEZE.md").exists()


@pytest.mark.unit
def test_alembic_env_has_freeze_notice():
    content = (REPO_ROOT / "alembic/env.py").read_text()
    assert "FREEZE NOTICE" in content or "PostgreSQL" in content

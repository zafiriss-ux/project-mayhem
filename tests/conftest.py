"""Shared test fixture factories.

Use these factories to construct common test objects (athlete profile, database manager,
and governance engine) so schema/constructor changes are centralized and fixture drift is
prevented across the test suite.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from titan.core.athlete import UniversalAthleteProfile
from titan.core.database import DatabaseManager
from titan.science.governance_engine import GovernanceEngine


@pytest.fixture
def athlete_profile_factory() -> Callable[..., UniversalAthleteProfile]:
    """Create athlete profiles with optional demographics/HR setup and attribute overrides."""

    def _factory(
        *,
        name: str | None = None,
        demographics: dict[str, Any] | None = None,
        hr_data: dict[str, Any] | None = None,
        overrides: dict[str, Any] | None = None,
    ) -> UniversalAthleteProfile:
        profile = UniversalAthleteProfile()
        if name is not None:
            profile.name = name
        if demographics:
            profile.set_demographics(**demographics)
        if hr_data:
            profile.set_hr_data(**hr_data)
        if overrides:
            for key, value in overrides.items():
                setattr(profile, key, value)
        return profile

    return _factory


@pytest.fixture
def db_manager_factory(tmp_path: Path) -> Callable[..., DatabaseManager]:
    """Create DatabaseManager instances rooted in pytest tmp_path by default."""

    def _factory(*, db_name: str = "test.db", db_dir: Path | None = None) -> DatabaseManager:
        return DatabaseManager(db_name=db_name, db_dir=tmp_path if db_dir is None else db_dir)

    return _factory


@pytest.fixture
def governance_engine_factory() -> Callable[[], GovernanceEngine]:
    """Create governance engine instances from a single shared test factory."""

    def _factory() -> GovernanceEngine:
        return GovernanceEngine()

    return _factory

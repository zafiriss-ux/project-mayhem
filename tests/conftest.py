"""Shared test fixture factories.

Use these factories to construct common test objects (athlete profile, database manager,
governance engine, Garmin sync results, and daily coach contexts) so schema/constructor
changes are centralized and fixture drift is prevented across the test suite.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest

from titan.core.athlete import UniversalAthleteProfile
from titan.core.database import DatabaseManager
from titan.orchestration.contracts import (
    DailyCoachContext,
    DailyCoachContextContract,
    GarminSyncResult,
    GarminSyncResultContract,
    HRVSyncMetricsContract,
)
from titan.science.governance_engine import GovernanceEngine


def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="Regenerate governance_golden.json. Requires ADR reference in commit.",
    )


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


@pytest.fixture
def garmin_sync_result_factory() -> Callable[..., GarminSyncResult]:
    """Create GarminSyncResult payloads with safe defaults and optional overrides.

    Prevents manual dict construction across integration tests.  Any field can
    be overridden to test specific sync states (empty HRV, stale data, etc.).
    """

    def _factory(
        *,
        activities: list[Mapping[str, object]] | None = None,
        weight: list[Mapping[str, object]] | None = None,
        sleep: list[Mapping[str, object]] | None = None,
        hrv: list[Mapping[str, object]] | None = None,
        days_back: int = 7,
        synced_days: int = 7,
        skipped_days: int = 0,
        status: str | None = None,
        data_trust: Mapping[str, object] | None = None,
    ) -> GarminSyncResult:
        hrv_metrics = HRVSyncMetricsContract(
            days_back=days_back,
            synced_days=synced_days,
            skipped_days=skipped_days,
        ).to_payload()
        return GarminSyncResultContract(
            activities=activities or [],
            weight=weight or [],
            sleep=sleep or [],
            hrv=hrv or [],
            hrv_sync_metrics=hrv_metrics,
            status=status,
            data_trust=data_trust,
        ).to_payload()

    return _factory


@pytest.fixture
def daily_coach_context_factory() -> Callable[..., DailyCoachContext]:
    """Create DailyCoachContext payloads with physiologically safe defaults.

    Prevents manual field-by-field construction in orchestration tests.
    Defaults represent a healthy, well-recovered athlete ready to train.
    Override any field to test specific governance/readiness scenarios.
    """

    def _factory(
        *,
        db: object = None,
        cs_tracker: object = None,
        afi_constraints: Mapping[str, object] | None = None,
        intensity_gate_result: Mapping[str, object] | None = None,
        readiness_score: float = 80.0,
        glycogen_debt: float = 2.0,
        fatigue_level: str = "LOW",
        acwr: float = 1.0,
        days_since_last_vo2: int | None = 3,
        fueling_confirmed: bool = True,
        planned_duration_min: int = 60,
        today_hrv: float = 65.0,
        baseline_hrv: float = 63.0,
        hrv_std_dev: float = 4.0,
        today_rhr: int = 52,
        baseline_rhr: float = 51.0,
        sleep_score: int = 78,
        subjective_fatigue_score: int = 3,
        tsb_value: float = 5.0,
        injury_flag: bool = False,
        priority_vector: Mapping[str, float] | None = None,
        lock_thresholds: Mapping[str, float] | None = None,
        garmin_data_stale: bool | None = None,
        hrv_stress_context: str | None = None,
        data_trust: Mapping[str, object] | None = None,
    ) -> DailyCoachContext:
        return DailyCoachContextContract(
            db=db,
            cs_tracker=cs_tracker,
            afi_constraints=afi_constraints or {},
            intensity_gate_result=intensity_gate_result or {"gate": "GREEN"},
            readiness_score=readiness_score,
            glycogen_debt=glycogen_debt,
            fatigue_level=fatigue_level,
            acwr=acwr,
            days_since_last_vo2=days_since_last_vo2,
            fueling_confirmed=fueling_confirmed,
            planned_duration_min=planned_duration_min,
            today_hrv=today_hrv,
            baseline_hrv=baseline_hrv,
            hrv_std_dev=hrv_std_dev,
            today_rhr=today_rhr,
            baseline_rhr=baseline_rhr,
            sleep_score=sleep_score,
            subjective_fatigue_score=subjective_fatigue_score,
            tsb_value=tsb_value,
            injury_flag=injury_flag,
            priority_vector=priority_vector or {},
            lock_thresholds=lock_thresholds or {},
            garmin_data_stale=garmin_data_stale,
            hrv_stress_context=hrv_stress_context,
            data_trust=data_trust,
        ).to_payload()

    return _factory

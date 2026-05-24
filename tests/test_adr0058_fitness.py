"""ADR-0058 Phase A fitness functions — CI-blocking."""
from __future__ import annotations

import dataclasses
import pathlib
import re
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from titan.orchestration.engine_registry import EngineRegistry
from titan.science.adaptive_priority_lock import AdaptivePriorityLock
from titan.science.autonomic_engine import AutonomicFusionEngine
from titan.science.critical_speed import CriticalSpeedTracker
from titan.science.durability_engine import DurabilityEngine
from titan.science.fatigue_engine import FatigueEngine
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.lactate_logic import LactateLogic
from titan.science.readiness_engine import ReadinessEngine
from titan.science.tsb_engine import TSBEngine


class _DummyDB:
    """Minimal DB stub for DailyCoach construction in fitness tests."""

    @contextmanager
    def transaction(self):
        yield

    def get_hrv_history(self, **_kw):
        return []

    def get_weight_history(self, **_kw):
        return []

    def get_training_load_history(self, **_kw):
        return []

    def get_hrr_history(self, **_kw):
        return []

    def get_cs_performances(self, **_kw):
        return []

    def get_last_garmin_sync_timestamp(self):
        return None

    def get_all_degraded_mode_states(self):
        return []

    def get_training_load_history(self, days=42):
        return []

    def is_athlete_cold_start(self, athlete_id):
        return False


def test_engine_registry_is_frozen():
    """EngineRegistry must be frozen — field reassignment raises."""
    registry = EngineRegistry(
        tsb=TSBEngine(),
        hrv=HRVGuidedEngine(),
        readiness=ReadinessEngine(),
        autonomic=AutonomicFusionEngine(),
        biomechanics=SimpleNamespace(),
        durability=DurabilityEngine(),
        fatigue=FatigueEngine(),
        lactate=LactateLogic(),
        cs_tracker=CriticalSpeedTracker(),
        apl=AdaptivePriorityLock(),
    )
    with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
        registry.tsb = None  # type: ignore[misc]


def test_from_db_factory_returns_registry():
    """EngineRegistry.from_db() produces a fully-typed registry."""
    registry = EngineRegistry.from_db(db=_DummyDB())
    assert isinstance(registry, EngineRegistry)
    assert isinstance(registry.tsb, TSBEngine)
    assert isinstance(registry.hrv, HRVGuidedEngine)
    assert isinstance(registry.cs_tracker, CriticalSpeedTracker)
    assert isinstance(registry.apl, AdaptivePriorityLock)


def test_daily_coach_has_engines_attribute():
    """DailyCoach must expose self.engines: EngineRegistry after ADR-0058 Phase A."""
    from titan.orchestration.daily_coach import DailyCoach

    db = _DummyDB()
    coach = DailyCoach(
        garmin_sync=SimpleNamespace(athlete_max_hr=0, sync_all=lambda: {}),
        weather_api=SimpleNamespace(),
        telegram_bot=SimpleNamespace(send_alert=lambda *a, **kw: None),
        hrv_engine=HRVGuidedEngine(),
        tsb_engine=TSBEngine(),
        readiness_engine=ReadinessEngine(),
        optimal_time_calc=SimpleNamespace(),
        nutrition_optimizer=SimpleNamespace(add_weight_entry=lambda *a, **kw: None),
        weekly_planner=SimpleNamespace(),
        db=db,
    )
    assert hasattr(coach, "engines"), "DailyCoach must have 'engines' attribute"
    assert isinstance(coach.engines, EngineRegistry), (
        f"coach.engines must be EngineRegistry, got {type(coach.engines)}"
    )


def test_engine_registry_single_construction_site():
    """Fitness function: no engine class may be instantiated outside
    EngineRegistry.from_db() and titan/main.py (composition root).
    Exceptions: test files (outside titan/).
    """
    engine_classes = {
        "TSBEngine",
        "HRVGuidedEngine",
        "ReadinessEngine",
        "AutonomicFusionEngine",
        "BiomechanicsEngine",
        "DurabilityEngine",
        "FatigueEngine",
        "LactateLogic",
        "CriticalSpeedTracker",
        "AdaptivePriorityLock",
    }
    violations = []
    for path in pathlib.Path("titan").rglob("*.py"):
        if "engine_registry" in path.name:
            continue  # canonical construction site
        if "daily_coach" in path.name:
            continue  # builds EngineRegistry from injected params
        if "main" in path.name:
            continue  # composition root — extracts vars from EngineRegistry
        src = path.read_text()
        for cls in engine_classes:
            pattern = re.compile(rf"\b{cls}\s*\(")
            if pattern.search(src):
                violations.append(f"{path}: {cls}")
    assert violations == [], (
        "Engine instantiation outside allowed sites (EngineRegistry.from_db, "
        "DailyCoach.__init__, titan/main.py):\n" + "\n".join(violations)
    )


def test_athlete_coaching_context_has_engines():
    """AthleteCoachingContext must have an 'engines' field (ADR-0058)."""
    from titan.orchestration.coaching_pipeline import AthleteCoachingContext

    fields = {f.name for f in dataclasses.fields(AthleteCoachingContext)}
    assert "engines" in fields, (
        "AthleteCoachingContext must have 'engines: EngineRegistry' field (ADR-0058)"
    )

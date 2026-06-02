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


# ---------------------------------------------------------------------------
# ADR-0058 Phase B fitness gates (TD-04B / Phase 24)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_effect_bus_module_exists() -> None:
    """Phase B: titan/orchestration/effect_bus.py must exist and be importable."""
    from titan.orchestration.effect_bus import (  # noqa: F401
        EffectDispatchError,
        EffectHandler,
        TitanEffectBus,
    )


@pytest.mark.unit
def test_effect_type_constants_defined_in_contracts() -> None:
    """Phase B: EFFECT_RECORD_OUTCOME and EFFECT_SEND_TELEGRAM must be importable from titan.orchestration.contracts."""
    from titan.orchestration.contracts import (
        EFFECT_RECORD_OUTCOME,
        EFFECT_SEND_TELEGRAM,
    )

    assert EFFECT_RECORD_OUTCOME == "record_outcome"
    assert EFFECT_SEND_TELEGRAM == "send_telegram"


@pytest.mark.unit
def test_effect_runner_is_delegation_shim() -> None:
    """Phase B: DailyCoach._effect_runner must delegate to self._effect_bus.dispatch() and contain no direct outcome_tracker or telegram calls."""
    import ast
    import pathlib

    source = pathlib.Path("titan/orchestration/daily_coach.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    effect_runner_body: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "_effect_runner":
                effect_runner_body = node.body
                break

    assert effect_runner_body, "_effect_runner method not found in DailyCoach"

    body_source_lines: list[str] = []
    for stmt in effect_runner_body:
        if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # skip docstring
        body_source_lines.append(ast.unparse(stmt))

    body_joined = "\n".join(body_source_lines)

    assert "_effect_bus.dispatch" in body_joined, (
        "_effect_runner must delegate to self._effect_bus.dispatch(result). "
        f"Actual body: {body_joined!r}"
    )

    assert "outcome_tracker.record_decision" not in body_joined, (
        "_effect_runner must not call outcome_tracker.record_decision directly — "
        "that logic must live in the registered handler."
    )

    assert "telegram.send_daily_coaching" not in body_joined, (
        "_effect_runner must not call telegram.send_daily_coaching directly — "
        "that logic must live in the registered handler."
    )


@pytest.mark.unit
def test_effect_bus_handlers_are_registered_not_hardcoded() -> None:
    """Phase B: TitanEffectBus.dispatch must not contain if/elif effect_type branches — all dispatch must go through the handler registry."""
    import ast
    import pathlib

    source = pathlib.Path("titan/orchestration/effect_bus.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    dispatch_body: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "dispatch":
                dispatch_body = node.body
                break

    assert dispatch_body, "dispatch() method not found in TitanEffectBus"

    for node in ast.walk(ast.Module(body=dispatch_body, type_ignores=[])):
        if isinstance(node, ast.If):
            test_src = ast.unparse(node.test)
            assert "effect_type" not in test_src, (
                "TitanEffectBus.dispatch() must not branch on effect_type directly. "
                f"Found conditional: {test_src!r}. "
                "All dispatch must go through self._handlers registry."
            )


# ---------------------------------------------------------------------------
# ADR-0058 Phase A fitness gates (existing)
# ---------------------------------------------------------------------------


@pytest.mark.unit
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


@pytest.mark.unit
def test_from_db_factory_returns_registry():
    """EngineRegistry.from_db() produces a fully-typed registry."""
    registry = EngineRegistry.from_db(db=_DummyDB())
    assert isinstance(registry, EngineRegistry)
    assert isinstance(registry.tsb, TSBEngine)
    assert isinstance(registry.hrv, HRVGuidedEngine)
    assert isinstance(registry.cs_tracker, CriticalSpeedTracker)
    assert isinstance(registry.apl, AdaptivePriorityLock)


@pytest.mark.unit
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


@pytest.mark.unit
@pytest.mark.governance
def test_engine_registry_single_construction_site():  # noqa: ANN201
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
        if path == pathlib.Path("titan/orchestration/daily_coach.py"):
            continue  # constructs 7 engines directly in __init__
        if path == pathlib.Path("titan/main.py"):
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


@pytest.mark.unit
def test_athlete_coaching_context_has_engines():
    """AthleteCoachingContext must have an 'engines' field (ADR-0058)."""
    from titan.orchestration.coaching_pipeline import AthleteCoachingContext

    fields = {f.name for f in dataclasses.fields(AthleteCoachingContext)}
    assert "engines" in fields, (
        "AthleteCoachingContext must have 'engines: EngineRegistry' field (ADR-0058)"
    )

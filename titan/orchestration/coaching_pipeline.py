from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from titan.orchestration.contracts import DecisionResult, GarminSyncResult

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager


@runtime_checkable
class CoachCallables(Protocol):
    """
    Explicit callable contract for coaching_pipeline() callers.
    Replaces coach: Any (T5-07-L3-D, ADR-0046).
    Only methods actually consumed by coaching_pipeline() are declared here.
    Do NOT add speculative methods — follow T5-24 precedent.
    """

    def _decision_pipeline(self, **kwargs: Any) -> DecisionResult: ...
    def _effect_runner(self, result: DecisionResult) -> bool: ...


@dataclass(frozen=True)
class AthleteCoachingContext:
    athlete_id: str
    coach: CoachCallables
    garmin_data: GarminSyncResult
    soreness: int
    subjective_fatigue_score: int
    today_rhr: int
    today_sleep_score: int
    today_sleep_hours: float
    baseline_rhr_for_comparison: float
    persistence_degraded: bool
    garmin_data_stale: bool
    latest_hrv: float
    baseline_hrv: float
    hrv_summary: dict[str, Any]
    afi_final: float
    afi_constraints: dict[str, Any]
    tsb_value: float
    tsb_status: str
    cs_thermal: float | None
    garmin_trust: Any
    garmin_report_payload: dict[str, Any]
    startup_hydration_confidence: dict[str, bool]
    startup_confidence_applies: bool
    # Cold-start protocol fields (ADR-0033 L3-C) — optional, default-safe
    db: DatabaseManager | None = None
    cold_start_active: bool = False
    cold_start_conservative_factor: float = 1.0


def coaching_pipeline(context: AthleteCoachingContext) -> bool:
    """Run decision pipeline and effect runner for one athlete context."""
    _athlete_id = context.athlete_id
    _was_cold_start = False

    if context.db is not None:
        _is_cold_start = context.db.is_athlete_cold_start(_athlete_id)
        if _is_cold_start:
            from titan.config.thresholds import COLD_START_SOFT_GATE_CONSERVATIVE_FACTOR
            context = dataclasses.replace(
                context,
                cold_start_active=True,
                cold_start_conservative_factor=COLD_START_SOFT_GATE_CONSERVATIVE_FACTOR,
            )
            _was_cold_start = True
            _exit_met = context.db.check_and_exit_cold_start(_athlete_id)
            if _exit_met:
                context = dataclasses.replace(
                    context,
                    cold_start_active=False,
                    cold_start_conservative_factor=1.0,
                )
                _was_cold_start = False

    decision_result: DecisionResult = context.coach._decision_pipeline(
        garmin_data=context.garmin_data,
        soreness=context.soreness,
        subjective_fatigue_score=context.subjective_fatigue_score,
        today_rhr=context.today_rhr,
        today_sleep_score=context.today_sleep_score,
        today_sleep_hours=context.today_sleep_hours,
        baseline_rhr_for_comparison=context.baseline_rhr_for_comparison,
        persistence_degraded=context.persistence_degraded,
        garmin_data_stale=context.garmin_data_stale,
        latest_hrv=context.latest_hrv,
        baseline_hrv=context.baseline_hrv,
        hrv_summary=context.hrv_summary,
        afi_final=context.afi_final,
        afi_constraints=context.afi_constraints,
        tsb_value=context.tsb_value,
        tsb_status=context.tsb_status,
        cs_thermal=context.cs_thermal,
        garmin_trust=context.garmin_trust,
        garmin_report_payload=context.garmin_report_payload,
        startup_hydration_confidence=context.startup_hydration_confidence,
        startup_confidence_applies=context.startup_confidence_applies,
    )

    if context.db is not None and _was_cold_start:
        context.db.increment_cold_start_sessions(_athlete_id)

    return context.coach._effect_runner(decision_result)

"""Typed payload contracts for critical orchestration boundaries."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import NotRequired, Protocol, TypedDict, runtime_checkable

# ---------------------------------------------------------------------------
# PlannedEffect canonical discriminant constants (ADR-0058 Phase B)
#
# These are the EXHAUSTIVE set of effect_type values.  Any new effect type
# MUST be added here and to ADR-0058 before use.  The TitanEffectBus handler
# registry is keyed on these constants.
# ---------------------------------------------------------------------------
EFFECT_RECORD_OUTCOME: str = "record_outcome"  # write decision to OutcomeTracker (DB)
EFFECT_SEND_TELEGRAM: str = "send_telegram"    # deliver coaching briefing via Telegram


class HRVSyncMetrics(TypedDict):
    days_back: int
    synced_days: int
    skipped_days: int


@dataclass(frozen=True)
class HRVSyncMetricsContract:
    days_back: int
    synced_days: int
    skipped_days: int

    def to_payload(self) -> HRVSyncMetrics:
        return {
            "days_back": self.days_back,
            "synced_days": self.synced_days,
            "skipped_days": self.skipped_days,
        }


class GarminSyncResult(TypedDict):
    activities: list[Mapping[str, object]]
    weight: list[Mapping[str, object]]
    sleep: list[Mapping[str, object]]
    hrv: list[Mapping[str, object]]
    hrv_sync_metrics: HRVSyncMetrics
    status: NotRequired[str]
    data_trust: NotRequired[Mapping[str, object]]
    data_age_hours: NotRequired[float]


@dataclass(frozen=True)
class GarminSyncResultContract:
    activities: list[Mapping[str, object]]
    weight: list[Mapping[str, object]]
    sleep: list[Mapping[str, object]]
    hrv: list[Mapping[str, object]]
    hrv_sync_metrics: HRVSyncMetrics
    status: str | None = None
    data_trust: Mapping[str, object] | None = None
    data_age_hours: float | None = None

    def to_payload(self) -> GarminSyncResult:
        payload: GarminSyncResult = {
            "activities": self.activities,
            "weight": self.weight,
            "sleep": self.sleep,
            "hrv": self.hrv,
            "hrv_sync_metrics": self.hrv_sync_metrics,
        }
        if self.status is not None:
            payload["status"] = self.status
        if self.data_trust is not None:
            payload["data_trust"] = self.data_trust
        if self.data_age_hours is not None:
            payload["data_age_hours"] = self.data_age_hours
        return payload


class TodaySessionPlan(TypedDict):
    session_type: str
    duration_min: int
    volume_pct: NotRequired[float]
    distance_km: NotRequired[float]
    details: NotRequired[str]
    phase: NotRequired[str]
    governance_locks_applied: NotRequired[list[str]]
    governance_clean: NotRequired[bool]
    intensity_gate_result: NotRequired[Mapping[str, object]]
    fueling_gate: NotRequired[Mapping[str, object]]
    vo2_eligibility: NotRequired[Mapping[str, object]]
    hrv_stress_context: NotRequired[str]


class DailyCoachContext(TypedDict):
    db: object
    cs_tracker: object
    afi_constraints: Mapping[str, object]
    intensity_gate_result: Mapping[str, object]
    readiness_score: float
    glycogen_debt: float
    fatigue_level: str
    acwr: float | None
    days_since_last_vo2: int | None
    fueling_confirmed: bool
    planned_duration_min: int
    today_hrv: float | None
    baseline_hrv: float
    hrv_std_dev: float
    today_rhr: int
    baseline_rhr: float
    sleep_score: int
    subjective_fatigue_score: int
    tsb_value: float
    injury_flag: bool
    priority_vector: Mapping[str, float]
    lock_thresholds: Mapping[str, float]
    garmin_data_stale: NotRequired[bool]
    hrv_stress_context: NotRequired[str]
    data_trust: NotRequired[Mapping[str, object]]


@dataclass(frozen=True)
class DailyCoachContextContract:
    db: object
    cs_tracker: object
    afi_constraints: Mapping[str, object]
    intensity_gate_result: Mapping[str, object]
    readiness_score: float
    glycogen_debt: float
    fatigue_level: str
    acwr: float | None
    days_since_last_vo2: int | None
    fueling_confirmed: bool
    planned_duration_min: int
    today_hrv: float | None
    baseline_hrv: float
    hrv_std_dev: float
    today_rhr: int
    baseline_rhr: float
    sleep_score: int
    subjective_fatigue_score: int
    tsb_value: float
    injury_flag: bool
    priority_vector: Mapping[str, float]
    lock_thresholds: Mapping[str, float]
    garmin_data_stale: bool | None = None
    hrv_stress_context: str | None = None
    data_trust: Mapping[str, object] | None = None

    def to_payload(self) -> DailyCoachContext:
        payload: DailyCoachContext = {
            "db": self.db,
            "cs_tracker": self.cs_tracker,
            "afi_constraints": self.afi_constraints,
            "intensity_gate_result": self.intensity_gate_result,
            "readiness_score": self.readiness_score,
            "glycogen_debt": self.glycogen_debt,
            "fatigue_level": self.fatigue_level,
            "acwr": self.acwr,
            "days_since_last_vo2": self.days_since_last_vo2,
            "fueling_confirmed": self.fueling_confirmed,
            "planned_duration_min": self.planned_duration_min,
            "today_hrv": self.today_hrv,
            "baseline_hrv": self.baseline_hrv,
            "hrv_std_dev": self.hrv_std_dev,
            "today_rhr": self.today_rhr,
            "baseline_rhr": self.baseline_rhr,
            "sleep_score": self.sleep_score,
            "subjective_fatigue_score": self.subjective_fatigue_score,
            "tsb_value": self.tsb_value,
            "injury_flag": self.injury_flag,
            "priority_vector": self.priority_vector,
            "lock_thresholds": self.lock_thresholds,
        }
        if self.garmin_data_stale is not None:
            payload["garmin_data_stale"] = self.garmin_data_stale
        if self.hrv_stress_context:
            payload["hrv_stress_context"] = self.hrv_stress_context
        if self.data_trust is not None:
            payload["data_trust"] = self.data_trust
        return payload



class DailyCoachingPayload(TypedDict):
    session_type: str
    duration: str
    details: str
    governance_locks: list[str]
    primary_reason: NotRequired[str]
    actionable_guidance: NotRequired[str]
    optimal_time: str
    dew_point: float | str
    conditions: str
    hrv_status: str
    hrv_value: float
    hrv_baseline: float
    afi: float
    sleep_quality: int
    sleep_hours: float
    readiness_score: float | str
    subjective_fatigue_score: int
    fatigue_level: str
    fatigue_tags: list[str]
    tsb: float
    tsb_status: str
    cs_smoothed: float | None
    cs_thermal: float | None
    archetype: str
    glycogen_debt: float
    glycogen_status: str
    glycogen_protocol: Mapping[str, object]
    electrolyte_alert: Mapping[str, object]
    nutrition_plan: str
    governance_report: Mapping[str, object]
    intensity_gate_result: Mapping[str, object] | None
    fueling_gate: Mapping[str, object] | None
    vo2_eligibility: Mapping[str, object] | None
    data_trust: NotRequired[Mapping[str, object]]


@dataclass(frozen=True)
class PlannedEffect:
    """A single side-effect to be executed by the Effect Runner.

    effect_type discriminant values (exhaustive):
      'record_outcome'  — write governance decision to outcome_tracker (DB)
      'send_telegram'   — deliver coaching briefing via Telegram
    """

    effect_type: str  # discriminant (see docstring)
    payload: Mapping[str, object]  # effect-specific data, frozen at decision time


@dataclass(frozen=True)
class DecisionResult:
    """Immutable output of the Decision Pipeline (steps 7–11).

    Invariant: constructed without executing any side-effects.
    The same DecisionResult can be replayed against any EffectRunner.

    decision_trace required keys: hrv, tsb, acwr, lock_codes_active,
    session_planned_pre_governance, locks_applied, governance_clean, phase,
    vlg_color, afi_value, readiness_score, glycogen_debt.
    """

    session_plan: TodaySessionPlan  # post-governance recommendation
    coaching_payload: DailyCoachingPayload  # Telegram delivery content
    planned_effects: tuple["PlannedEffect", ...]  # ordered effects (tuple — immutable)
    decision_trace: Mapping[str, object]  # forensic replay data
    snapshot_at: str  # ISO-8601 timestamp of state snapshot


class AthleteProfile(TypedDict):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    max_hr: int
    threshold_hr: int
    phase: str
    goal: str




@runtime_checkable
class BiomechanicsEngineProtocol(Protocol):
    ...


class TitanContext(TypedDict):
    garmin: object
    weather: object
    telegram: object
    hrv_engine: object
    tsb_engine: object
    acwr_engine: object
    readiness_engine: object
    glycogen_model: object
    drift_engine: object
    lactate_logic: object
    trimp_engine: object
    fatigue_engine: object
    adaptive_memory: object
    biomechanics: BiomechanicsEngineProtocol
    efficiency_engine: object
    durability_engine: object
    critical_speed: object
    rcp_engine: object
    weekly_planner: object
    optimal_time_calc: object
    nutrition_optimizer: object
    daily_coach: object
    db: object
    athlete_profile: AthleteProfile
    last_garmin_data: Mapping[str, object]
    last_weekly_plan: Mapping[str, object] | None
    today_session_type: str


@dataclass(frozen=True)
class TitanContextContract:
    garmin: object
    weather: object
    telegram: object
    hrv_engine: object
    tsb_engine: object
    acwr_engine: object
    readiness_engine: object
    glycogen_model: object
    drift_engine: object
    lactate_logic: object
    trimp_engine: object
    fatigue_engine: object
    adaptive_memory: object
    biomechanics: BiomechanicsEngineProtocol
    efficiency_engine: object
    durability_engine: object
    critical_speed: object
    rcp_engine: object
    weekly_planner: object
    optimal_time_calc: object
    nutrition_optimizer: object
    daily_coach: object
    db: object
    athlete_profile: AthleteProfile
    last_garmin_data: Mapping[str, object]
    last_weekly_plan: Mapping[str, object] | None
    today_session_type: str

    def to_payload(self) -> TitanContext:
        return {
            "garmin": self.garmin,
            "weather": self.weather,
            "telegram": self.telegram,
            "hrv_engine": self.hrv_engine,
            "tsb_engine": self.tsb_engine,
            "acwr_engine": self.acwr_engine,
            "readiness_engine": self.readiness_engine,
            "glycogen_model": self.glycogen_model,
            "drift_engine": self.drift_engine,
            "lactate_logic": self.lactate_logic,
            "trimp_engine": self.trimp_engine,
            "fatigue_engine": self.fatigue_engine,
            "adaptive_memory": self.adaptive_memory,
            "biomechanics": self.biomechanics,
            "efficiency_engine": self.efficiency_engine,
            "durability_engine": self.durability_engine,
            "critical_speed": self.critical_speed,
            "rcp_engine": self.rcp_engine,
            "weekly_planner": self.weekly_planner,
            "optimal_time_calc": self.optimal_time_calc,
            "nutrition_optimizer": self.nutrition_optimizer,
            "daily_coach": self.daily_coach,
            "db": self.db,
            "athlete_profile": self.athlete_profile,
            "last_garmin_data": self.last_garmin_data,
            "last_weekly_plan": self.last_weekly_plan,
            "today_session_type": self.today_session_type,
        }

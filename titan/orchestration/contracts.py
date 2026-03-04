"""Typed payload contracts for critical orchestration boundaries."""

from dataclasses import dataclass
from typing import Any, NotRequired, TypedDict


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
    activities: list[dict[str, Any]]
    weight: list[dict[str, Any]]
    sleep: list[dict[str, Any]]
    hrv: list[dict[str, Any]]
    hrv_sync_metrics: HRVSyncMetrics


@dataclass(frozen=True)
class GarminSyncResultContract:
    activities: list[dict[str, Any]]
    weight: list[dict[str, Any]]
    sleep: list[dict[str, Any]]
    hrv: list[dict[str, Any]]
    hrv_sync_metrics: HRVSyncMetrics

    def to_payload(self) -> GarminSyncResult:
        return {
            "activities": self.activities,
            "weight": self.weight,
            "sleep": self.sleep,
            "hrv": self.hrv,
            "hrv_sync_metrics": self.hrv_sync_metrics,
        }


class TodaySessionPlan(TypedDict):
    session_type: str
    duration_min: int
    volume_pct: NotRequired[float]
    distance_km: NotRequired[float]
    details: NotRequired[str]
    phase: NotRequired[str]
    governance_locks_applied: NotRequired[list[str]]
    governance_clean: NotRequired[bool]
    intensity_gate_result: NotRequired[dict[str, Any]]
    fueling_gate: NotRequired[dict[str, Any]]
    vo2_eligibility: NotRequired[dict[str, Any]]


class DailyCoachContext(TypedDict):
    db: Any
    cs_tracker: Any
    afi_constraints: dict[str, Any]
    intensity_gate_result: dict[str, Any]
    readiness_score: float
    glycogen_debt: float
    fatigue_level: str
    acwr: float
    days_since_last_vo2: Any
    fueling_confirmed: bool
    planned_duration_min: int
    today_hrv: float
    baseline_hrv: float
    hrv_std_dev: float
    today_rhr: int
    baseline_rhr: float
    sleep_score: int
    subjective_fatigue_score: int
    tsb_value: float
    injury_flag: bool
    priority_vector: dict[str, Any]
    lock_thresholds: dict[str, Any]


@dataclass(frozen=True)
class DailyCoachContextContract:
    db: Any
    cs_tracker: Any
    afi_constraints: dict[str, Any]
    intensity_gate_result: dict[str, Any]
    readiness_score: float
    glycogen_debt: float
    fatigue_level: str
    acwr: float
    days_since_last_vo2: Any
    fueling_confirmed: bool
    planned_duration_min: int
    today_hrv: float
    baseline_hrv: float
    hrv_std_dev: float
    today_rhr: int
    baseline_rhr: float
    sleep_score: int
    subjective_fatigue_score: int
    tsb_value: float
    injury_flag: bool
    priority_vector: dict[str, Any]
    lock_thresholds: dict[str, Any]

    def to_payload(self) -> DailyCoachContext:
        return {
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


class DailyCoachingPayload(TypedDict):
    session_type: str
    duration: str
    details: str
    governance_locks: list[str]
    optimal_time: Any
    dew_point: Any
    conditions: str
    hrv_status: str
    hrv_value: float
    hrv_baseline: float
    afi: float
    sleep_quality: int
    sleep_hours: float
    readiness_score: Any
    subjective_fatigue_score: int
    fatigue_level: str
    fatigue_tags: list[str]
    tsb: float
    tsb_status: str
    cs_smoothed: Any
    cs_thermal: Any
    archetype: str
    glycogen_debt: float
    glycogen_status: str
    glycogen_protocol: dict[str, Any]
    electrolyte_alert: dict[str, Any]
    nutrition_plan: str
    governance_report: dict[str, Any]
    intensity_gate_result: Any
    fueling_gate: Any
    vo2_eligibility: Any


class AthleteProfile(TypedDict):
    name: str
    age: int
    weight_kg: float
    height_cm: float
    max_hr: int
    threshold_hr: int
    phase: str
    goal: str


class TitanContext(TypedDict):
    garmin: Any
    weather: Any
    telegram: Any
    hrv_engine: Any
    tsb_engine: Any
    acwr_engine: Any
    readiness_engine: Any
    glycogen_model: Any
    drift_engine: Any
    lactate_logic: Any
    trimp_engine: Any
    fatigue_engine: Any
    adaptive_memory: Any
    biomechanics: Any
    efficiency_engine: Any
    durability_engine: Any
    critical_speed: Any
    rcp_engine: Any
    weekly_planner: Any
    optimal_time_calc: Any
    nutrition_optimizer: Any
    daily_coach: Any
    db: Any
    athlete_profile: AthleteProfile
    last_garmin_data: dict[str, Any]
    last_weekly_plan: dict[str, Any] | None
    today_session_type: str


@dataclass(frozen=True)
class TitanContextContract:
    garmin: Any
    weather: Any
    telegram: Any
    hrv_engine: Any
    tsb_engine: Any
    acwr_engine: Any
    readiness_engine: Any
    glycogen_model: Any
    drift_engine: Any
    lactate_logic: Any
    trimp_engine: Any
    fatigue_engine: Any
    adaptive_memory: Any
    biomechanics: Any
    efficiency_engine: Any
    durability_engine: Any
    critical_speed: Any
    rcp_engine: Any
    weekly_planner: Any
    optimal_time_calc: Any
    nutrition_optimizer: Any
    daily_coach: Any
    db: Any
    athlete_profile: AthleteProfile
    last_garmin_data: dict[str, Any]
    last_weekly_plan: dict[str, Any] | None
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

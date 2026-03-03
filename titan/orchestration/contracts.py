"""Typed payload contracts for critical orchestration boundaries."""

from typing import Any, Dict, List, NotRequired, TypedDict


class HRVSyncMetrics(TypedDict):
    days_back: int
    synced_days: int
    skipped_days: int


class GarminSyncResult(TypedDict):
    activities: List[Dict[str, Any]]
    weight: List[Dict[str, Any]]
    sleep: List[Dict[str, Any]]
    hrv: List[Dict[str, Any]]
    hrv_sync_metrics: HRVSyncMetrics


class TodaySessionPlan(TypedDict):
    session_type: str
    duration_min: int
    volume_pct: NotRequired[float]
    distance_km: NotRequired[float]
    details: NotRequired[str]
    phase: NotRequired[str]
    governance_locks_applied: NotRequired[List[str]]
    governance_clean: NotRequired[bool]
    intensity_gate_result: NotRequired[Dict[str, Any]]
    fueling_gate: NotRequired[Dict[str, Any]]
    vo2_eligibility: NotRequired[Dict[str, Any]]


class DailyCoachContext(TypedDict):
    db: Any
    cs_tracker: Any
    afi_constraints: Dict[str, Any]
    intensity_gate_result: Dict[str, Any]
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
    priority_vector: Dict[str, Any]
    lock_thresholds: Dict[str, Any]


class DailyCoachingPayload(TypedDict):
    session_type: str
    duration: str
    details: str
    governance_locks: List[str]
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
    fatigue_tags: List[str]
    tsb: float
    tsb_status: str
    cs_smoothed: Any
    cs_thermal: Any
    archetype: str
    glycogen_debt: float
    glycogen_status: str
    glycogen_protocol: Dict[str, Any]
    electrolyte_alert: Dict[str, Any]
    nutrition_plan: str
    governance_report: Dict[str, Any]
    intensity_gate_result: Any
    fueling_gate: Any
    vo2_eligibility: Any

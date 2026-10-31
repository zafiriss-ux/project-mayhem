from __future__ import annotations

from datetime import date, timedelta

import pytest
from freezegun import freeze_time

from titan.core.database import DatabaseManager
from titan.orchestration.contracts import GarminSyncResultContract
from titan.orchestration.daily_coach import DailyCoach
from titan.orchestration.engine_registry import EngineRegistry
from titan.science.biomechanics import BiomechanicsEngine
from titan.science.data_trust import evaluate_garmin_trust
from titan.science.durability_engine import DurabilityEngine
from titan.science.lactate_logic import LactateLogic

# AT-02: a fixed day, so a run near midnight cannot see two dates.
E2E_TODAY = "2026-03-04"


class StubGarminSync:
    """Returns what GarminSync.sync_all() returns on a good morning (AT-02).

    Same top-level keys as GarminSyncResultContract and the same record keys as
    sync_sleep() / sync_activities() / sync_hrv() / sync_weight(). Sleep is one
    dated entry per night, newest first, as sync_sleep() returns it.
    """

    def __init__(self, today: str) -> None:
        self.today = today

    def sync_all(self):
        yesterday = (date.fromisoformat(self.today) - timedelta(days=1)).isoformat()
        return GarminSyncResultContract(
            activities=[
                {
                    "date": self.today,
                    "activity_type": "running",
                    "distance_km": 6.0,
                    "duration_sec": 2100,
                    "avg_hr": 142,
                    "max_hr": 165,
                    "avg_pace_sec_per_km": 350,
                    "calories": 420,
                    "elevation_gain_m": 30,
                    "activity_id": "act-001",
                    "training_effect_label": "RECOVERY",
                    "estimated_training_load": 45.0,
                    "load_estimated": False,
                }
            ],
            weight=[{"date": self.today, "weight_kg": 70.5}],
            sleep=[
                {
                    "date": self.today,
                    "total_sleep_hours": 7.5,
                    "deep_sleep_hours": 1.4,
                    "rem_sleep_hours": 1.6,
                    "sleep_score": 82,
                    "resting_hr": 50,
                },
                {
                    "date": yesterday,
                    "total_sleep_hours": 6.1,
                    "deep_sleep_hours": 0.9,
                    "rem_sleep_hours": 1.1,
                    "sleep_score": 61,
                    "resting_hr": 57,
                },
            ],
            hrv=[{"date": self.today, "rmssd": 49.0, "status": "BALANCED", "source": "garmin"}],
            hrv_sync_metrics={"days_back": 14, "synced_days": 1, "skipped_days": 0},
            data_trust=evaluate_garmin_trust(data_age_hours=0.0).to_payload(),
            data_age_hours=0.0,
        ).to_payload()


class StubTelegram:
    def __init__(self) -> None:
        self.daily_messages: list[dict] = []
        self.alerts: list[dict] = []

    def send_daily_coaching(self, payload):
        self.daily_messages.append(payload)
        return True

    def send_alert(self, **kwargs):
        self.alerts.append(kwargs)
        return True


class StubSimpleEngine:
    def __init__(self) -> None:
        self.hrv_log: list = []

    def add_hrv_measurement(self, *_args, **_kwargs):
        return None

    def calculate_ln_rmssd_deviation(self, **_kwargs):
        return 0.0

    def get_hrv_summary(self, before_date=None):
        return {"latest_hrv": 49.0, "baseline": 45.0, "trend": "steady", "std_dev": 1.2}

    def check_baseline_drift(self, window_days: int = 14) -> bool:
        return False


class StubAutonomic:
    def __init__(self) -> None:
        self.hrr_log: list[tuple] = []

    def add_hrr(self, *_args, **_kwargs):
        return None

    def calculate_afi(self, **_kwargs):
        return 0.15

    def apply_48h_buffer(self, value):
        return value

    def get_readiness_constraints(self, *_args, **_kwargs):
        return {"afi_modifier": 0, "readiness_clamp": 100}


class StubTSB:
    def calculate_tsb(self):
        return (3.0, "FRESH")


class StubReadiness:
    def analyze_readiness(self, **_kwargs):
        return {"score": 72}


class StubWeeklyPlanner:
    def get_today_session(self):
        return {
            "session_type": "EASY",
            "volume_pct": 1.0,
            "duration_min": 35,
            "distance_km": 6,
            "details": "Keep it conversational.",
        }


class StubWeather:
    pass


class StubOptimalTime:
    def calculate_optimal_time(self, **_kwargs):
        return {"recommended_time": "07:10", "dew_point": 11, "quality": "GOOD"}


class StubNutrition:
    def analyze_weight_trend(self):
        return {"current_weight": 70.5}

    def add_weight_entry(self, *_args, **_kwargs):
        return None

    def calculate_daily_nutrition(self, **_kwargs):
        return {"carbs_g": 250, "protein_g": 120}


class StubCS:
    archetype = "steady"
    cs_smoothed = 3.8
    confidence = 1.0

    def apply_thermal(self, *_args, **_kwargs):
        return 3.8


class StubGlycogen:
    daily_debt = 0.0
    status = "NORMAL"

    def update(self, **_kwargs):
        return None

    def overnight_resynthesis(self, **_kwargs):
        return None

    @staticmethod
    def norwegian_protocol(*_args, **_kwargs):
        return {"target_carbs_g": 60}

    @staticmethod
    def electrolyte_guard(*_args, **_kwargs):
        return "none"


class StubGovernance:
    def apply_constraints(self, session_plan, context):
        return {**session_plan, "governance_locks_applied": [], "governance_clean": True}

    def get_governance_report(self, **_kwargs):
        return {}


class StubFatigue:
    def classify_fatigue(self, **_kwargs):
        return ("LOW", [])


class StubVLG:
    class _State:
        color = "GREEN"

    def resolve(self, **_kwargs):
        return self._State()


class StubAPL:
    def resolve(self, **_kwargs):
        return {"priority_vector": {}, "lock_thresholds": {}}


class StubOutcomeTracker:
    def __init__(self):
        self.decisions: list[dict] = []

    def record_decision(self, **kwargs):
        self.decisions.append(kwargs)


def stub_engine_registry() -> EngineRegistry:
    """Build an EngineRegistry of e2e stubs, mirroring the removed DailyCoach fallback."""
    return EngineRegistry(
        tsb=StubTSB(),
        hrv=StubSimpleEngine(),
        readiness=StubReadiness(),
        autonomic=StubAutonomic(),
        biomechanics=BiomechanicsEngine(),
        durability=DurabilityEngine(),
        fatigue=StubFatigue(),
        lactate=LactateLogic(),
        cs_tracker=StubCS(),
        apl=StubAPL(),
    )


@pytest.fixture
def morning_routine_setup(tmp_path):
    today = E2E_TODAY
    # The context manager stops the freeze even if the setup below raises.
    with freeze_time(f"{today} 07:30:00"):
        db = DatabaseManager(db_name="e2e_gold_path.db", db_dir=tmp_path)
        try:
            telegram = StubTelegram()
            coach = DailyCoach(
                garmin_sync=StubGarminSync(today=today),
                weather_api=StubWeather(),
                telegram_bot=telegram,
                hrv_engine=StubSimpleEngine(),
                tsb_engine=StubTSB(),
                readiness_engine=StubReadiness(),
                optimal_time_calc=StubOptimalTime(),
                nutrition_optimizer=StubNutrition(),
                weekly_planner=StubWeeklyPlanner(),
                db=db,
                engines=stub_engine_registry(),
                glycogen_accum=StubGlycogen(),
                governance=StubGovernance(),
                volume_load_gauge=StubVLG(),
                outcome_tracker=StubOutcomeTracker(),
            )
            yield {"coach": coach, "db": db, "telegram": telegram, "today": today}
        finally:
            db.close()

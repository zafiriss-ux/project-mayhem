from titan.integrations.garmin_sync import GarminSync
from titan.orchestration.daily_coach import DailyCoach


def test_garmin_sync_all_contract_shape():
    sync = GarminSync(email="x", password="y")
    sync.sync_activities = lambda days_back=7: []
    sync.sync_weight = lambda days_back=14: []
    sync.sync_sleep = lambda days_back=7: []
    sync.sync_hrv = lambda days_back=7: []

    payload = sync.sync_all(days_back=1)

    assert set(payload.keys()) == {"activities", "weight", "sleep", "hrv", "hrv_sync_metrics", "data_trust"}
    assert set(payload["hrv_sync_metrics"].keys()) == {"days_back", "synced_days", "skipped_days"}


def test_daily_coach_context_contract_shape():
    coach = DailyCoach.__new__(DailyCoach)
    coach.db = object()
    coach.cs_tracker = object()

    context = coach._build_daily_coach_context(
        afi_constraints={"afi_modifier": -5},
        intensity_gate={"color": "YELLOW"},
        readiness_score=67.0,
        glycogen_debt=23.5,
        fatigue_level="MODERATE",
        acwr=1.12,
        days_since_last_vo2=3,
        fueling_confirmed=True,
        planned_duration_min=70,
        today_hrv=42.1,
        baseline_hrv=48.7,
        hrv_std_dev=4.2,
        today_rhr=52,
        baseline_rhr=50.0,
        sleep_score=76,
        subjective_fatigue_score=4,
        tsb_value=-8.0,
        injury_flag=False,
        priority_vector={"recovery": 1},
        lock_thresholds={"acwr": 1.25},
    )

    assert set(context.keys()) == {
        "db",
        "cs_tracker",
        "afi_constraints",
        "intensity_gate_result",
        "readiness_score",
        "glycogen_debt",
        "fatigue_level",
        "acwr",
        "days_since_last_vo2",
        "fueling_confirmed",
        "planned_duration_min",
        "today_hrv",
        "baseline_hrv",
        "hrv_std_dev",
        "today_rhr",
        "baseline_rhr",
        "sleep_score",
        "subjective_fatigue_score",
        "tsb_value",
        "injury_flag",
        "priority_vector",
        "lock_thresholds",
        "esi_level",
        "esi_pace_adjustment_sec_per_km",
    }

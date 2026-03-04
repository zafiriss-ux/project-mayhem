import json

from titan.orchestration.contracts import (
    DailyCoachContextContract,
    GarminSyncResultContract,
    HRVSyncMetricsContract,
)


def test_garmin_sync_result_contract_to_payload_happy_path():
    payload = GarminSyncResultContract(
        activities=[{"date": "2026-03-04"}],
        weight=[{"weight_kg": 70.2}],
        sleep=[{"sleep_score": 85}],
        hrv=[{"rmssd": 43.2}],
        hrv_sync_metrics={"days_back": 7, "synced_days": 1, "skipped_days": 0},
    ).to_payload()

    assert payload["activities"][0]["date"] == "2026-03-04"
    assert json.loads(json.dumps(payload))["hrv_sync_metrics"]["synced_days"] == 1


def test_garmin_sync_result_contract_to_payload_boundary_empty_collections():
    payload = GarminSyncResultContract(
        activities=[],
        weight=[],
        sleep=[],
        hrv=[],
        hrv_sync_metrics={"days_back": 0, "synced_days": 0, "skipped_days": 0},
    ).to_payload()

    assert payload["activities"] == []
    assert payload["hrv_sync_metrics"]["days_back"] == 0


def test_daily_coach_context_contract_to_payload_happy_path():
    payload = DailyCoachContextContract(
        db=object(),
        cs_tracker=object(),
        afi_constraints={"afi_modifier": -5},
        intensity_gate_result={"color": "YELLOW"},
        readiness_score=66.0,
        glycogen_debt=20.0,
        fatigue_level="MODERATE",
        acwr=1.1,
        days_since_last_vo2=3,
        fueling_confirmed=True,
        planned_duration_min=60,
        today_hrv=42.0,
        baseline_hrv=40.0,
        hrv_std_dev=3.2,
        today_rhr=50,
        baseline_rhr=49.5,
        sleep_score=78,
        subjective_fatigue_score=4,
        tsb_value=-6.0,
        injury_flag=False,
        priority_vector={"recovery": 1},
        lock_thresholds={"acwr": 1.25},
    ).to_payload()

    assert payload["intensity_gate_result"]["color"] == "YELLOW"
    assert payload["priority_vector"]["recovery"] == 1


def test_daily_coach_context_contract_to_payload_boundary_nullable_vo2_field():
    payload = DailyCoachContextContract(
        db=object(),
        cs_tracker=object(),
        afi_constraints={},
        intensity_gate_result={},
        readiness_score=50.0,
        glycogen_debt=0.0,
        fatigue_level="LOW",
        acwr=1.0,
        days_since_last_vo2=None,
        fueling_confirmed=False,
        planned_duration_min=45,
        today_hrv=0.0,
        baseline_hrv=0.0,
        hrv_std_dev=0.0,
        today_rhr=0,
        baseline_rhr=0.0,
        sleep_score=0,
        subjective_fatigue_score=0,
        tsb_value=0.0,
        injury_flag=False,
        priority_vector={},
        lock_thresholds={},
    ).to_payload()

    assert payload["days_since_last_vo2"] is None


def test_hrv_sync_metrics_contract_to_payload_happy_path():
    payload = HRVSyncMetricsContract(days_back=7, synced_days=6, skipped_days=1).to_payload()

    assert payload == {"days_back": 7, "synced_days": 6, "skipped_days": 1}


def test_hrv_sync_metrics_contract_to_payload_boundary_zero_values():
    payload = HRVSyncMetricsContract(days_back=0, synced_days=0, skipped_days=0).to_payload()

    assert json.loads(json.dumps(payload)) == {"days_back": 0, "synced_days": 0, "skipped_days": 0}

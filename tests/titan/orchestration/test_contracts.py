import json
from dataclasses import FrozenInstanceError
from typing import get_type_hints

from titan.orchestration.contracts import (
    BiomechanicsEngineProtocol,
    DailyCoachContextContract,
    DailyCoachingPayload,
    DecisionResult,
    GarminSyncResultContract,
    HRVSyncMetricsContract,
    PlannedEffect,
    TitanContext,
    TitanContextContract,
    TodaySessionPlan,
)
from titan.science.biomechanics import BiomechanicsAnalysis


def test_daily_coaching_payload_contract_happy_path_typed_fields():
    payload: DailyCoachingPayload = {
        "session_type": "EASY",
        "duration": "10 km",
        "details": "steady",
        "governance_locks": [],
        "optimal_time": "07:00",
        "dew_point": 12.5,
        "conditions": "GOOD",
        "hrv_status": "STABLE",
        "hrv_value": 42.1,
        "hrv_baseline": 40.0,
        "afi": 85.0,
        "sleep_quality": 80,
        "sleep_hours": 7.5,
        "readiness_score": 72.0,
        "subjective_fatigue_score": 3,
        "fatigue_level": "LOW",
        "fatigue_tags": ["fresh"],
        "tsb": -5.0,
        "tsb_status": "MANAGE",
        "cs_smoothed": 4.2,
        "cs_thermal": 4.0,
        "archetype": "balanced",
        "glycogen_debt": 20.0,
        "glycogen_status": "MODERATE",
        "glycogen_protocol": {"carbs_g": 60},
        "electrolyte_alert": {"status": "ok"},
        "nutrition_plan": "60g carbs, 25g protein",
        "governance_report": {"summary": "clear"},
        "intensity_gate_result": {"color": "GREEN"},
        "fueling_gate": {"ok": True},
        "vo2_eligibility": {"eligible": True},
    }

    assert payload["optimal_time"] == "07:00"
    assert payload["readiness_score"] == 72.0
    assert payload["intensity_gate_result"] == {"color": "GREEN"}


def test_daily_coaching_payload_contract_boundary_nullable_and_na_fields():
    payload: DailyCoachingPayload = {
        "session_type": "REST",
        "duration": "0 km",
        "details": "",
        "governance_locks": ["H2"],
        "optimal_time": "N/A",
        "dew_point": "N/A",
        "conditions": "N/A",
        "hrv_status": "N/A",
        "hrv_value": 0.0,
        "hrv_baseline": 0.0,
        "afi": 0.0,
        "sleep_quality": 0,
        "sleep_hours": 0.0,
        "readiness_score": "N/A",
        "subjective_fatigue_score": 0,
        "fatigue_level": "LOW",
        "fatigue_tags": [],
        "tsb": 0.0,
        "tsb_status": "N/A",
        "cs_smoothed": None,
        "cs_thermal": None,
        "archetype": "N/A",
        "glycogen_debt": 0.0,
        "glycogen_status": "LOW",
        "glycogen_protocol": {},
        "electrolyte_alert": {},
        "nutrition_plan": "N/A",
        "governance_report": {},
        "intensity_gate_result": None,
        "fueling_gate": None,
        "vo2_eligibility": None,
    }

    assert payload["dew_point"] == "N/A"
    assert payload["cs_smoothed"] is None
    assert payload["vo2_eligibility"] is None


def test_today_session_plan_contract_annotation_happy_path_mapping_fields():
    hints = get_type_hints(TodaySessionPlan, include_extras=True)

    assert "typing.NotRequired[collections.abc.Mapping[str, object]]" in str(hints["intensity_gate_result"])
    assert "typing.NotRequired[collections.abc.Mapping[str, object]]" in str(hints["fueling_gate"])


def test_today_session_plan_contract_annotation_boundary_allows_missing_optional_fields():
    payload: TodaySessionPlan = {"session_type": "EASY", "duration_min": 45}

    assert payload["session_type"] == "EASY"
    assert payload["duration_min"] == 45


def test_garmin_sync_result_contract_to_payload_happy_path():
    activities = [{"date": "2026-03-04"}]
    weight = [{"weight_kg": 70.2}]
    sleep = [{"sleep_score": 85}]
    hrv = [{"rmssd": 43.2}]

    payload = GarminSyncResultContract(
        activities=activities,
        weight=weight,
        sleep=sleep,
        hrv=hrv,
        hrv_sync_metrics={"days_back": 7, "synced_days": 1, "skipped_days": 0},
    ).to_payload()

    assert payload["activities"] is activities
    assert payload["weight"] is weight
    assert payload["sleep"] is sleep
    assert payload["hrv"] is hrv
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
    db_handle = object()
    cs_tracker = object()
    payload = DailyCoachContextContract(
        db=db_handle,
        cs_tracker=cs_tracker,
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

    assert payload["db"] is db_handle
    assert payload["cs_tracker"] is cs_tracker
    assert payload["intensity_gate_result"]["color"] == "YELLOW"
    assert payload["days_since_last_vo2"] == 3
    assert payload["priority_vector"]["recovery"] == 1
    assert payload["lock_thresholds"]["acwr"] == 1.25


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


def test_titan_context_contract_to_payload_happy_path():
    garmin_client = object()
    db_handle = object()
    last_garmin_data = {"activities": []}
    last_weekly_plan = {"monday": "easy"}

    payload = TitanContextContract(
        garmin=garmin_client,
        weather=object(),
        telegram=object(),
        hrv_engine=object(),
        tsb_engine=object(),
        acwr_engine=object(),
        readiness_engine=object(),
        glycogen_model=object(),
        drift_engine=object(),
        lactate_logic=object(),
        trimp_engine=object(),
        fatigue_engine=object(),
        adaptive_memory=object(),
        biomechanics=object(),
        efficiency_engine=object(),
        durability_engine=object(),
        critical_speed=object(),
        rcp_engine=object(),
        weekly_planner=object(),
        optimal_time_calc=object(),
        nutrition_optimizer=object(),
        daily_coach=object(),
        db=db_handle,
        athlete_profile={
            "name": "Athlete",
            "age": 35,
            "weight_kg": 75.0,
            "height_cm": 175.0,
            "max_hr": 190,
            "threshold_hr": 168,
            "phase": "BUILD",
            "goal": "5K",
        },
        last_garmin_data=last_garmin_data,
        last_weekly_plan=last_weekly_plan,
        today_session_type="EASY",
    ).to_payload()

    assert payload["garmin"] is garmin_client
    assert payload["db"] is db_handle
    assert payload["last_garmin_data"] is last_garmin_data
    assert payload["last_weekly_plan"] is last_weekly_plan
    assert payload["athlete_profile"]["name"] == "Athlete"
    assert payload["today_session_type"] == "EASY"


# ── B1 tests: PlannedEffect + DecisionResult type invariants ─────────────────


def _minimal_session_plan() -> TodaySessionPlan:
    return {"session_type": "EASY", "duration_min": 45}


def _minimal_coaching_payload() -> DailyCoachingPayload:
    return {
        "session_type": "EASY",
        "duration": "10 km",
        "details": "",
        "governance_locks": [],
        "optimal_time": "07:00",
        "dew_point": 12.0,
        "conditions": "GOOD",
        "hrv_status": "STABLE",
        "hrv_value": 42.0,
        "hrv_baseline": 40.0,
        "afi": 0.0,
        "sleep_quality": 75,
        "sleep_hours": 7.5,
        "readiness_score": 70.0,
        "subjective_fatigue_score": 3,
        "fatigue_level": "LOW",
        "fatigue_tags": [],
        "tsb": 0.0,
        "tsb_status": "OPTIMAL",
        "cs_smoothed": None,
        "cs_thermal": None,
        "archetype": "balanced",
        "glycogen_debt": 10.0,
        "glycogen_status": "LOW",
        "glycogen_protocol": {},
        "electrolyte_alert": {},
        "nutrition_plan": "60g carbs, 25g protein",
        "governance_report": {},
        "intensity_gate_result": None,
        "fueling_gate": None,
        "vo2_eligibility": None,
    }


def _minimal_decision_result(**overrides) -> DecisionResult:
    kwargs: dict = {
        "session_plan": _minimal_session_plan(),
        "coaching_payload": _minimal_coaching_payload(),
        "planned_effects": (),
        "decision_trace": {"hrv": 42.0, "tsb": 0.0},
        "snapshot_at": "2026-03-07T07:00:00",
    }
    kwargs.update(overrides)
    return DecisionResult(**kwargs)


def test_planned_effect_is_frozen():
    effect = PlannedEffect(effect_type="send_telegram", payload={"msg": "hi"})
    try:
        effect.effect_type = "record_outcome"  # type: ignore[misc]
        raise AssertionError("Expected FrozenInstanceError")
    except FrozenInstanceError:
        pass


def test_decision_result_is_frozen():
    result = _minimal_decision_result()
    try:
        result.snapshot_at = "mutated"  # type: ignore[misc]
        raise AssertionError("Expected FrozenInstanceError")
    except FrozenInstanceError:
        pass


def test_decision_result_planned_effects_is_tuple():
    effect = PlannedEffect(effect_type="send_telegram", payload={})
    result = _minimal_decision_result(planned_effects=(effect,))
    assert isinstance(result.planned_effects, tuple)
    assert result.planned_effects[0].effect_type == "send_telegram"


def test_planned_effect_discriminants():
    for discriminant in ("record_outcome", "send_telegram"):
        effect = PlannedEffect(effect_type=discriminant, payload={})
        assert effect.effect_type == discriminant


# ─────────────────────────────────────────────────────────────────────────────


def test_titan_context_contract_to_payload_boundary_nullable_weekly_plan():
    payload = TitanContextContract(
        garmin=object(),
        weather=object(),
        telegram=object(),
        hrv_engine=object(),
        tsb_engine=object(),
        acwr_engine=object(),
        readiness_engine=object(),
        glycogen_model=object(),
        drift_engine=object(),
        lactate_logic=object(),
        trimp_engine=object(),
        fatigue_engine=object(),
        adaptive_memory=object(),
        biomechanics=object(),
        efficiency_engine=object(),
        durability_engine=object(),
        critical_speed=object(),
        rcp_engine=object(),
        weekly_planner=object(),
        optimal_time_calc=object(),
        nutrition_optimizer=object(),
        daily_coach=object(),
        db=object(),
        athlete_profile={
            "name": "Athlete",
            "age": 35,
            "weight_kg": 75.0,
            "height_cm": 175.0,
            "max_hr": 190,
            "threshold_hr": 168,
            "phase": "BUILD",
            "goal": "5K",
        },
        last_garmin_data={},
        last_weekly_plan=None,
        today_session_type="REST",
    ).to_payload()

    assert payload["last_weekly_plan"] is None


def test_titan_context_contract_annotation_uses_biomechanics_engine_protocol():
    typed_dict_hints = get_type_hints(TitanContext, include_extras=True)
    dataclass_hints = get_type_hints(TitanContextContract, include_extras=True)

    assert typed_dict_hints["biomechanics"] is BiomechanicsEngineProtocol
    assert dataclass_hints["biomechanics"] is BiomechanicsEngineProtocol


def test_biomechanics_engine_protocol_structural_subtype_expectation():
    assert isinstance(BiomechanicsAnalysis(), BiomechanicsEngineProtocol)


def test_biomechanics_engine_protocol_boundary_has_no_speculative_members():
    assert sorted(BiomechanicsEngineProtocol.__dict__.get("__annotations__", {})) == []

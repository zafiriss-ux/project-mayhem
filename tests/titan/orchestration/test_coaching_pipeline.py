from types import SimpleNamespace

import pytest

from titan.orchestration.coaching_pipeline import AthleteCoachingContext, coaching_pipeline


def _build_context(*, coach, athlete_id: str = "athlete-1") -> AthleteCoachingContext:
    return AthleteCoachingContext(
        athlete_id=athlete_id,
        coach=coach,
        garmin_data={"status": "ok"},
        soreness=5,
        subjective_fatigue_score=5,
        today_rhr=50,
        today_sleep_score=80,
        today_sleep_hours=7.0,
        baseline_rhr_for_comparison=50.0,
        persistence_degraded=False,
        garmin_data_stale=False,
        latest_hrv=45.0,
        baseline_hrv=42.0,
        hrv_summary={"std_dev": 1.0},
        afi_final=0.0,
        afi_constraints={"afi_modifier": 0, "readiness_clamp": 100},
        tsb_value=0.0,
        tsb_status="BALANCED",
        cs_thermal=None,
        garmin_trust=SimpleNamespace(trust_level=SimpleNamespace(value="HIGH")),
        garmin_report_payload={"source": "garmin"},
        startup_hydration_confidence={"hrv": True, "weight": True, "load": True, "hrr": True, "cs": True},
        startup_confidence_applies=False,
    )


@pytest.mark.unit
def test_coaching_pipeline_happy_path_returns_effect_runner_result():
    calls = []

    def _decision_pipeline(**kwargs):
        calls.append(kwargs)
        return {"readiness_score": 82, "athlete": "athlete-1"}

    coach = SimpleNamespace(
        _decision_pipeline=_decision_pipeline,
        _effect_runner=lambda payload: payload["readiness_score"] == 82,
    )

    result = coaching_pipeline(_build_context(coach=coach, athlete_id="athlete-1"))

    assert result is True
    assert len(calls) == 1
    assert calls[0]["soreness"] == 5


@pytest.mark.unit
def test_coaching_pipeline_state_isolation_oracle_sequential_calls_are_independent():
    decision_calls = []

    def _decision_pipeline(**kwargs):
        decision_calls.append(kwargs)
        readiness_score = 90 if kwargs["soreness"] <= 2 else 15
        return {
            "athlete_id": kwargs["garmin_data"]["athlete_id"],
            "readiness_score": readiness_score,
        }

    coach = SimpleNamespace(
        _decision_pipeline=_decision_pipeline,
        _effect_runner=lambda payload: payload,
    )

    ready_context = _build_context(coach=coach, athlete_id="athlete-ready")
    low_context = _build_context(coach=coach, athlete_id="athlete-low")
    ready_context = AthleteCoachingContext(
        **{**ready_context.__dict__, "garmin_data": {"athlete_id": "athlete-ready"}, "soreness": 1}
    )
    low_context = AthleteCoachingContext(
        **{**low_context.__dict__, "garmin_data": {"athlete_id": "athlete-low"}, "soreness": 9}
    )

    ready_result = coaching_pipeline(ready_context)
    low_result = coaching_pipeline(low_context)

    assert ready_result["athlete_id"] == "athlete-ready"
    assert ready_result["readiness_score"] == 90
    assert low_result["athlete_id"] == "athlete-low"
    assert low_result["readiness_score"] == 15
    assert decision_calls[0]["garmin_data"]["athlete_id"] == "athlete-ready"
    assert decision_calls[1]["garmin_data"]["athlete_id"] == "athlete-low"


@pytest.mark.unit
def test_coaching_pipeline_decision_pipeline_exception_fails_closed():
    """INV-12: a _decision_pipeline exception must not propagate — it is caught,
    alerted via telegram, and the run returns False (no prescription)."""
    alerts = []
    effect_runner_calls = []
    coach = SimpleNamespace(
        _decision_pipeline=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        _effect_runner=lambda payload: effect_runner_calls.append(payload),
        telegram=SimpleNamespace(send_alert=lambda *a, **k: alerts.append((a, k))),
    )

    result = coaching_pipeline(_build_context(coach=coach))

    assert result is False
    assert len(alerts) == 1
    assert not effect_runner_calls


@pytest.mark.unit
def test_decision_pipeline_failure_alert_matches_real_send_alert_signature():
    """INV-12 fail-safe alert must call send_alert the way TitanTelegramBot defines it.

    A one-argument call raised TypeError inside the try block, so the athlete never
    received the "do not do quality work today" alert.
    """
    from unittest.mock import create_autospec

    from titan.integrations.telegram_bot import TitanTelegramBot

    telegram = create_autospec(TitanTelegramBot, instance=True)
    coach = SimpleNamespace(
        _decision_pipeline=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
        _effect_runner=lambda payload: None,
        telegram=telegram,
    )

    assert coaching_pipeline(_build_context(coach=coach)) is False
    telegram.send_alert.assert_called_once()
    kwargs = telegram.send_alert.call_args.kwargs
    assert kwargs["level"] == "critical"
    assert "EASY session or rest" in kwargs["message"]

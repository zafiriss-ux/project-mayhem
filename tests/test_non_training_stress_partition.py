from titan.science.governance_engine import GovernanceEngine


def _base_context(**overrides):
    context = {
        "today_hrv": 50.0,
        "baseline_hrv": 70.0,
        "today_rhr": 62.0,
        "baseline_rhr": 50.0,
        "acwr": 1.0,
        "tsb_value": 0.0,
        "readiness_score": 80.0,
        "sleep_score": 80,
        "subjective_fatigue_score": 3,
        "glycogen_debt": 2.0,
        "fatigue_level": "LOW",
        "days_since_last_vo2": 3,
        "fueling_confirmed": True,
    }
    context.update(overrides)
    return context


def test_non_training_illness_pattern_forces_rest_with_traceable_context():
    gov = GovernanceEngine()
    plan = {"session_type": "INTERVALS", "max_zone": 5, "duration_min": 45}

    result = gov.apply_constraints(plan, _base_context(acwr=1.1))

    assert result["session_type"] == "REST"
    assert result["max_zone"] == 1
    assert result["hrv_stress_context"] == "ILLNESS_PATTERN"
    assert any(r["gate"] == "H2_H3_NON_TRAINING_STRESS" for r in result["hard_stop_reasons"])


def test_non_training_unexplained_moderate_stays_conservative_without_illness_escalation():
    gov = GovernanceEngine()
    plan = {"session_type": "TEMPO", "max_zone": 4, "duration_min": 45}

    result = gov.apply_constraints(
        plan,
        _base_context(today_rhr=58.0, baseline_rhr=50.0, acwr=1.0),
    )

    assert result["session_type"] == "REST"
    assert result["hrv_stress_context"] == "UNEXPLAINED_MODERATE"
    assert not any(r["gate"] == "H2_H3_NON_TRAINING_STRESS" for r in result["hard_stop_reasons"])


def test_non_training_training_explained_context_preserves_existing_hard_stop_behavior():
    gov = GovernanceEngine()
    plan = {"session_type": "HAMMER", "max_zone": 5, "duration_min": 45}

    result = gov.apply_constraints(plan, _base_context(acwr=1.45, today_rhr=56.0, baseline_rhr=50.0))

    assert result["session_type"] == "REST"
    assert result["hrv_stress_context"] == "TRAINING_EXPLAINED"
    assert any(r["gate"] == "H2" for r in result["hard_stop_reasons"])

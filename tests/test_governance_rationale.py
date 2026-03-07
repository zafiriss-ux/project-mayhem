

def _session(session_type: str = "INTERVALS") -> dict:
    return {"session_type": session_type, "max_zone": 5, "zone": 5, "duration_min": 60}


def _base_context() -> dict:
    return {
        "today_hrv": 70.0,
        "baseline_hrv": 80.0,
        "today_rhr": 50,
        "baseline_rhr": 47,
        "tsb_value": -10.0,
        "subjective_fatigue_score": 3,
        "acwr": 1.0,
        "readiness_score": 80,
        "glycogen_debt": 2.0,
        "fatigue_level": "LOW",
        "days_since_last_vo2": 3,
        "fueling_confirmed": True,
    }


def test_governance_rationale_hard_stop_contains_primary_reason_and_gate(governance_engine_factory):
    engine = governance_engine_factory()
    context = _base_context() | {"injury_flag": True}

    result = engine.apply_constraints(_session(), context)

    rationale = result["decision_rationale"]
    assert rationale["primary_reason"]
    assert any(
        finding["gate"] == "H1" and finding["status"] == "TRIGGERED"
        for finding in rationale["gate_findings"]
    )


def test_governance_rationale_approved_contains_h1_h5_with_margin_values(governance_engine_factory):
    engine = governance_engine_factory()

    result = engine.apply_constraints(_session("EASY"), _base_context())

    findings = {item["gate"]: item for item in result["decision_rationale"]["gate_findings"]}
    for gate in ["H1", "H2", "H3", "H4", "H5"]:
        assert gate in findings
    assert findings["H2"]["margin"] is not None
    assert findings["H3"]["margin"] is not None


def test_override_metrics_calculation_uses_30_day_rate_and_trend():
    decisions = []
    for i in range(30):
        decisions.append(
            {
                "session_post_governance": "EASY",
                "outcome_session_type_actual": "INTERVALS" if i >= 20 else "EASY",
            }
        )

    from titan.ui.operator_console import OperatorConsoleService

    payload = OperatorConsoleService._compute_override_metrics(decisions, window_days=30)

    assert payload["override_rate_30d"] == 0.333
    assert payload["trend"] == "up"
    assert payload["trust_signal"] == "DRIFT_WARNING"

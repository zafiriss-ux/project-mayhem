"""Small findings of the Phase 4 audit (SG-11, SG-12; D-112). Each test fails without the fix."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from tests.titan.orchestration.test_daily_coach import MinimalCoachFactory
from titan.core.athlete import profile_problems

_RECORD = {
    "birth_date": "1988-07-02", "sex": "F", "weight_kg": 58.0, "height_cm": 165,
    "max_hr": 186, "threshold_hr": 166, "training_phase": "BASE", "training_goal": "10K",
    "location_city": "Volos", "location_country": "GR",
}


@pytest.mark.unit
@pytest.mark.parametrize("threshold_hr", [186, 200])
def test_a_threshold_hr_at_or_above_max_hr_is_not_a_usable_profile(threshold_hr: int) -> None:
    problems = profile_problems({**_RECORD, "threshold_hr": threshold_hr}, date(2026, 10, 17))
    assert problems == ["threshold_hr: must be below max_hr"]


@pytest.mark.unit
def test_a_threshold_hr_below_max_hr_is_fine() -> None:
    assert profile_problems(_RECORD, date(2026, 10, 17)) == []


@pytest.mark.unit
def test_an_out_of_range_max_hr_is_reported_once() -> None:
    problems = profile_problems({**_RECORD, "max_hr": 90, "threshold_hr": 166}, date(2026, 10, 17))
    assert problems == ["max_hr: must be between 100 and 220"]


@pytest.mark.unit
def test_no_load_history_reaches_governance_as_missing_tsb() -> None:
    coach = MinimalCoachFactory.build(telegram_success=True)
    coach.tsb = SimpleNamespace(
        calculate_tsb=lambda: (None, "INSUFFICIENT DATA"), daily_loads=[], add_daily_load=lambda *a: None,
    )
    seen: list[dict] = []
    coach.governance = SimpleNamespace(
        apply_constraints=lambda session_plan, context: seen.append(dict(context)) or {
            **session_plan, "governance_locks_applied": [], "governance_clean": True,
        },
        get_governance_report=lambda **k: {},
    )

    assert coach.run_morning_routine() is True
    assert seen and "tsb_value" in seen[0] and seen[0]["tsb_value"] is None


@pytest.mark.unit
def test_missing_tsb_gives_the_easy_ceiling_in_governance() -> None:
    """The gate side of the same path: None is H4_MISSING with an EASY ceiling (ADR-0051)."""
    from tests.test_p0_safety_gates import make_context
    from titan.science.governance_engine import GovernanceEngine

    result = GovernanceEngine().apply_constraints(
        {"session_type": "TEMPO", "distance_km": 10.0, "duration_min": 50, "max_zone": 4},
        make_context(tsb_value=None),
    )
    assert result["session_type"] in {"EASY", "REST"}


@pytest.mark.integration
@pytest.mark.parametrize("delta", [-0.9, 0.21, float("nan"), float("inf")])
def test_an_offset_past_the_ceiling_is_not_saved(tmp_path, delta: float) -> None:
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    try:
        with pytest.raises(ValueError):
            db.save_threshold_offset(
                athlete_id="owner", threshold_key="VO2_READINESS_MIN", delta_value=delta,
                source="manual", confidence=1.0, updated_at="2026-10-17T00:00:00+00:00",
            )
        assert db.get_athlete_threshold_offsets("owner") == []
    finally:
        db.close()


@pytest.mark.integration
def test_a_raw_offset_past_the_ceiling_is_clamped_when_read(tmp_path) -> None:
    from titan.core.database import DatabaseManager
    from titan.science.threshold_adapter import ThresholdAdapter

    db = DatabaseManager(db_name="titan_core.db", db_dir=tmp_path)
    try:
        db.conn.executemany(
            "INSERT INTO athlete_threshold_offsets (athlete_id, threshold_key, delta_value, updated_at, "
            "source, confidence) VALUES ('owner', ?, ?, '2026-10-17', 'manual', 1.0)",
            [("VO2_READINESS_MIN", -0.9), ("ACWR_CEILING", 0.5), ("HARD_STOP_HRV_DELTA", 3.0)],
        )
        db.conn.commit()
        adapter = ThresholdAdapter(athlete_id="owner", db=db)
        adapter.load()

        assert adapter.get_threshold("VO2_READINESS_MIN", 65.0) == pytest.approx(65.0 * 0.8)
        assert adapter.get_threshold("ACWR_CEILING", 1.5) == pytest.approx(1.5 * 1.2)
        assert adapter.get_threshold("HARD_STOP_HRV_DELTA", 15.0) == 15.0
    finally:
        db.close()

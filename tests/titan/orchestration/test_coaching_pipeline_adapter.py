"""
tests/titan/orchestration/test_coaching_pipeline_adapter.py

ADR-0052 Stage 3: ThresholdAdapter injection into coaching_pipeline().
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from titan.orchestration.coaching_pipeline import (
    AthleteCoachingContext,
    coaching_pipeline,
)
from titan.science.threshold_adapter import ThresholdAdapter

# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_coach() -> SimpleNamespace:
    return SimpleNamespace(
        _decision_pipeline=lambda **_kw: {"readiness_score": 80},
        _effect_runner=lambda _r: True,
    )


def _build_graduated_context(db: MagicMock) -> AthleteCoachingContext:
    """Build a minimal valid context for a graduated (non-cold-start) athlete."""
    return AthleteCoachingContext(
        athlete_id="owner",
        coach=_make_coach(),
        garmin_data={"status": "ok"},
        soreness=3,
        subjective_fatigue_score=3,
        today_rhr=48,
        today_sleep_score=80,
        today_sleep_hours=7.5,
        baseline_rhr_for_comparison=48.0,
        persistence_degraded=False,
        garmin_data_stale=False,
        latest_hrv=50.0,
        baseline_hrv=48.0,
        hrv_summary={"std_dev": 1.5},
        afi_final=0.0,
        afi_constraints={"afi_modifier": 0, "readiness_clamp": 100},
        tsb_value=5.0,
        tsb_status="BALANCED",
        cs_thermal=None,
        garmin_trust=SimpleNamespace(trust_level=SimpleNamespace(value="HIGH")),
        garmin_report_payload={"source": "garmin"},
        startup_hydration_confidence={
            "hrv": True, "weight": True, "load": True, "hrr": True, "cs": True
        },
        startup_confidence_applies=False,
        db=db,
        cold_start_active=False,
    )


def _build_cold_start_context(db: MagicMock) -> AthleteCoachingContext:
    """Build a valid context for a cold-start athlete."""
    return AthleteCoachingContext(
        athlete_id="new_athlete",
        coach=_make_coach(),
        garmin_data={"status": "ok"},
        soreness=5,
        subjective_fatigue_score=5,
        today_rhr=55,
        today_sleep_score=70,
        today_sleep_hours=6.0,
        baseline_rhr_for_comparison=50.0,
        persistence_degraded=False,
        garmin_data_stale=False,
        latest_hrv=40.0,
        baseline_hrv=45.0,
        hrv_summary={},
        afi_final=0.0,
        afi_constraints={"afi_modifier": 0, "readiness_clamp": 100},
        tsb_value=-5.0,
        tsb_status="FRESH",
        cs_thermal=None,
        garmin_trust=SimpleNamespace(trust_level=SimpleNamespace(value="MEDIUM")),
        garmin_report_payload={},
        startup_hydration_confidence={},
        startup_confidence_applies=False,
        db=db,
        cold_start_active=False,
    )


def _build_no_db_context() -> AthleteCoachingContext:
    """Build a valid context with db=None."""
    return AthleteCoachingContext(
        athlete_id="owner",
        coach=_make_coach(),
        garmin_data={"status": "ok"},
        soreness=3,
        subjective_fatigue_score=3,
        today_rhr=48,
        today_sleep_score=80,
        today_sleep_hours=7.5,
        baseline_rhr_for_comparison=48.0,
        persistence_degraded=False,
        garmin_data_stale=False,
        latest_hrv=50.0,
        baseline_hrv=48.0,
        hrv_summary={"std_dev": 1.5},
        afi_final=0.0,
        afi_constraints={"afi_modifier": 0, "readiness_clamp": 100},
        tsb_value=5.0,
        tsb_status="BALANCED",
        cs_thermal=None,
        garmin_trust=SimpleNamespace(trust_level=SimpleNamespace(value="HIGH")),
        garmin_report_payload={},
        startup_hydration_confidence={},
        startup_confidence_applies=False,
        db=None,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestThresholdAdapterInjection:

    def test_adapter_not_instantiated_during_cold_start(self):
        """
        During cold-start, ThresholdAdapter must NOT be instantiated.
        ADR-0033 L3-C: circuit breaker disabled during cold-start.
        ADR-0052 Stage 3: adapter bypassed entirely.
        """
        db = MagicMock()
        db.is_athlete_cold_start.return_value = True
        db.check_and_exit_cold_start.return_value = False  # cold-start remains active
        ctx = _build_cold_start_context(db)

        with patch(
            "titan.orchestration.coaching_pipeline.ThresholdAdapter"
        ) as mock_adapter_cls:
            coaching_pipeline(ctx)
            mock_adapter_cls.assert_not_called()

    def test_adapter_instantiated_for_graduated_athlete(self):
        """
        For a graduated athlete (is_cold_start=False), ThresholdAdapter
        must be instantiated and load() called.
        """
        db = MagicMock()
        db.is_athlete_cold_start.return_value = False
        db.check_and_exit_cold_start.return_value = False
        mock_adapter = MagicMock(spec=ThresholdAdapter)
        mock_adapter.load.return_value = None

        ctx = _build_graduated_context(db)

        with patch(
            "titan.orchestration.coaching_pipeline.ThresholdAdapter",
            return_value=mock_adapter,
        ):
            coaching_pipeline(ctx)
            mock_adapter.load.assert_called_once()

    def test_adapter_none_when_no_db(self):
        """
        When ctx.db is None, ThresholdAdapter must NOT be instantiated.
        GovernanceEngine receives threshold_adapter=None (no adaptation).
        """
        ctx = _build_no_db_context()

        with patch(
            "titan.orchestration.coaching_pipeline.ThresholdAdapter"
        ) as mock_adapter_cls:
            coaching_pipeline(ctx)
            mock_adapter_cls.assert_not_called()

    def test_governance_engine_receives_adapter(self):
        """
        GovernanceEngine must be constructed with the ThresholdAdapter
        instance, not None, for a graduated athlete with DB.
        """
        db = MagicMock()
        db.is_athlete_cold_start.return_value = False
        db.check_and_exit_cold_start.return_value = False
        mock_adapter = MagicMock(spec=ThresholdAdapter)
        mock_adapter.load.return_value = None

        ctx = _build_graduated_context(db)

        with patch(
            "titan.orchestration.coaching_pipeline.ThresholdAdapter",
            return_value=mock_adapter,
        ), patch(
            "titan.orchestration.coaching_pipeline.GovernanceEngine"
        ) as mock_engine_cls:
            mock_engine_cls.return_value.apply_constraints.return_value = MagicMock(
                session_type="EASY", lock_codes=[], governance_clean=True
            )
            coaching_pipeline(ctx)
            call_kwargs = mock_engine_cls.call_args
            assert call_kwargs is not None, "GovernanceEngine must be instantiated"
            kwargs = call_kwargs.kwargs if call_kwargs.kwargs else {}
            assert kwargs.get("threshold_adapter") is mock_adapter, (
                "GovernanceEngine must receive the ThresholdAdapter instance"
            )

    def test_propose_adaptation_never_called(self):
        """
        Stage 3 wires adapter for read-only threshold lookup.
        propose_adaptation() (Stage 4) must NOT be called.
        """
        db = MagicMock()
        db.is_athlete_cold_start.return_value = False
        db.check_and_exit_cold_start.return_value = False
        mock_adapter = MagicMock(spec=ThresholdAdapter)
        mock_adapter.load.return_value = None

        ctx = _build_graduated_context(db)

        with patch(
            "titan.orchestration.coaching_pipeline.ThresholdAdapter",
            return_value=mock_adapter,
        ):
            coaching_pipeline(ctx)
            mock_adapter.propose_adaptation.assert_not_called()

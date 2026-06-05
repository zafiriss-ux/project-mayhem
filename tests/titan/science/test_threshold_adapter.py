"""
Tests for ThresholdAdapter — ADR-0052 Stage 2 per-athlete threshold offset module.

Covers: load(), get_threshold(), propose_adaptation(), is_circuit_breaker_active(),
is_hard_stop_gate(), MODULE_VERSION, INV-01 compliance, round-trip persistence.
"""
import math
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from titan.config.thresholds import (
    CALIBRATION_MIN_OUTCOME_COUNT,
    HARD_STOP_THRESHOLD_KEYS,
    THRESHOLD_ADAPTER_DAMPING_PCT,
    THRESHOLD_ADAPTER_MAX_DELTA_PCT,
)
from titan.science.threshold_adapter import (
    HARD_STOP_GATE_NAMES,
    MODULE_VERSION,
    ThresholdAdapter,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_db(
    offsets: list[dict] | None = None,
    is_cold_start: bool = True,
    false_neg_rate: float = 0.0,
) -> MagicMock:
    """Return a minimal DatabaseManager mock configured for ThresholdAdapter tests."""
    db = MagicMock()
    db.get_athlete_threshold_offsets.return_value = offsets or []
    db.is_athlete_cold_start.return_value = is_cold_start
    db.get_false_negative_rate.return_value = false_neg_rate
    db.save_threshold_offset.return_value = None
    return db


def _loaded_adapter(
    athlete_id: str = "athlete_01",
    offsets: list[dict] | None = None,
    is_cold_start: bool = True,
    false_neg_rate: float = 0.0,
) -> tuple[ThresholdAdapter, MagicMock]:
    """Return a (ThresholdAdapter, mock_db) pair that has already been loaded."""
    db = _make_db(offsets=offsets, is_cold_start=is_cold_start, false_neg_rate=false_neg_rate)
    adapter = ThresholdAdapter(athlete_id=athlete_id, db=db)
    adapter.load()
    return adapter, db


# ---------------------------------------------------------------------------
# Test 1 — get_threshold: hard-stop gate returns base_value unchanged
# ---------------------------------------------------------------------------

class TestGetThresholdHardStopGates:
    @pytest.mark.unit
    def test_hard_stop_hrv_delta_bypassed(self):
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "HARD_STOP_HRV_DELTA", "delta_value": 0.15}]
        )
        # Even with an offset stored, hard-stop gate must be returned unchanged
        result = adapter.get_threshold("HARD_STOP_HRV_DELTA", 15.0)
        assert result == 15.0

    @pytest.mark.unit
    def test_hard_stop_rhr_delta_bypassed(self):
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "HARD_STOP_RHR_DELTA", "delta_value": 0.20}]
        )
        result = adapter.get_threshold("HARD_STOP_RHR_DELTA", 8.0)
        assert result == 8.0

    @pytest.mark.unit
    def test_hard_stop_tsb_floor_bypassed(self):
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "HARD_STOP_TSB_FLOOR", "delta_value": 0.10}]
        )
        result = adapter.get_threshold("HARD_STOP_TSB_FLOOR", -50.0)
        assert result == -50.0

    @pytest.mark.unit
    def test_subjective_fatigue_extreme_bypassed(self):
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "SUBJECTIVE_FATIGUE_EXTREME", "delta_value": 0.10}]
        )
        result = adapter.get_threshold("SUBJECTIVE_FATIGUE_EXTREME", 8)
        assert result == 8


# ---------------------------------------------------------------------------
# Test 2 — get_threshold: delta is applied for soft gates
# ---------------------------------------------------------------------------

class TestGetThresholdAppliesDelta:
    @pytest.mark.unit
    def test_positive_delta_increases_threshold(self):
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "VO2_READINESS_MIN", "delta_value": 0.10}]
        )
        result = adapter.get_threshold("VO2_READINESS_MIN", 65.0)
        assert math.isclose(result, 65.0 * 1.10, rel_tol=1e-9)

    @pytest.mark.unit
    def test_negative_delta_decreases_threshold(self):
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "VO2_READINESS_MIN", "delta_value": -0.10}]
        )
        result = adapter.get_threshold("VO2_READINESS_MIN", 65.0)
        assert math.isclose(result, 65.0 * 0.90, rel_tol=1e-9)

    @pytest.mark.unit
    def test_zero_delta_returns_base_unchanged(self):
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "VO2_READINESS_MIN", "delta_value": 0.0}]
        )
        result = adapter.get_threshold("VO2_READINESS_MIN", 65.0)
        assert result == 65.0

    @pytest.mark.unit
    def test_unknown_threshold_returns_base(self):
        adapter, _ = _loaded_adapter()
        result = adapter.get_threshold("SOME_UNKNOWN_THRESHOLD", 42.0)
        assert result == 42.0


# ---------------------------------------------------------------------------
# Test 3 — get_threshold: raises RuntimeError if not loaded
# ---------------------------------------------------------------------------

class TestGetThresholdRaisesIfNotLoaded:
    @pytest.mark.unit
    def test_raises_runtime_error_before_load(self):
        db = _make_db()
        adapter = ThresholdAdapter(athlete_id="athlete_01", db=db)
        with pytest.raises(RuntimeError, match="load\\(\\)"):
            adapter.get_threshold("VO2_READINESS_MIN", 65.0)

    @pytest.mark.unit
    def test_no_error_after_load(self):
        adapter, _ = _loaded_adapter()
        # Should not raise
        result = adapter.get_threshold("VO2_READINESS_MIN", 65.0)
        assert result == 65.0


# ---------------------------------------------------------------------------
# Test 4 — propose_adaptation: refused for hard-stop gates
# ---------------------------------------------------------------------------

class TestProposeAdaptationRefusedHardStop:
    @pytest.mark.unit
    def test_hard_stop_hrv_returns_false(self):
        adapter, db = _loaded_adapter(is_cold_start=False, false_neg_rate=0.0)
        result = adapter.propose_adaptation("HARD_STOP_HRV_DELTA", +1.0, 15.0)
        assert result is False
        db.save_threshold_offset.assert_not_called()

    @pytest.mark.unit
    def test_hard_stop_rhr_returns_false(self):
        adapter, db = _loaded_adapter(is_cold_start=False, false_neg_rate=0.0)
        result = adapter.propose_adaptation("HARD_STOP_RHR_DELTA", -1.0, 8.0)
        assert result is False
        db.save_threshold_offset.assert_not_called()

    @pytest.mark.unit
    def test_hard_stop_tsb_floor_returns_false(self):
        adapter, db = _loaded_adapter(is_cold_start=False, false_neg_rate=0.0)
        result = adapter.propose_adaptation("HARD_STOP_TSB_FLOOR", +1.0, -50.0)
        assert result is False
        db.save_threshold_offset.assert_not_called()


# ---------------------------------------------------------------------------
# Test 5 — propose_adaptation: applies damping step
# ---------------------------------------------------------------------------

class TestProposeAdaptationAppliesDamping:
    @pytest.mark.unit
    def test_positive_direction_adds_damping_pct(self):
        adapter, db = _loaded_adapter(is_cold_start=False, false_neg_rate=0.0)
        result = adapter.propose_adaptation("VO2_READINESS_MIN", +1.0, 65.0)
        assert result is True
        # The new delta should equal exactly one damping step
        assert math.isclose(
            adapter._offsets["VO2_READINESS_MIN"],
            THRESHOLD_ADAPTER_DAMPING_PCT,
            rel_tol=1e-9,
        )

    @pytest.mark.unit
    def test_negative_direction_subtracts_damping_pct(self):
        adapter, db = _loaded_adapter(is_cold_start=False, false_neg_rate=0.0)
        result = adapter.propose_adaptation("VO2_READINESS_MIN", -1.0, 65.0)
        assert result is True
        assert math.isclose(
            adapter._offsets["VO2_READINESS_MIN"],
            -THRESHOLD_ADAPTER_DAMPING_PCT,
            rel_tol=1e-9,
        )

    @pytest.mark.unit
    def test_db_save_called_on_successful_adaptation(self):
        adapter, db = _loaded_adapter(is_cold_start=False, false_neg_rate=0.0)
        adapter.propose_adaptation("VO2_READINESS_MIN", +1.0, 65.0)
        db.save_threshold_offset.assert_called_once()
        call_kwargs = db.save_threshold_offset.call_args
        assert call_kwargs.kwargs["threshold_key"] == "VO2_READINESS_MIN"
        assert call_kwargs.kwargs["source"] == "calibration"


# ---------------------------------------------------------------------------
# Test 6 — propose_adaptation: ceiling enforced
# ---------------------------------------------------------------------------

class TestProposeAdaptationCeilingEnforced:
    @pytest.mark.unit
    def test_ceiling_clamps_at_max_delta_pct(self):
        # Start near ceiling (0.19), push positive — should clamp at 0.20
        start_delta = THRESHOLD_ADAPTER_MAX_DELTA_PCT - THRESHOLD_ADAPTER_DAMPING_PCT * 0.5
        adapter, db = _loaded_adapter(
            offsets=[{"threshold_key": "VO2_READINESS_MIN", "delta_value": start_delta}],
            is_cold_start=False,
            false_neg_rate=0.0,
        )
        result = adapter.propose_adaptation("VO2_READINESS_MIN", +1.0, 65.0)
        assert result is True
        assert math.isclose(
            adapter._offsets["VO2_READINESS_MIN"],
            THRESHOLD_ADAPTER_MAX_DELTA_PCT,
            rel_tol=1e-9,
        )

    @pytest.mark.unit
    def test_already_at_ceiling_returns_false(self):
        adapter, db = _loaded_adapter(
            offsets=[{"threshold_key": "VO2_READINESS_MIN",
                      "delta_value": THRESHOLD_ADAPTER_MAX_DELTA_PCT}],
            is_cold_start=False,
            false_neg_rate=0.0,
        )
        result = adapter.propose_adaptation("VO2_READINESS_MIN", +1.0, 65.0)
        assert result is False
        db.save_threshold_offset.assert_not_called()

    @pytest.mark.unit
    def test_negative_ceiling_clamps_at_minus_max_delta_pct(self):
        start_delta = -(THRESHOLD_ADAPTER_MAX_DELTA_PCT - THRESHOLD_ADAPTER_DAMPING_PCT * 0.5)
        adapter, db = _loaded_adapter(
            offsets=[{"threshold_key": "VO2_READINESS_MIN", "delta_value": start_delta}],
            is_cold_start=False,
            false_neg_rate=0.0,
        )
        result = adapter.propose_adaptation("VO2_READINESS_MIN", -1.0, 65.0)
        assert result is True
        assert math.isclose(
            adapter._offsets["VO2_READINESS_MIN"],
            -THRESHOLD_ADAPTER_MAX_DELTA_PCT,
            rel_tol=1e-9,
        )


# ---------------------------------------------------------------------------
# Test 7 — circuit breaker disabled during cold-start (ADR-0033 L3-C)
# ---------------------------------------------------------------------------

class TestCircuitBreakerDisabledDuringColdStart:
    @pytest.mark.unit
    def test_cold_start_returns_false_regardless_of_rate(self):
        # Even with a sky-high false-neg rate, cold-start bypasses the breaker
        adapter, db = _loaded_adapter(is_cold_start=True, false_neg_rate=0.99)
        assert adapter.is_circuit_breaker_active() is False
        db.get_false_negative_rate.assert_not_called()

    @pytest.mark.unit
    def test_non_cold_start_checks_false_neg_rate(self):
        adapter, db = _loaded_adapter(is_cold_start=False, false_neg_rate=0.0)
        adapter.is_circuit_breaker_active()
        db.get_false_negative_rate.assert_called_once()

    @pytest.mark.unit
    def test_non_cold_start_high_rate_activates_breaker(self):
        from titan.config.thresholds import THRESHOLD_ADAPTER_FALSE_NEG_RATE_LIMIT
        adapter, _ = _loaded_adapter(
            is_cold_start=False,
            false_neg_rate=THRESHOLD_ADAPTER_FALSE_NEG_RATE_LIMIT + 0.01,
        )
        assert adapter.is_circuit_breaker_active() is True

    @pytest.mark.unit
    def test_non_cold_start_below_rate_limit_no_breaker(self):
        from titan.config.thresholds import THRESHOLD_ADAPTER_FALSE_NEG_RATE_LIMIT
        adapter, _ = _loaded_adapter(
            is_cold_start=False,
            false_neg_rate=THRESHOLD_ADAPTER_FALSE_NEG_RATE_LIMIT - 0.01,
        )
        assert adapter.is_circuit_breaker_active() is False


# ---------------------------------------------------------------------------
# Test 8 — INV-01 compliance: non-finite base_value returned unchanged
# ---------------------------------------------------------------------------

class TestNonFiniteBaseValueReturnedUnchanged:
    @pytest.mark.unit
    def test_nan_returned_unchanged(self):
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "VO2_READINESS_MIN", "delta_value": 0.10}]
        )
        result = adapter.get_threshold("VO2_READINESS_MIN", float("nan"))
        assert math.isnan(result)

    @pytest.mark.unit
    def test_inf_returned_unchanged(self):
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "VO2_READINESS_MIN", "delta_value": 0.10}]
        )
        result = adapter.get_threshold("VO2_READINESS_MIN", float("inf"))
        assert math.isinf(result)

    @pytest.mark.unit
    def test_neg_inf_returned_unchanged(self):
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "VO2_READINESS_MIN", "delta_value": 0.10}]
        )
        result = adapter.get_threshold("VO2_READINESS_MIN", float("-inf"))
        assert math.isinf(result) and result < 0


# ---------------------------------------------------------------------------
# Test 9 — round-trip persistence: offset survives load() in a new instance
# ---------------------------------------------------------------------------

class TestRoundTripPersistence:
    @pytest.mark.unit
    def test_offset_persists_across_instances(self):
        """propose_adaptation() → new ThresholdAdapter.load() → offset survives."""
        stored: dict[str, float] = {}

        def fake_save(athlete_id, threshold_key, delta_value, source, confidence, updated_at):
            stored[threshold_key] = delta_value

        def fake_get(athlete_id):
            return [
                {"threshold_key": k, "delta_value": v}
                for k, v in stored.items()
            ]

        db1 = _make_db(is_cold_start=False, false_neg_rate=0.0)
        db1.save_threshold_offset.side_effect = fake_save
        db1.get_athlete_threshold_offsets.side_effect = fake_get

        adapter1 = ThresholdAdapter(athlete_id="athlete_round_trip", db=db1)
        adapter1.load()
        applied = adapter1.propose_adaptation("VO2_READINESS_MIN", +1.0, 65.0)
        assert applied is True

        # Second instance reads from the same backing store
        db2 = _make_db(is_cold_start=False, false_neg_rate=0.0)
        db2.get_athlete_threshold_offsets.side_effect = fake_get
        adapter2 = ThresholdAdapter(athlete_id="athlete_round_trip", db=db2)
        adapter2.load()

        saved_delta = adapter2._offsets.get("VO2_READINESS_MIN")
        assert saved_delta is not None
        assert math.isclose(saved_delta, THRESHOLD_ADAPTER_DAMPING_PCT, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Test 10 — module constants and static helpers
# ---------------------------------------------------------------------------

class TestModuleConstantsAndHelpers:
    @pytest.mark.unit
    def test_module_version(self):
        assert MODULE_VERSION == "1.0.0"

    @pytest.mark.unit
    def test_hard_stop_gate_names_is_nonempty_frozenset(self):
        assert isinstance(HARD_STOP_GATE_NAMES, frozenset)
        assert len(HARD_STOP_GATE_NAMES) > 0

    @pytest.mark.unit
    def test_hard_stop_gate_names_matches_thresholds_frozenset(self):
        assert HARD_STOP_GATE_NAMES == HARD_STOP_THRESHOLD_KEYS

    @pytest.mark.unit
    def test_is_hard_stop_gate_true_for_hard_stop(self):
        assert ThresholdAdapter.is_hard_stop_gate("HARD_STOP_HRV_DELTA") is True

    @pytest.mark.unit
    def test_is_hard_stop_gate_false_for_soft_gate(self):
        assert ThresholdAdapter.is_hard_stop_gate("VO2_READINESS_MIN") is False

    @pytest.mark.unit
    def test_loaded_property_false_before_load(self):
        db = _make_db()
        adapter = ThresholdAdapter(athlete_id="x", db=db)
        assert adapter.loaded is False

    @pytest.mark.unit
    def test_loaded_property_true_after_load(self):
        adapter, _ = _loaded_adapter()
        assert adapter.loaded is True

    @pytest.mark.unit
    def test_athlete_id_property(self):
        db = _make_db()
        adapter = ThresholdAdapter(athlete_id="my_athlete", db=db)
        assert adapter.athlete_id == "my_athlete"


# ---------------------------------------------------------------------------
# Test 11 — GovernanceEngine optional injection (ADR-0052)
# ---------------------------------------------------------------------------

class TestGovernanceEngineInjection:
    @pytest.mark.unit
    def test_governance_engine_accepts_no_adapter(self):
        from titan.science.governance_engine import GovernanceEngine
        engine = GovernanceEngine()
        assert engine._threshold_adapter is None

    @pytest.mark.unit
    def test_governance_engine_accepts_adapter(self):
        from titan.science.governance_engine import GovernanceEngine
        adapter, _ = _loaded_adapter()
        engine = GovernanceEngine(threshold_adapter=adapter)
        assert engine._threshold_adapter is adapter

    @pytest.mark.unit
    def test_get_soft_threshold_no_adapter_returns_base(self):
        from titan.science.governance_engine import GovernanceEngine
        engine = GovernanceEngine()
        result = engine._get_soft_threshold("VO2_READINESS_MIN", 65.0)
        assert result == 65.0

    @pytest.mark.unit
    def test_get_soft_threshold_with_adapter_applies_delta(self):
        from titan.science.governance_engine import GovernanceEngine
        adapter, _ = _loaded_adapter(
            offsets=[{"threshold_key": "VO2_READINESS_MIN", "delta_value": 0.10}]
        )
        engine = GovernanceEngine(threshold_adapter=adapter)
        result = engine._get_soft_threshold("VO2_READINESS_MIN", 65.0)
        assert math.isclose(result, 65.0 * 1.10, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Test 12 — circuit breaker blocks propose_adaptation
# ---------------------------------------------------------------------------

class TestCircuitBreakerBlocksAdaptation:
    @pytest.mark.unit
    def test_active_breaker_returns_false(self):
        from titan.config.thresholds import THRESHOLD_ADAPTER_FALSE_NEG_RATE_LIMIT
        adapter, db = _loaded_adapter(
            is_cold_start=False,
            false_neg_rate=THRESHOLD_ADAPTER_FALSE_NEG_RATE_LIMIT + 0.05,
        )
        result = adapter.propose_adaptation("VO2_READINESS_MIN", +1.0, 65.0)
        assert result is False
        db.save_threshold_offset.assert_not_called()

    @pytest.mark.unit
    def test_zero_direction_returns_false(self):
        adapter, db = _loaded_adapter(is_cold_start=False, false_neg_rate=0.0)
        result = adapter.propose_adaptation("VO2_READINESS_MIN", 0.0, 65.0)
        assert result is False
        db.save_threshold_offset.assert_not_called()

    @pytest.mark.unit
    def test_nan_direction_returns_false(self):
        adapter, db = _loaded_adapter(is_cold_start=False, false_neg_rate=0.0)
        result = adapter.propose_adaptation("VO2_READINESS_MIN", float("nan"), 65.0)
        assert result is False
        db.save_threshold_offset.assert_not_called()

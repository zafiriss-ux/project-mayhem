"""
Chaos injection tests for GovernanceEngine (Pass 3).

Verifies that governance gates degrade gracefully and apply fail-safe
conservative outcomes when dependencies misbehave.

5 chaos scenarios:
  C1 — DB raises RuntimeError during override ratio read → fail-safe lock
  C2 — DB returns None for override ratio       → fail-safe lock
  C3 — All biometric context fields are None    → apply_constraints does not crash
  C4 — Corrupt intensity_gate_result            → apply_constraints does not crash
  C5 — cs_tracker missing .confidence attribute → CS lock fires conservatively
"""

import pytest

from titan.science.governance_engine import GovernanceEngine

# ─── Stubs ────────────────────────────────────────────────────────────────────


class _RaisingDB:
    """DB stub that raises a configurable exception on get_override_ratio."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def get_override_ratio(self, **_kwargs: object) -> float:
        raise self._exc


class _NoneRatioDB:
    """DB stub that returns None (invalid) for override ratio."""

    def get_override_ratio(self, **_kwargs: object) -> None:  # type: ignore[override]
        return None


class _NeutralDB:
    """DB stub returning a safe 0 % override ratio."""

    def get_override_ratio(self, **_kwargs: object) -> float:
        return 0.0


class _FullConfidenceTracker:
    """CS tracker stub at full confidence."""

    confidence = 1.0


def _safe_plan(session_type: str = "INTERVALS") -> dict:
    return {"session_type": session_type, "max_zone": 5}


def _safe_ctx(**overrides: object) -> dict:
    """Minimal valid context that fires no governance gates."""
    ctx: dict = {
        "today_hrv": 60.0,
        "baseline_hrv": 60.0,
        "hrv_std_dev": 5.0,
        "today_rhr": 50,
        "baseline_rhr": 50.0,
        "tsb_value": 0.0,
        "subjective_fatigue_score": 0,
        "injury_flag": False,
        "sleep_score": 80,
        "readiness_score": 75.0,
        "acwr": 1.1,
        "glycogen_debt": 2.0,
        "days_since_last_vo2": 3,
        "fueling_confirmed": True,
        "db": _NeutralDB(),
        "cs_tracker": _FullConfidenceTracker(),
        "afi_constraints": {},
        "intensity_gate_result": None,
    }
    ctx.update(overrides)
    return ctx


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestChaosScenarios:

    # C1 — DB raises RuntimeError during ratio read
    def test_c1_db_runtime_error_returns_fail_safe_lock(self) -> None:
        """RuntimeError from DB must produce locked=True fail-safe, not propagate."""
        gov = GovernanceEngine()
        result = gov.check_override_lockdown(db=_RaisingDB(RuntimeError("disk I/O error")))

        assert result["locked"] is True
        assert result.get("error_code") in {"DB_READ_ERROR", "SCHEMA_MISMATCH"}
        assert result.get("max_zone") == 2

    # C2 — DB returns None for override ratio
    def test_c2_db_none_ratio_returns_fail_safe_lock(self) -> None:
        """None override ratio must trigger the fail-safe conservative lock path."""
        gov = GovernanceEngine()
        result = gov.check_override_lockdown(db=_NoneRatioDB())

        assert result["locked"] is True

    # C3 — All biometric fields are None
    def test_c3_all_none_biometrics_does_not_crash(self) -> None:
        """apply_constraints must not raise when every biometric field is None."""
        gov = GovernanceEngine()
        plan = _safe_plan()
        ctx = _safe_ctx(
            today_hrv=None,
            baseline_hrv=None,
            hrv_std_dev=None,
            today_rhr=None,
            baseline_rhr=None,
            tsb_value=None,
            subjective_fatigue_score=None,
            sleep_score=None,
            readiness_score=None,
        )
        result = gov.apply_constraints(plan, ctx)

        assert isinstance(result, dict)
        assert "governance_locks_applied" in result

    # C4 — Corrupt (non-dict) intensity_gate_result
    @pytest.mark.parametrize(
        "bad_value",
        [
            "RED",   # string
            42,      # integer
            [],      # empty list
        ],
    )
    def test_c4_corrupt_intensity_gate_does_not_crash(self, bad_value: object) -> None:
        """A non-dict intensity_gate_result must be handled without raising."""
        gov = GovernanceEngine()
        plan = _safe_plan()
        ctx = _safe_ctx(intensity_gate_result=bad_value)
        result = gov.apply_constraints(plan, ctx)

        assert isinstance(result, dict)
        assert "governance_locks_applied" in result

    # C5 — cs_tracker missing .confidence attribute
    def test_c5_cs_tracker_missing_confidence_fires_conservative_lock(self) -> None:
        """cs_tracker without a .confidence attribute must produce locked=True."""
        gov = GovernanceEngine()

        class _BareTracker:
            """Tracker with no confidence attribute."""

        result = gov.check_cs_confidence_lock(cs_tracker=_BareTracker())

        assert result["locked"] is True
        assert result["confidence"] == 0.0

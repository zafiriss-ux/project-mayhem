"""
Governance golden-case tests (Pass 3).

12 named scenarios covering each governance gate and the full decision
pipeline end-to-end.  Each scenario is a self-documenting test that
asserts a specific, expected governance outcome.

Gate coverage:
  H1 — Injury flag             (test 5)
  H2 — HRV collapse            (test 2)
  H3 — RHR spike               (test 3)
  H4 — TSB critical floor      (test 4)
  H5 — Extreme fatigue         (test 6)
  VO2 eligibility: V1 ACWR     (test 7)
  VO2 eligibility: V2 readiness(test 8)
  Override lockdown            (test 9)
  CS confidence lock           (test 10)
  2-of-4 downgrade             (test 11)
  Fueling gate lock            (test 12)
  Governance clean             (test 1)
"""

import pytest

from titan.config.thresholds import (
    HARD_STOP_HRV_DELTA,
    HARD_STOP_RHR_DELTA,
    HARD_STOP_TSB_FLOOR,
    SUBJECTIVE_FATIGUE_EXTREME,
    VO2_ACWR_MAX,
    VO2_READINESS_MIN,
)
from titan.science.governance_engine import GovernanceEngine

# ─── Stubs ────────────────────────────────────────────────────────────────────


class _NeutralDB:
    """DB stub: 0 % override ratio — no lockdown."""

    def get_override_ratio(self, **_kwargs: object) -> float:
        return 0.0


class _LockedDB:
    """DB stub: 90 % override ratio — above the 80 % lockdown ceiling."""

    def get_override_ratio(self, **_kwargs: object) -> float:
        return 0.90


class _FullCSTracker:
    """CS tracker stub at full confidence — no CS lock."""

    confidence = 1.0


class _LowCSTracker:
    """CS tracker stub below the 0.70 confidence threshold."""

    confidence = 0.50


# ─── Context factory ──────────────────────────────────────────────────────────


def _make(
    session_type: str = "INTERVALS",
    max_zone: int = 5,
    **ctx_overrides: object,
) -> tuple[dict, dict]:
    """Return (plan, context) with every governance gate passing by default."""
    plan: dict = {"session_type": session_type, "max_zone": max_zone}
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
        "athlete_id": "owner",  # ADR-0068: the lockdown reads this athlete's ratio
        "cs_tracker": _FullCSTracker(),
        "afi_constraints": {},
        "intensity_gate_result": None,
    }
    ctx.update(ctx_overrides)
    return plan, ctx


_GOV = GovernanceEngine()  # stateless — safe to share across tests


# ─── Golden cases ─────────────────────────────────────────────────────────────


class TestGovernanceGoldenCases:

    # 1 — Healthy athlete: quality session survives governance clean
    @pytest.mark.unit
    @pytest.mark.governance
    def test_01_healthy_athlete_intervals_governance_clean(self) -> None:
        """Neutral context: INTERVALS must pass all gates and report governance_clean=True."""
        plan, ctx = _make("INTERVALS")
        _GOV.apply_constraints(plan, ctx)

        assert plan["governance_clean"] is True
        assert plan["session_type"] == "INTERVALS"
        assert plan["governance_locks_applied"] == []

    # 2 — HRV collapse: H2 hard stop → REST
    @pytest.mark.unit
    @pytest.mark.governance
    def test_02_hrv_collapse_triggers_h2_rest(self) -> None:
        """HRV drop >= 15 ms (H2 threshold) must force REST and max_zone=1."""
        plan, ctx = _make("INTERVALS", today_hrv=60.0 - HARD_STOP_HRV_DELTA - 5.0, baseline_hrv=60.0)
        _GOV.apply_constraints(plan, ctx)

        assert plan["session_type"] == "REST"
        assert plan["max_zone"] == 1
        gate_codes = [r["gate"] for r in plan.get("hard_stop_reasons", [])]
        assert "H2" in gate_codes

    # 3 — RHR spike: H3 hard stop → REST
    @pytest.mark.unit
    @pytest.mark.governance
    def test_03_rhr_spike_triggers_h3_rest(self) -> None:
        """RHR rise >= 8 bpm (H3 threshold) must force REST and max_zone=1."""
        plan, ctx = _make("INTERVALS", today_rhr=50.0 + HARD_STOP_RHR_DELTA + 4, baseline_rhr=50.0)
        _GOV.apply_constraints(plan, ctx)

        assert plan["session_type"] == "REST"
        assert plan["max_zone"] == 1
        gate_codes = [r["gate"] for r in plan.get("hard_stop_reasons", [])]
        assert "H3" in gate_codes

    # 4 — TSB critical floor: H4 gate → EASY + max_zone capped at 2
    @pytest.mark.unit
    @pytest.mark.governance
    def test_04_tsb_critical_floor_triggers_h4_easy(self) -> None:
        """TSB <= -50 (H4 threshold) must downgrade quality session to EASY and cap max_zone=2."""
        plan, ctx = _make("INTERVALS", tsb_value=HARD_STOP_TSB_FLOOR - 5.0)
        _GOV.apply_constraints(plan, ctx)

        assert plan["session_type"] == "EASY"
        assert plan["max_zone"] <= 2
        gate_codes = [r["gate"] for r in plan.get("hard_stop_reasons", [])]
        assert "H4" in gate_codes

    # 5 — Injury flag: H1 gate → REST (highest-priority gate)
    @pytest.mark.unit
    @pytest.mark.governance
    def test_05_injury_flag_triggers_h1_rest(self) -> None:
        """Active injury_flag=True must trigger H1 gate and force REST unconditionally."""
        plan, ctx = _make("INTERVALS", injury_flag=True)
        _GOV.apply_constraints(plan, ctx)

        assert plan["session_type"] == "REST"
        assert plan["max_zone"] == 1
        gate_codes = [r["gate"] for r in plan.get("hard_stop_reasons", [])]
        assert "H1" in gate_codes

    # 6 — Extreme fatigue: H5 gate → EASY
    @pytest.mark.unit
    @pytest.mark.governance
    def test_06_extreme_fatigue_triggers_h5_downgrade(self) -> None:
        """Subjective fatigue >= 8 (H5 threshold) must downgrade session and cap max_zone=2."""
        plan, ctx = _make("INTERVALS", subjective_fatigue_score=SUBJECTIVE_FATIGUE_EXTREME + 1)
        _GOV.apply_constraints(plan, ctx)

        assert plan["session_type"] in {"EASY", "REST"}
        assert plan["max_zone"] <= 2
        gate_codes = [r["gate"] for r in plan.get("hard_stop_reasons", [])]
        assert "H5" in gate_codes

    # 7 — High ACWR: V1 VO2 eligibility failure → HAMMER ineligible
    @pytest.mark.unit
    @pytest.mark.governance
    def test_07_high_acwr_blocks_vo2_hammer(self) -> None:
        """ACWR > 1.30 (V1 condition) must fail VO2 eligibility gate for HAMMER."""
        plan, ctx = _make("HAMMER", acwr=VO2_ACWR_MAX + 0.25)
        _GOV.apply_constraints(plan, ctx)

        vo2 = plan.get("vo2_eligibility", {})
        assert vo2.get("eligible") is False
        assert "V1" in vo2.get("failed_conditions", [])

    # 8 — Low readiness: V2 VO2 eligibility failure → HAMMER ineligible
    @pytest.mark.unit
    @pytest.mark.governance
    def test_08_low_readiness_blocks_vo2_hammer(self) -> None:
        """readiness_score < 65 (V2 condition) must fail VO2 eligibility gate for HAMMER."""
        plan, ctx = _make("HAMMER", readiness_score=VO2_READINESS_MIN - 10.0)
        _GOV.apply_constraints(plan, ctx)

        vo2 = plan.get("vo2_eligibility", {})
        assert vo2.get("eligible") is False
        assert "V2" in vo2.get("failed_conditions", [])

    # 9 — Override lockdown: quality sessions blocked → EASY
    @pytest.mark.unit
    @pytest.mark.governance
    def test_09_override_lockdown_blocks_quality_session(self) -> None:
        """Override ratio > 80 % must lock INTERVALS and downgrade to EASY."""
        plan, ctx = _make("INTERVALS", db=_LockedDB())
        _GOV.apply_constraints(plan, ctx)

        assert "OVERRIDE_LOCKDOWN" in plan["governance_locks_applied"]
        assert plan["session_type"] == "EASY"

    # 10 — Low CS confidence: CS lock applied → prediction disabled
    @pytest.mark.unit
    @pytest.mark.governance
    def test_10_low_cs_confidence_sets_calibration_required(self) -> None:
        """CS confidence < 0.70 must set cs_prediction_disabled and required_calibration."""
        plan, ctx = _make("INTERVALS", cs_tracker=_LowCSTracker())
        _GOV.apply_constraints(plan, ctx)

        assert plan.get("cs_prediction_disabled") is True
        assert plan.get("required_calibration") is True
        assert "CS_CONFIDENCE_LOCK" in plan["governance_locks_applied"]

    # 11 — 2-of-4 downgrade: INTERVALS → TEMPO
    @pytest.mark.unit
    @pytest.mark.governance
    def test_11_two_of_four_indicators_downgrade_intervals_to_tempo(self) -> None:
        """HRV soft (I1) + low sleep (I2) must downgrade INTERVALS → TEMPO via 2-of-4 gate."""
        plan, ctx = _make(
            "INTERVALS",
            today_hrv=52.0,   # 52 < baseline(60) - std(5) = 55 → I1 fires
            baseline_hrv=60.0,
            hrv_std_dev=5.0,
            sleep_score=55,   # 55 < 60 threshold → I2 fires
        )
        # HRV drop = 8 ms < 15 ms (H2 threshold) → hard stop does NOT fire
        _GOV.apply_constraints(plan, ctx)

        downgrade = plan.get("downgrade_2of4", {})
        assert downgrade.get("downgrade_2of4") is True
        assert downgrade.get("count", 0) >= 2
        assert "READINESS_2OF4_DOWNGRADE" in plan["governance_locks_applied"]

    # 12 — Fueling gate lock: HAMMER without fueling → TEMPO
    @pytest.mark.unit
    @pytest.mark.governance
    def test_12_fueling_gate_lock_downgrades_hammer_without_fueling(self) -> None:
        """HAMMER session without confirmed fueling must be locked to TEMPO."""
        plan, ctx = _make("HAMMER", fueling_confirmed=False)
        _GOV.apply_constraints(plan, ctx)

        fueling = plan.get("fueling_gate", {})
        assert fueling.get("action") == "LOCK"
        assert plan["session_type"] == "TEMPO"
        assert "FUELING_GATE_LOCK" in plan["governance_locks_applied"]

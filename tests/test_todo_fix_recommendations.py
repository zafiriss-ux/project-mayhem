"""tests/test_todo_fix_recommendations.py

P0/P1/P2/P3 tests recommended after resolving the TODO comments identified
in the ADR-0007 audit of titan/orchestration/daily_coach.py.

Coverage targets
----------------
P0  GovernanceEngine — four hard-stop gates (H1 injury, H2 HRV, H3 RHR, H4 TSB)
P1  GovernanceEngine — 2-of-4 soft downgrade (I2 sleep indicator boundary)
P1  IntensityGovernor — YELLOW / RED colour gates and zone caps
P2  GovernanceEngine — VO2 eligibility gate (V5: days_since_last_vo2)
"""

import pytest

from titan.config.thresholds import (
    HARD_STOP_HRV_DELTA,
    HARD_STOP_RHR_DELTA,
    HARD_STOP_TSB_FLOOR,
    SUBJECTIVE_FATIGUE_2OF4,
    VO2_MIN_DAYS_SINCE_LAST,
)
from titan.science.governance_engine import GovernanceEngine
from titan.science.intensity_governor import IntensityGovernor

# ── Helpers ──────────────────────────────────────────────────────────────────


@pytest.fixture
def gov():
    return GovernanceEngine()


@pytest.fixture
def ig():
    return IntensityGovernor()


def _green_gate_result():
    """A GREEN IntensityGovernor result that never interferes with other gates."""
    return IntensityGovernor().evaluate(
        {
            "drift_pct": 0.0,
            "glycogen_debt": 1.0,
            "acwr": 1.0,
            "readiness_score": 80.0,
            "fatigue_level": "LOW",
            "planned_session": "EASY",
            "planned_volume_pct": 1.0,
        }
    )


def make_context(**overrides):
    """
    Baseline governance context — no gate fires with these defaults.
    All metrics sit inside their safe operating envelopes.
    """
    ctx = {
        # HRV: no drop from baseline
        "today_hrv": 50.0,
        "baseline_hrv": 50.0,
        "hrv_std_dev": 5.0,
        # RHR: no spike
        "today_rhr": 50.0,
        "baseline_rhr": 50.0,
        # Load / metabolic
        "tsb_value": 0.0,
        "acwr": 1.0,
        "glycogen_debt": 2.0,
        # Subjective state
        "subjective_fatigue_score": 0,
        "fatigue_level": "LOW",
        # Sleep / readiness
        "sleep_score": 75,
        "readiness_score": 80.0,
        # Medical
        "injury_flag": False,
        # VO2 eligibility
        "days_since_last_vo2": 5,
        "fueling_confirmed": True,
        # Planning
        "planned_duration_min": 45,
        # Pre-evaluated intensity gate
        "intensity_gate_result": _green_gate_result(),
    }
    ctx.update(overrides)
    return ctx


def make_plan(session_type="EASY", **overrides):
    plan = {"session_type": session_type, "max_zone": 5, "duration_min": 45}
    plan.update(overrides)
    return plan


# ── P0: H2 — HRV Collapse Hard Stop ─────────────────────────────────────────


class TestHRVCollapseHardStop:
    """H2 gate fires when today_hrv drops more than HARD_STOP_HRV_DELTA % below baseline."""

    def test_fires_when_hrv_drops_beyond_threshold(self, gov):
        # Gate check: today_hrv < baseline_hrv - HARD_STOP_HRV_DELTA (absolute ms drop)
        baseline = 50.0
        ctx = make_context(today_hrv=baseline - HARD_STOP_HRV_DELTA - 0.1, baseline_hrv=baseline)
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "HARD_STOP_SAFETY_GATES" in result.get("governance_locks_applied", [])

    def test_does_not_fire_at_exact_threshold(self, gov):
        # Boundary: today_hrv == baseline - HARD_STOP_HRV_DELTA → strictly NOT < floor
        baseline = 50.0
        ctx = make_context(today_hrv=baseline - HARD_STOP_HRV_DELTA, baseline_hrv=baseline)
        result = gov.apply_constraints(make_plan("EASY"), ctx)
        assert "HARD_STOP_SAFETY_GATES" not in result.get("governance_locks_applied", [])

    def test_does_not_fire_within_threshold(self, gov):
        baseline = 50.0
        ctx = make_context(today_hrv=baseline - HARD_STOP_HRV_DELTA + 0.5, baseline_hrv=baseline)
        result = gov.apply_constraints(make_plan("EASY"), ctx)
        assert "HARD_STOP_SAFETY_GATES" not in result.get("governance_locks_applied", [])

    def test_session_downgraded_on_hrv_collapse(self, gov):
        baseline = 50.0
        ctx = make_context(today_hrv=baseline * 0.5, baseline_hrv=baseline)
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert result["session_type"] in ("REST", "EASY")


# ── P0: H3 — RHR Spike Hard Stop ─────────────────────────────────────────────


class TestRHRSpikeHardStop:
    """H3 gate fires when today_rhr exceeds baseline_rhr + HARD_STOP_RHR_DELTA bpm."""

    def test_fires_when_rhr_spikes_above_threshold(self, gov):
        baseline = 50.0
        ctx = make_context(
            today_rhr=baseline + HARD_STOP_RHR_DELTA + 0.1,
            baseline_rhr=baseline,
        )
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "HARD_STOP_SAFETY_GATES" in result.get("governance_locks_applied", [])

    def test_does_not_fire_below_rhr_threshold(self, gov):
        baseline = 50.0
        ctx = make_context(
            today_rhr=baseline + HARD_STOP_RHR_DELTA - 0.5,
            baseline_rhr=baseline,
        )
        result = gov.apply_constraints(make_plan("EASY"), ctx)
        assert "HARD_STOP_SAFETY_GATES" not in result.get("governance_locks_applied", [])

    @pytest.mark.parametrize("delta", [9.0, 15.0, 30.0])
    def test_fires_for_various_spikes(self, gov, delta):
        baseline = 50.0
        ctx = make_context(today_rhr=baseline + delta, baseline_rhr=baseline)
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "HARD_STOP_SAFETY_GATES" in result.get("governance_locks_applied", [])


# ── P0: H4 — TSB Critical Floor ──────────────────────────────────────────────


class TestTSBCriticalFloor:
    """H4 gate fires when tsb_value falls below HARD_STOP_TSB_FLOOR (−50)."""

    def test_fires_when_tsb_below_floor(self, gov):
        ctx = make_context(tsb_value=HARD_STOP_TSB_FLOOR - 1.0)
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "HARD_STOP_SAFETY_GATES" in result.get("governance_locks_applied", [])

    def test_does_not_fire_above_floor(self, gov):
        ctx = make_context(tsb_value=HARD_STOP_TSB_FLOOR + 1.0)
        result = gov.apply_constraints(make_plan("EASY"), ctx)
        assert "HARD_STOP_SAFETY_GATES" not in result.get("governance_locks_applied", [])

    @pytest.mark.parametrize("tsb", [-49.9, 0.0, 10.0])
    def test_safe_tsb_values_produce_no_lock(self, gov, tsb):
        ctx = make_context(tsb_value=tsb)
        result = gov.apply_constraints(make_plan("EASY"), ctx)
        assert "HARD_STOP_SAFETY_GATES" not in result.get("governance_locks_applied", [])


# ── P0: H1 — Injury / Medical Flag Gate ──────────────────────────────────────


class TestInjuryFlagGate:
    """H1 gate fires when injury_flag=True; must downgrade session regardless of other metrics."""

    def test_fires_when_injury_flag_set(self, gov):
        ctx = make_context(injury_flag=True)
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "HARD_STOP_SAFETY_GATES" in result.get("governance_locks_applied", [])
        assert result["session_type"] in ("REST", "EASY")

    def test_clears_when_no_injury_flag(self, gov):
        ctx = make_context(injury_flag=False)
        result = gov.apply_constraints(make_plan("EASY"), ctx)
        assert "HARD_STOP_SAFETY_GATES" not in result.get("governance_locks_applied", [])

    def test_injury_overrides_excellent_metrics(self, gov):
        """Perfect HRV, low RHR, and positive TSB cannot bypass the injury gate."""
        ctx = make_context(
            injury_flag=True,
            today_hrv=80.0,
            baseline_hrv=50.0,
            today_rhr=40.0,
            baseline_rhr=60.0,
            tsb_value=10.0,
        )
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "HARD_STOP_SAFETY_GATES" in result.get("governance_locks_applied", [])


# ── P1: 2-of-4 Soft Downgrade — Sleep Score Indicator (I2) ───────────────────


class TestSleepScore2of4Indicator:
    """
    I2: sleep_score < 60 counts as one negative readiness indicator.
    The 2-of-4 soft downgrade fires when at least two indicators are present.
    """

    def test_sleep_plus_subjective_fatigue_triggers_downgrade(self, gov):
        """I2 (sleep < 60) + I4 (subjective_fatigue >= 6) → two indicators → DOWNGRADE."""
        ctx = make_context(
            sleep_score=55,
            subjective_fatigue_score=SUBJECTIVE_FATIGUE_2OF4,
            readiness_score=80.0,
            today_hrv=50.0,
            baseline_hrv=50.0,
            hrv_std_dev=5.0,
        )
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "READINESS_2OF4_DOWNGRADE" in result.get("governance_locks_applied", [])

    def test_sleep_alone_does_not_trigger_downgrade(self, gov):
        """One bad indicator alone must NOT trigger the 2-of-4 downgrade."""
        ctx = make_context(
            sleep_score=55,
            subjective_fatigue_score=0,
            readiness_score=80.0,
            today_hrv=50.0,
            baseline_hrv=50.0,
            hrv_std_dev=5.0,
        )
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "READINESS_2OF4_DOWNGRADE" not in result.get("governance_locks_applied", [])

    @pytest.mark.parametrize(
        "sleep_score, expect_2of4",
        [
            (59, True),   # strictly below 60 → I2 fires → 2 total → DOWNGRADE
            (60, False),  # boundary: at 60 → I2 does NOT fire → only 1 total
            (45, True),   # well below
            (85, False),  # excellent sleep
        ],
    )
    def test_sleep_indicator_boundary(self, gov, sleep_score, expect_2of4):
        """Exact < 60 boundary for indicator I2, with I4 always contributing one signal."""
        ctx = make_context(
            sleep_score=sleep_score,
            subjective_fatigue_score=SUBJECTIVE_FATIGUE_2OF4,  # I4 always fires
            readiness_score=80.0,
            today_hrv=50.0,
            baseline_hrv=50.0,
            hrv_std_dev=5.0,
        )
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        locks = result.get("governance_locks_applied", [])
        if expect_2of4:
            assert "READINESS_2OF4_DOWNGRADE" in locks
        else:
            assert "READINESS_2OF4_DOWNGRADE" not in locks


# ── P1: IntensityGovernor YELLOW / RED Gates ─────────────────────────────────


class TestIntensityGovernorColorGates:
    """IntensityGovernor correctly classifies signals into GREEN / YELLOW / RED."""

    @pytest.fixture
    def green_signals(self):
        return {
            "drift_pct": 0.0,
            "glycogen_debt": 1.0,
            "acwr": 1.0,
            "readiness_score": 80.0,
            "fatigue_level": "LOW",
            "planned_session": "EASY",
            "planned_volume_pct": 1.0,
        }

    def test_green_baseline_gives_max_zone_5(self, ig, green_signals):
        result = ig.evaluate(green_signals)
        assert result.color == "GREEN"
        assert result.max_zone == 5
        assert result.volume_modifier == 1.0

    # — Drift signals ──────────────────────────────────────────────────────────

    def test_drift_above_3_5_triggers_yellow(self, ig, green_signals):
        green_signals["drift_pct"] = 3.6
        result = ig.evaluate(green_signals)
        assert result.color == "YELLOW"
        assert result.max_zone <= 3

    def test_drift_at_3_5_stays_green(self, ig, green_signals):
        green_signals["drift_pct"] = 3.5
        result = ig.evaluate(green_signals)
        assert result.color == "GREEN"

    def test_drift_above_5_triggers_red(self, ig, green_signals):
        green_signals["drift_pct"] = 5.1
        result = ig.evaluate(green_signals)
        assert result.color == "RED"
        assert result.max_zone <= 2

    # — Glycogen signals ───────────────────────────────────────────────────────

    def test_glycogen_at_4_triggers_yellow(self, ig, green_signals):
        green_signals["glycogen_debt"] = 4.0
        result = ig.evaluate(green_signals)
        assert result.color == "YELLOW"
        assert result.volume_modifier < 1.0

    def test_glycogen_above_6_triggers_red(self, ig, green_signals):
        green_signals["glycogen_debt"] = 7.0
        result = ig.evaluate(green_signals)
        assert result.color == "RED"
        assert result.max_zone <= 2

    # — Fatigue signals ────────────────────────────────────────────────────────

    def test_medium_fatigue_triggers_yellow(self, ig, green_signals):
        green_signals["fatigue_level"] = "MEDIUM"
        result = ig.evaluate(green_signals)
        assert result.color == "YELLOW"

    def test_high_fatigue_triggers_red(self, ig, green_signals):
        green_signals["fatigue_level"] = "HIGH"
        result = ig.evaluate(green_signals)
        assert result.color == "RED"
        assert result.max_zone <= 2


# ── P2: VO2 Eligibility Gate — V5: days_since_last_vo2 ───────────────────────


class TestVO2EligibilityGateDaysSinceLast:
    """V5 gate: VO2 session blocked when days_since_last_vo2 < VO2_MIN_DAYS_SINCE_LAST (2)."""

    def test_blocks_when_days_too_low(self, gov):
        ctx = make_context(
            days_since_last_vo2=VO2_MIN_DAYS_SINCE_LAST - 1,
            acwr=1.0,
            glycogen_debt=2.0,
            readiness_score=80.0,
            fatigue_level="LOW",
        )
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "VO2_ELIGIBILITY_GATE" in result.get("governance_locks_applied", [])

    def test_allows_when_sufficient_days_elapsed(self, gov):
        ctx = make_context(
            days_since_last_vo2=VO2_MIN_DAYS_SINCE_LAST + 1,
            acwr=1.0,
            glycogen_debt=2.0,
            readiness_score=80.0,
            fatigue_level="LOW",
        )
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "VO2_ELIGIBILITY_GATE" not in result.get("governance_locks_applied", [])

    def test_easy_session_not_subject_to_vo2_gate(self, gov):
        """EASY sessions are never evaluated for VO2 eligibility."""
        ctx = make_context(days_since_last_vo2=0)
        result = gov.apply_constraints(make_plan("EASY"), ctx)
        assert "VO2_ELIGIBILITY_GATE" not in result.get("governance_locks_applied", [])

    @pytest.mark.parametrize("days", [0, 1])
    def test_various_too_soon_values_all_blocked(self, gov, days):
        ctx = make_context(days_since_last_vo2=days)
        result = gov.apply_constraints(make_plan("INTERVALS"), ctx)
        assert "VO2_ELIGIBILITY_GATE" in result.get("governance_locks_applied", [])

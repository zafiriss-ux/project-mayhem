"""
APL integration tests — AdaptivePriorityLock + OutcomeTracker + EvidenceRegistry.

Test scope:
  - APL output contract: all required keys always present
  - PARASYMPATHETIC_GUARD is always rank 1 (non-negotiable)
  - Phase × load matrix produces correct gate ordering per spec
  - Adaptive threshold scaling per phase
  - Stateless: same inputs always produce the same outputs
  - VLG → load_band mapping used by APL
  - OutcomeTracker: record/retrieve round-trip, calibration summary
  - EvidenceRegistry: query helpers, all canonical parameters covered
"""

import pytest

from titan.config.evidence_registry import (
    EVIDENCE_REGISTRY,
    get_calibration_candidates,
    get_evidence,
    get_policy_parameters,
    get_registry_summary,
)
from titan.config.thresholds import (
    HARD_STOP_HRV_DELTA,
    HARD_STOP_RHR_DELTA,
    HARD_STOP_TSB_FLOOR,
    SUBJECTIVE_FATIGUE_2OF4,
    SUBJECTIVE_FATIGUE_EXTREME,
    VO2_ACWR_MAX,
    VO2_ACWR_MIN,
    VO2_GLYCOGEN_DEBT_MAX,
    VO2_MIN_DAYS_SINCE_LAST,
    VO2_READINESS_MIN,
)
from titan.science.adaptive_priority_lock import AdaptivePriorityLock
from titan.science.outcome_tracker import OutcomeTracker
from titan.science.volume_load_gauge import VLGState, VolumeLoadGauge

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def apl():
    return AdaptivePriorityLock()


@pytest.fixture
def vlg():
    return VolumeLoadGauge()


@pytest.fixture
def green_vlg_state(vlg):
    """GREEN VLGState: all components within safe range."""
    return vlg.resolve(tsb_value=-10.0, acwr=1.05, glycogen_debt=1.0)


@pytest.fixture
def red_vlg_state(vlg):
    """RED VLGState: TSB at hard floor."""
    return vlg.resolve(tsb_value=-55.0, acwr=1.6, glycogen_debt=8.0)


@pytest.fixture
def yellow_vlg_state(vlg):
    """YELLOW VLGState: mild overload."""
    return vlg.resolve(tsb_value=-35.0, acwr=1.35, glycogen_debt=2.0)


@pytest.fixture
def no_para_guard():
    """AFI constraints with parasympathetic guard NOT triggered."""
    return {'parasympathetic_guard': {'triggered': False, 'reason': ''}}


@pytest.fixture
def active_para_guard():
    """AFI constraints with parasympathetic guard TRIGGERED."""
    return {
        'parasympathetic_guard': {
            'triggered': True,
            'reason': 'AFI < -0.5 and HRR60 depressed',
        }
    }


@pytest.fixture
def tracker():
    return OutcomeTracker()


@pytest.fixture
def dummy_apl_result():
    return {
        'priority_vector': {
            'PARASYMPATHETIC_GUARD': 1,
            'CS_CONFIDENCE_LOCK': 2,
            'OVERRIDE_LOCKDOWN': 3,
        },
        'lock_thresholds': {
            'acwr_ceiling': 1.10,
            'tsb_floor': -20.0,
            'cs_min_confidence': 0.85,
        },
        'apl_rationale': {},
    }


# ──────────────────────────────────────────────────────────────────────────────
# APL output contract
# ──────────────────────────────────────────────────────────────────────────────

class TestAPLOutputContract:
    """APL always returns a dict with the three required top-level keys."""

    REQUIRED_KEYS = {'priority_vector', 'lock_thresholds', 'apl_rationale'}
    PRIORITY_VECTOR_GATES = {'PARASYMPATHETIC_GUARD', 'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN'}
    LOCK_THRESHOLD_KEYS = {'acwr_ceiling', 'tsb_floor', 'cs_min_confidence'}

    @pytest.mark.parametrize('phase', ['BASE', 'BUILD', 'PEAK', 'TAPER', 'POST_RACE'])
    def test_required_keys_present_for_all_phases(self, apl, green_vlg_state, no_para_guard, phase):
        result = apl.resolve(
            vlg_state=green_vlg_state,
            afi_constraints=no_para_guard,
            phase=phase,
            cs_confidence=0.8,
        )
        assert set(result.keys()) == self.REQUIRED_KEYS, (
            f'Missing keys for phase={phase}: {self.REQUIRED_KEYS - set(result.keys())}'
        )

    def test_priority_vector_has_all_three_gates(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'BASE', 0.8)
        assert set(result['priority_vector'].keys()) == self.PRIORITY_VECTOR_GATES

    def test_lock_thresholds_has_all_three_keys(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'BASE', 0.8)
        assert self.LOCK_THRESHOLD_KEYS.issubset(result['lock_thresholds'].keys())

    def test_apl_rationale_covers_all_three_gates(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'BASE', 0.8)
        assert set(result['apl_rationale'].keys()) == self.PRIORITY_VECTOR_GATES


# ──────────────────────────────────────────────────────────────────────────────
# PARASYMPATHETIC_GUARD is always rank 1
# ──────────────────────────────────────────────────────────────────────────────

class TestParasympatheticGuardInvariant:
    """PARASYMPATHETIC_GUARD must be rank 1 in every possible input combination."""

    @pytest.mark.parametrize('phase', ['BASE', 'BUILD', 'PEAK', 'TAPER', 'POST_RACE'])
    @pytest.mark.parametrize('cs_confidence', [0.0, 0.5, 1.0])
    def test_para_guard_always_rank_1(
        self, apl, green_vlg_state, red_vlg_state, yellow_vlg_state,
        no_para_guard, active_para_guard, phase, cs_confidence,
    ):
        for vlg_state in (green_vlg_state, red_vlg_state, yellow_vlg_state):
            for afi in (no_para_guard, active_para_guard):
                result = apl.resolve(vlg_state, afi, phase, cs_confidence)
                pv = result['priority_vector']
                assert pv['PARASYMPATHETIC_GUARD'] == 1, (
                    f'PARASYMPATHETIC_GUARD rank was {pv["PARASYMPATHETIC_GUARD"]} '
                    f'for phase={phase}, cs_conf={cs_confidence}'
                )

    def test_para_triggered_appears_in_rationale(self, apl, green_vlg_state, active_para_guard):
        result = apl.resolve(green_vlg_state, active_para_guard, 'BASE', 0.8)
        rationale = result['apl_rationale']['PARASYMPATHETIC_GUARD']
        assert 'ACTIVE' in rationale or 'triggered' in rationale.lower()


# ──────────────────────────────────────────────────────────────────────────────
# Phase × load matrix ordering
# ──────────────────────────────────────────────────────────────────────────────

class TestPhaseLoadMatrix:
    """Verify gate ordering per spec Section 5.2."""

    def test_peak_any_load_cs_rank2(self, apl, green_vlg_state, yellow_vlg_state,
                                    red_vlg_state, no_para_guard):
        """PEAK: CS_CONFIDENCE_LOCK always rank 2 regardless of load."""
        for vlg in (green_vlg_state, yellow_vlg_state, red_vlg_state):
            result = apl.resolve(vlg, no_para_guard, 'PEAK', 0.8)
            pv = result['priority_vector']
            assert pv['CS_CONFIDENCE_LOCK'] == 2, f'PEAK failed: {pv}'
            assert pv['OVERRIDE_LOCKDOWN'] == 3

    def test_taper_any_load_cs_rank2(self, apl, green_vlg_state, red_vlg_state, no_para_guard):
        """TAPER: CS_CONFIDENCE_LOCK always rank 2."""
        for vlg in (green_vlg_state, red_vlg_state):
            result = apl.resolve(vlg, no_para_guard, 'TAPER', 0.8)
            pv = result['priority_vector']
            assert pv['CS_CONFIDENCE_LOCK'] == 2
            assert pv['OVERRIDE_LOCKDOWN'] == 3

    def test_post_race_any_load_override_rank2(self, apl, green_vlg_state, red_vlg_state,
                                                no_para_guard):
        """POST_RACE: OVERRIDE_LOCKDOWN always rank 2."""
        for vlg in (green_vlg_state, red_vlg_state):
            result = apl.resolve(vlg, no_para_guard, 'POST_RACE', 0.8)
            pv = result['priority_vector']
            assert pv['OVERRIDE_LOCKDOWN'] == 2
            assert pv['CS_CONFIDENCE_LOCK'] == 3

    def test_base_any_load_override_rank2(self, apl, green_vlg_state, red_vlg_state,
                                           no_para_guard):
        """BASE: OVERRIDE_LOCKDOWN always rank 2."""
        for vlg in (green_vlg_state, red_vlg_state):
            result = apl.resolve(vlg, no_para_guard, 'BASE', 0.8)
            pv = result['priority_vector']
            assert pv['OVERRIDE_LOCKDOWN'] == 2
            assert pv['CS_CONFIDENCE_LOCK'] == 3

    def test_build_overload_override_rank2(self, apl, vlg, no_para_guard):
        """BUILD + OVERLOAD/CRITICAL: OVERRIDE_LOCKDOWN rank 2."""
        # YELLOW → OVERLOAD
        overload_state = vlg.resolve(tsb_value=-35.0, acwr=1.35, glycogen_debt=2.0)
        result = apl.resolve(overload_state, no_para_guard, 'BUILD', 0.8)
        pv = result['priority_vector']
        assert pv['OVERRIDE_LOCKDOWN'] == 2

    def test_build_optimal_cs_rank2(self, apl, green_vlg_state, no_para_guard):
        """BUILD + OPTIMAL load: CS_CONFIDENCE_LOCK rank 2."""
        result = apl.resolve(green_vlg_state, no_para_guard, 'BUILD', 0.8)
        pv = result['priority_vector']
        assert pv['CS_CONFIDENCE_LOCK'] == 2

    def test_ranks_are_1_2_3_no_duplicates(self, apl, green_vlg_state, no_para_guard):
        """Every priority_vector must have exactly the values {1, 2, 3}."""
        for phase in ['BASE', 'BUILD', 'PEAK', 'TAPER', 'POST_RACE']:
            result = apl.resolve(green_vlg_state, no_para_guard, phase, 0.8)
            assert set(result['priority_vector'].values()) == {1, 2, 3}, (
                f'Ranks not {{1,2,3}} for phase={phase}: {result["priority_vector"]}'
            )


# ──────────────────────────────────────────────────────────────────────────────
# Adaptive threshold scaling
# ──────────────────────────────────────────────────────────────────────────────

class TestAdaptiveThresholds:
    """Verify threshold scaling per spec Section 5.3."""

    def test_peak_tightens_acwr_ceiling(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'PEAK', 0.8)
        assert result['lock_thresholds']['acwr_ceiling'] == pytest.approx(1.10)

    def test_peak_raises_tsb_floor(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'PEAK', 0.8)
        assert result['lock_thresholds']['tsb_floor'] == pytest.approx(-20.0)

    def test_peak_raises_cs_confidence(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'PEAK', 0.8)
        assert result['lock_thresholds']['cs_min_confidence'] == pytest.approx(0.85)

    def test_taper_acwr_ceiling(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'TAPER', 0.8)
        assert result['lock_thresholds']['acwr_ceiling'] == pytest.approx(1.25)

    def test_base_uses_default_thresholds(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'BASE', 0.8)
        lt = result['lock_thresholds']
        assert lt['acwr_ceiling'] == pytest.approx(VO2_ACWR_MAX)
        assert lt['tsb_floor'] == pytest.approx(HARD_STOP_TSB_FLOOR)
        assert lt['cs_min_confidence'] == pytest.approx(0.70)

    def test_very_low_cs_confidence_raises_cs_threshold(self, apl, green_vlg_state, no_para_guard):
        """cs_confidence < 0.5 should push cs_min_confidence to at least 0.85."""
        result = apl.resolve(green_vlg_state, no_para_guard, 'BASE', cs_confidence=0.3)
        assert result['lock_thresholds']['cs_min_confidence'] >= 0.85

    def test_thresholds_are_floats(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'BUILD', 0.8)
        for k, v in result['lock_thresholds'].items():
            assert isinstance(v, float), f'{k} is not float: {type(v)}'


# ──────────────────────────────────────────────────────────────────────────────
# Statelesness
# ──────────────────────────────────────────────────────────────────────────────

class TestAPLStateless:
    """Same inputs must always produce the same outputs."""

    def test_deterministic_output(self, apl, green_vlg_state, no_para_guard):
        r1 = apl.resolve(green_vlg_state, no_para_guard, 'PEAK', 0.8)
        r2 = apl.resolve(green_vlg_state, no_para_guard, 'PEAK', 0.8)
        assert r1['priority_vector'] == r2['priority_vector']
        assert r1['lock_thresholds'] == r2['lock_thresholds']

    def test_multiple_calls_do_not_accumulate_state(self, apl, green_vlg_state,
                                                     red_vlg_state, no_para_guard):
        """Calling with red then green should not affect the green result."""
        apl.resolve(red_vlg_state, no_para_guard, 'BUILD', 0.4)
        result = apl.resolve(green_vlg_state, no_para_guard, 'BASE', 0.8)
        lt = result['lock_thresholds']
        assert lt['acwr_ceiling'] == pytest.approx(VO2_ACWR_MAX)


# ──────────────────────────────────────────────────────────────────────────────
# Unknown / edge-case inputs
# ──────────────────────────────────────────────────────────────────────────────

class TestAPLEdgeCases:

    def test_unknown_phase_defaults_gracefully(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'MYSTERY_PHASE', 0.8)
        pv = result['priority_vector']
        assert pv['PARASYMPATHETIC_GUARD'] == 1
        assert set(pv.values()) == {1, 2, 3}

    def test_empty_afi_constraints_does_not_raise(self, apl, green_vlg_state):
        result = apl.resolve(green_vlg_state, {}, 'BASE', 0.8)
        assert 'priority_vector' in result

    def test_none_afi_constraints_does_not_raise(self, apl, green_vlg_state):
        result = apl.resolve(green_vlg_state, None, 'BASE', 0.8)
        assert 'priority_vector' in result

    def test_invalid_cs_confidence_does_not_raise(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'BASE', 'NOT_A_FLOAT')
        assert 'lock_thresholds' in result

    def test_cs_confidence_zero(self, apl, green_vlg_state, no_para_guard):
        result = apl.resolve(green_vlg_state, no_para_guard, 'BASE', 0.0)
        assert result['lock_thresholds']['cs_min_confidence'] >= 0.85


# ──────────────────────────────────────────────────────────────────────────────
# OutcomeTracker
# ──────────────────────────────────────────────────────────────────────────────

class TestOutcomeTracker:

    def test_record_and_retrieve_decision(self, tracker, dummy_apl_result):
        d = tracker.record_decision(
            session_planned='INTERVALS',
            session_post_governance='TEMPO',
            locks_applied=['VO2_ELIGIBILITY_GATE'],
            governance_clean=False,
            phase='BUILD',
            vlg_color='GREEN',
            apl_result=dummy_apl_result,
            acwr=1.1,
            tsb_value=-15.0,
            readiness_score=70.0,
            glycogen_debt=2.0,
            afi_value=0.1,
            date='2026-03-01',
        )
        assert d.session_planned == 'INTERVALS'
        assert d.session_post_governance == 'TEMPO'
        assert d.date == '2026-03-01'
        assert d.governance_clean is False

    def test_record_outcome_matches_by_date(self, tracker, dummy_apl_result):
        tracker.record_decision(
            session_planned='EASY', session_post_governance='EASY',
            locks_applied=[], governance_clean=True,
            phase='BASE', vlg_color='GREEN',
            apl_result=dummy_apl_result,
            acwr=1.0, tsb_value=-5.0, readiness_score=80.0,
            glycogen_debt=1.0, date='2026-03-02',
        )
        found = tracker.record_outcome(
            date='2026-03-02', rpe=5, completed=True,
            actual_session_type='EASY',
        )
        assert found is True
        decisions = tracker.get_decisions(date='2026-03-02', with_outcomes_only=True)
        assert len(decisions) == 1
        assert decisions[0].outcome_rpe == 5
        assert decisions[0].outcome_completed is True

    def test_record_outcome_miss_returns_false(self, tracker):
        found = tracker.record_outcome(date='1999-01-01', rpe=5, completed=True)
        assert found is False

    def test_no_outcomes_calibration_summary(self, tracker, dummy_apl_result):
        tracker.record_decision(
            session_planned='EASY', session_post_governance='EASY',
            locks_applied=[], governance_clean=True,
            phase='BASE', vlg_color='GREEN',
            apl_result=dummy_apl_result,
            acwr=1.0, tsb_value=-5.0, readiness_score=80.0,
            glycogen_debt=1.0,
        )
        summary = tracker.get_calibration_summary()
        assert summary['status'] == 'NO_OUTCOMES_YET'
        assert summary['n_decisions'] == 1

    def test_calibration_summary_with_outcomes(self, tracker, dummy_apl_result):
        for i in range(5):
            date = f'2026-03-{i+1:02d}'
            tracker.record_decision(
                session_planned='EASY', session_post_governance='EASY',
                locks_applied=[], governance_clean=True,
                phase='BASE', vlg_color='GREEN',
                apl_result=dummy_apl_result,
                acwr=1.0, tsb_value=-5.0, readiness_score=80.0,
                glycogen_debt=1.0, date=date,
            )
            tracker.record_outcome(date=date, rpe=4, completed=True)
        summary = tracker.get_calibration_summary()
        assert summary['n_with_outcome'] == 5
        assert summary['completion_rate'] == 1.0
        assert summary['avg_rpe_when_completed'] == pytest.approx(4.0)


    def test_heuristic_promotion_candidates_require_confirmed_signal(self, tracker, dummy_apl_result):
        for i in range(6):
            date = f'2026-04-{i+1:02d}'
            tracker.record_decision(
                session_planned='INTERVALS', session_post_governance='TEMPO',
                locks_applied=['VO2_ELIGIBILITY_GATE'], governance_clean=False,
                phase='BUILD', vlg_color='YELLOW',
                apl_result=dummy_apl_result,
                acwr=1.2, tsb_value=-20.0, readiness_score=58.0,
                glycogen_debt=5.0, date=date,
            )
            tracker.record_outcome(date=date, rpe=7, completed=False)

        for i in range(6):
            date = f'2026-05-{i+1:02d}'
            tracker.record_decision(
                session_planned='INTERVALS', session_post_governance='INTERVALS',
                locks_applied=[], governance_clean=True,
                phase='BUILD', vlg_color='GREEN',
                apl_result=dummy_apl_result,
                acwr=1.05, tsb_value=-8.0, readiness_score=72.0,
                glycogen_debt=2.0, date=date,
            )
            tracker.record_outcome(date=date, rpe=5, completed=True)

        summary = tracker.get_calibration_summary()
        candidates = summary['heuristic_promotion_candidates']

        assert candidates
        assert candidates[0]['parameter'] == 'VO2_READINESS_MIN'
        assert candidates[0]['trigger_lock'] == 'VO2_ELIGIBILITY_GATE'


    def test_moderate_promotion_candidates_require_cross_profile_replication(self, tracker, dummy_apl_result):
        for i in range(8):
            date = f'2026-06-{i+1:02d}'
            tracker.record_decision(
                session_planned='INTERVALS', session_post_governance='TEMPO',
                locks_applied=['VO2_ELIGIBILITY_GATE'], governance_clean=False,
                phase='BUILD', vlg_color='YELLOW',
                apl_result=dummy_apl_result,
                acwr=1.2, tsb_value=-15.0, readiness_score=60.0,
                glycogen_debt=6.0, athlete_profile_id='ATHLETE_A', date=date,
            )
            tracker.record_outcome(date=date, rpe=8, completed=False)

        for i in range(8):
            date = f'2026-07-{i+1:02d}'
            tracker.record_decision(
                session_planned='INTERVALS', session_post_governance='TEMPO',
                locks_applied=['VO2_ELIGIBILITY_GATE'], governance_clean=False,
                phase='PEAK', vlg_color='YELLOW',
                apl_result=dummy_apl_result,
                acwr=1.18, tsb_value=-13.0, readiness_score=62.0,
                glycogen_debt=5.5, athlete_profile_id='ATHLETE_B', date=date,
            )
            tracker.record_outcome(date=date, rpe=8, completed=False)

        for i in range(20):
            date = f'2026-08-{i+1:02d}'
            tracker.record_decision(
                session_planned='INTERVALS', session_post_governance='INTERVALS',
                locks_applied=[], governance_clean=True,
                phase='BUILD', vlg_color='GREEN',
                apl_result=dummy_apl_result,
                acwr=1.0, tsb_value=-5.0, readiness_score=75.0,
                glycogen_debt=2.0, athlete_profile_id='ATHLETE_A', date=date,
            )
            tracker.record_outcome(date=date, rpe=5, completed=True)

        summary = tracker.get_calibration_summary()
        candidates = summary['moderate_promotion_candidates']

        assert candidates
        assert candidates[0]['parameter'] == 'VO2_GLYCOGEN_DEBT_MAX'
        assert candidates[0]['profile_replication_count'] == 2
        assert candidates[0]['phase_replication_count'] == 2

    def test_moderate_promotion_candidates_block_single_profile_signal(self, tracker, dummy_apl_result):
        for i in range(10):
            date = f'2026-09-{i+1:02d}'
            tracker.record_decision(
                session_planned='INTERVALS', session_post_governance='TEMPO',
                locks_applied=['VO2_ELIGIBILITY_GATE'], governance_clean=False,
                phase='BUILD', vlg_color='YELLOW',
                apl_result=dummy_apl_result,
                acwr=1.2, tsb_value=-16.0, readiness_score=58.0,
                glycogen_debt=6.5, athlete_profile_id='ATHLETE_A', date=date,
            )
            tracker.record_outcome(date=date, rpe=8, completed=False)

        for i in range(12):
            date = f'2026-10-{i+1:02d}'
            tracker.record_decision(
                session_planned='INTERVALS', session_post_governance='INTERVALS',
                locks_applied=[], governance_clean=True,
                phase='PEAK', vlg_color='GREEN',
                apl_result=dummy_apl_result,
                acwr=1.02, tsb_value=-4.0, readiness_score=76.0,
                glycogen_debt=2.0, athlete_profile_id='ATHLETE_A', date=date,
            )
            tracker.record_outcome(date=date, rpe=5, completed=True)

        summary = tracker.get_calibration_summary()
        assert summary['moderate_promotion_candidates'] == []

    def test_get_lock_rate_by_phase(self, tracker, dummy_apl_result):
        tracker.record_decision(
            'INTERVALS', 'TEMPO', ['VO2_ELIGIBILITY_GATE'], False,
            'BUILD', 'GREEN', dummy_apl_result,
            1.1, -15.0, 70.0, 2.0, date='2026-03-01',
        )
        tracker.record_decision(
            'EASY', 'EASY', [], True,
            'BUILD', 'GREEN', dummy_apl_result,
            1.0, -5.0, 80.0, 1.0, date='2026-03-02',
        )
        rates = tracker.get_lock_rate_by_phase()
        assert 'BUILD' in rates
        assert rates['BUILD'] == pytest.approx(0.5)

    def test_filter_by_phase(self, tracker, dummy_apl_result):
        tracker.record_decision(
            'EASY', 'EASY', [], True, 'PEAK', 'GREEN', dummy_apl_result,
            1.0, -5.0, 80.0, 1.0, date='2026-03-01',
        )
        tracker.record_decision(
            'EASY', 'EASY', [], True, 'BASE', 'GREEN', dummy_apl_result,
            1.0, -5.0, 80.0, 1.0, date='2026-03-02',
        )
        assert len(tracker.get_decisions(phase='PEAK')) == 1
        assert len(tracker.get_decisions(phase='BASE')) == 1


# ──────────────────────────────────────────────────────────────────────────────
# EvidenceRegistry
# ──────────────────────────────────────────────────────────────────────────────

class TestEvidenceRegistry:

    # Every threshold in thresholds.py should be in the registry.
    CANONICAL_PARAMETERS = {
        'HARD_STOP_HRV_DELTA', 'HARD_STOP_RHR_DELTA', 'HARD_STOP_TSB_FLOOR',
        'SUBJECTIVE_FATIGUE_EXTREME', 'SUBJECTIVE_FATIGUE_2OF4',
        'VO2_ACWR_MIN', 'VO2_ACWR_MAX', 'VO2_READINESS_MIN',
        'VO2_GLYCOGEN_DEBT_MAX', 'VO2_MIN_DAYS_SINCE_LAST',
    }

    def test_all_canonical_parameters_registered(self):
        missing = self.CANONICAL_PARAMETERS - set(EVIDENCE_REGISTRY.keys())
        assert not missing, f'Unregistered parameters: {missing}'

    def test_get_evidence_returns_record(self):
        record = get_evidence('HARD_STOP_HRV_DELTA')
        assert record is not None
        assert record.parameter == 'HARD_STOP_HRV_DELTA'

    def test_get_evidence_unknown_returns_none(self):
        assert get_evidence('NONEXISTENT_PARAM') is None

    def test_evidence_levels_are_valid(self):
        valid = {'STRONG', 'MODERATE', 'HEURISTIC'}
        for k, v in EVIDENCE_REGISTRY.items():
            assert v.evidence_level in valid, (
                f'{k} has invalid evidence_level: {v.evidence_level!r}'
            )

    def test_population_codes_are_valid(self):
        valid = {'ELITE', 'RECREATIONAL', 'MASTER', 'MIXED'}
        for k, v in EVIDENCE_REGISTRY.items():
            assert v.population in valid, (
                f'{k} has invalid population: {v.population!r}'
            )

    def test_registry_values_mirror_live_thresholds(self):
        """Registry values should match what's in thresholds.py."""
        live = {
            'HARD_STOP_HRV_DELTA': HARD_STOP_HRV_DELTA,
            'HARD_STOP_RHR_DELTA': HARD_STOP_RHR_DELTA,
            'HARD_STOP_TSB_FLOOR': HARD_STOP_TSB_FLOOR,
            'SUBJECTIVE_FATIGUE_EXTREME': float(SUBJECTIVE_FATIGUE_EXTREME),
            'SUBJECTIVE_FATIGUE_2OF4': float(SUBJECTIVE_FATIGUE_2OF4),
            'VO2_ACWR_MIN': VO2_ACWR_MIN,
            'VO2_ACWR_MAX': VO2_ACWR_MAX,
            'VO2_READINESS_MIN': VO2_READINESS_MIN,
            'VO2_GLYCOGEN_DEBT_MAX': VO2_GLYCOGEN_DEBT_MAX,
            'VO2_MIN_DAYS_SINCE_LAST': float(VO2_MIN_DAYS_SINCE_LAST),
        }
        for param, expected in live.items():
            record = get_evidence(param)
            assert record is not None
            assert record.value == pytest.approx(expected), (
                f'{param} registry value {record.value} != live threshold {expected}'
            )

    def test_policy_parameters_are_heuristic(self):
        for param in get_policy_parameters():
            record = get_evidence(param)
            assert record.evidence_level == 'HEURISTIC'

    def test_calibration_candidates_non_empty(self):
        candidates = get_calibration_candidates()
        assert len(candidates) > 0

    def test_registry_summary_structure(self):
        summary = get_registry_summary()
        assert 'total_parameters' in summary
        assert 'by_evidence_level' in summary
        assert 'promoted_parameters' in summary
        assert summary['total_parameters'] == len(EVIDENCE_REGISTRY)

    def test_promotion_metadata_is_consistent(self):
        for k, v in EVIDENCE_REGISTRY.items():
            if v.promoted_from_level is None:
                assert v.promotion_evidence_count is None, (
                    f'{k} has promotion_evidence_count without promoted_from_level'
                )
                assert v.promotion_date is None, (
                    f'{k} has promotion_date without promoted_from_level'
                )
                continue

            assert v.promoted_from_level in {'HEURISTIC', 'MODERATE'}, (
                f'{k} has invalid promoted_from_level: {v.promoted_from_level!r}'
            )
            assert isinstance(v.promotion_evidence_count, int)
            assert v.promotion_evidence_count > 0
            assert isinstance(v.promotion_date, str)
            assert len(v.promotion_date) == 10

    def test_vo2_min_days_is_strong_evidence(self):
        record = get_evidence('VO2_MIN_DAYS_SINCE_LAST')
        assert record.evidence_level == 'STRONG'

    def test_readiness_min_is_heuristic(self):
        """VO2_READINESS_MIN is an internal composite — correctly HEURISTIC."""
        record = get_evidence('VO2_READINESS_MIN')
        assert record.evidence_level == 'HEURISTIC'

    def test_every_record_has_non_empty_rationale(self):
        for k, v in EVIDENCE_REGISTRY.items():
            assert v.rationale.strip(), f'{k} has empty rationale'
            assert v.source.strip(), f'{k} has empty source'

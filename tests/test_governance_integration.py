"""
Integration tests: governance output contract + orchestration boundary.

These tests verify:
1. Governance output contracts — every vo2_eligibility dict produced by
   GovernanceEngine satisfies Vo2EligibilityContract (shape + invariants).
2. Backward-compatibility — the coaching_data keys consumed by DailyCoach /
   Telegram remain stable across any governance path.
3. Gate ordering — contract is always satisfied regardless of gate execution path.
"""

import pytest

from titan.science.governance_contracts import (
    ContractViolation,
    assert_vo2_eligibility_contract,
    validate_vo2_eligibility,
)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def gov(governance_engine_factory):
    return governance_engine_factory()


def _vo2_context(**overrides):
    """Return a minimal valid VO2 context, with optional overrides."""
    base = {
        'acwr': 1.1,
        'readiness_score': 72,
        'glycogen_debt': 3.0,
        'fatigue_level': 'LOW',
        'days_since_last_vo2': 3,
        'fueling_confirmed': True,
        # T5-49: conservative defaults (40) fire I2_sleep; supply healthy value so
        # VO2-focused tests are not disrupted by the 2-of-4 downgrade gate.
        'sleep_score': 80,
    }
    base.update(overrides)
    return base


# ─────────────────────────────────────────────────────────────────────────────
# Contract shape tests — every governance path must satisfy the contract
# ─────────────────────────────────────────────────────────────────────────────

class TestVo2EligibilityContract:
    """Assert that assert_vo2_eligibility_contract() catches shape violations."""

    def test_valid_eligible_result_passes(self):
        result = {
            'eligible': True,
            'failed_conditions': [],
            'original_session': 'HAMMER',
            'downgraded_to': None,
            'detailed_failed_conditions': [],
            'reason': 'All VO2 eligibility conditions satisfied',
        }
        assert_vo2_eligibility_contract(result)  # must not raise

    def test_valid_ineligible_result_passes(self):
        result = {
            'eligible': False,
            'failed_conditions': ['V1'],
            'original_session': 'HAMMER',
            'downgraded_to': 'TEMPO',
            'detailed_failed_conditions': [
                {'code': 'V1', 'metric': 'acwr', 'operator': 'between',
                 'min': 0.8, 'max': 1.3, 'actual': 1.5}
            ],
            'reason': 'VO2max session requires: ACWR in [0.8,1.3]',
        }
        assert_vo2_eligibility_contract(result)  # must not raise

    def test_missing_key_raises(self):
        result = {
            'eligible': True,
            'failed_conditions': [],
            # 'original_session' is missing
            'downgraded_to': None,
            'detailed_failed_conditions': [],
            'reason': 'ok',
        }
        with pytest.raises(ContractViolation, match='original_session'):
            assert_vo2_eligibility_contract(result)

    def test_eligible_true_with_failed_conditions_raises(self):
        result = {
            'eligible': True,
            'failed_conditions': ['V1'],
            'original_session': 'HAMMER',
            'downgraded_to': None,
            'detailed_failed_conditions': [
                {'code': 'V1', 'metric': 'acwr', 'operator': 'between',
                 'min': 0.8, 'max': 1.3, 'actual': 1.5}
            ],
            'reason': 'bad',
        }
        with pytest.raises(ContractViolation, match='eligible=True'):
            assert_vo2_eligibility_contract(result)

    def test_eligible_false_empty_failed_raises(self):
        result = {
            'eligible': False,
            'failed_conditions': [],
            'original_session': 'HAMMER',
            'downgraded_to': 'TEMPO',
            'detailed_failed_conditions': [],
            'reason': 'bad',
        }
        with pytest.raises(ContractViolation, match='eligible=False'):
            assert_vo2_eligibility_contract(result)

    def test_eligible_true_downgraded_to_set_raises(self):
        result = {
            'eligible': True,
            'failed_conditions': [],
            'original_session': 'HAMMER',
            'downgraded_to': 'TEMPO',
            'detailed_failed_conditions': [],
            'reason': 'bad',
        }
        with pytest.raises(ContractViolation, match='downgraded_to'):
            assert_vo2_eligibility_contract(result)

    def test_unknown_failure_code_raises(self):
        result = {
            'eligible': False,
            'failed_conditions': ['X9'],
            'original_session': 'HAMMER',
            'downgraded_to': 'TEMPO',
            'detailed_failed_conditions': [
                {'code': 'X9', 'metric': 'acwr', 'operator': 'between', 'actual': 1.5}
            ],
            'reason': 'bad',
        }
        with pytest.raises(ContractViolation, match="X9"):
            assert_vo2_eligibility_contract(result)

    def test_validate_returns_none_on_success(self):
        result = {
            'eligible': True,
            'failed_conditions': [],
            'original_session': 'HAMMER',
            'downgraded_to': None,
            'detailed_failed_conditions': [],
            'reason': 'ok',
        }
        assert validate_vo2_eligibility(result) is None

    def test_validate_returns_string_on_violation(self):
        result = {
            'eligible': True,
            'failed_conditions': ['V1'],  # invariant violation
            'original_session': 'HAMMER',
            'downgraded_to': None,
            'detailed_failed_conditions': [
                {'code': 'V1', 'metric': 'acwr', 'operator': 'between', 'actual': 1.5}
            ],
            'reason': 'bad',
        }
        error = validate_vo2_eligibility(result)
        assert error is not None
        assert 'eligible=True' in error

    def test_validate_none_input_returns_none(self):
        assert validate_vo2_eligibility(None) is None

    def test_validate_non_dict_input_returns_contract_error(self):
        error = validate_vo2_eligibility(123)  # type: ignore[arg-type]
        assert error is not None
        assert "must be dict" in error

    def test_invalid_detail_operator_raises(self):
        result = {
            'eligible': False,
            'failed_conditions': ['V1'],
            'original_session': 'HAMMER',
            'downgraded_to': 'TEMPO',
            'detailed_failed_conditions': [
                {'code': 'V1', 'metric': 'acwr', 'operator': 'invalid_op', 'actual': 1.5}
            ],
            'reason': 'bad',
        }
        with pytest.raises(ContractViolation, match='operator'):
            assert_vo2_eligibility_contract(result)


# ─────────────────────────────────────────────────────────────────────────────
# Integration contract tests — GovernanceEngine must always produce
# contract-valid vo2_eligibility dicts
# ─────────────────────────────────────────────────────────────────────────────

class TestGovernanceOutputContract:
    """Every governance path must satisfy the Vo2EligibilityContract."""

    def _assert_contract(self, result):
        vo2 = result.get('vo2_eligibility')
        if vo2 is not None:
            assert_vo2_eligibility_contract(vo2)

    def test_contract_on_eligible_path(self, gov):
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        result = gov.apply_constraints(plan, _vo2_context())
        self._assert_contract(result)
        assert result['vo2_eligibility']['eligible'] is True

    def test_contract_on_v1_fail_path(self, gov):
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        result = gov.apply_constraints(plan, _vo2_context(acwr=0.5))
        self._assert_contract(result)
        assert 'V1' in result['vo2_eligibility']['failed_conditions']

    def test_contract_on_v2_fail_path(self, gov):
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        result = gov.apply_constraints(plan, _vo2_context(readiness_score=40))
        self._assert_contract(result)
        assert 'V2' in result['vo2_eligibility']['failed_conditions']

    def test_contract_on_v3_fail_path(self, gov):
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        result = gov.apply_constraints(plan, _vo2_context(glycogen_debt=9.0))
        self._assert_contract(result)
        assert 'V3' in result['vo2_eligibility']['failed_conditions']

    def test_contract_on_v4_fail_path(self, gov):
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        result = gov.apply_constraints(plan, _vo2_context(fatigue_level='HIGH'))
        self._assert_contract(result)
        assert 'V4' in result['vo2_eligibility']['failed_conditions']

    def test_contract_on_v5_fail_path(self, gov):
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        result = gov.apply_constraints(plan, _vo2_context(days_since_last_vo2=1))
        self._assert_contract(result)
        assert 'V5' in result['vo2_eligibility']['failed_conditions']

    def test_contract_on_all_fail_path(self, gov):
        plan = {'session_type': 'INTERVALS', 'zone': 5, 'duration_min': 45}
        result = gov.apply_constraints(plan, {
            'acwr': 'bad',
            'readiness_score': 'bad',
            'glycogen_debt': 'bad',
            'fatigue_level': 'bad',
            'days_since_last_vo2': 'bad',
            'fueling_confirmed': True,
            # T5-49: supply healthy sleep so only VO2 conditions fail (not 2-of-4 gate).
            'sleep_score': 80,
        })
        self._assert_contract(result)
        assert result['vo2_eligibility']['failed_conditions'] == ['V1', 'V2', 'V3', 'V4', 'V5']

    def test_contract_on_invalid_numeric_path(self, gov):
        plan = {'session_type': 'RACE', 'duration_min': 90}
        result = gov.apply_constraints(plan, _vo2_context(acwr=None, readiness_score=None))
        # None inputs: acwr/readiness_score treated as missing → conservative fail (V1+V2)
        self._assert_contract(result)
        assert result['vo2_eligibility']['eligible'] is False
        assert 'V1' in result['vo2_eligibility']['failed_conditions']
        assert 'V2' in result['vo2_eligibility']['failed_conditions']

    def test_contract_on_non_numeric_zone_denies_and_downgrades(self, gov):
        plan = {'session_type': 'INTERVALS', 'zone': 'bad-zone', 'duration_min': 45}
        result = gov.apply_constraints(plan, _vo2_context())

        self._assert_contract(result)
        assert result['session_type'] == 'TEMPO'
        assert result['vo2_eligibility']['eligible'] is False
        assert result['vo2_eligibility']['original_session'] == 'INTERVALS_Z5'
        assert result['vo2_eligibility']['downgraded_to'] == 'TEMPO'

    def test_non_numeric_duration_min_applies_fueling_lock_fallback(self, gov):
        plan = {'session_type': 'RACE', 'duration_min': 'ninety'}
        # T5-49: supply healthy sleep/readiness so only the fueling gate fires.
        # T5-63: supply acwr so VO2 eligibility gate (OBS-028 fix) does not fire.
        result = gov.apply_constraints(plan, {'fueling_confirmed': False, 'sleep_score': 80, 'readiness_score': 70, 'acwr': 1.1})

        assert result['session_type'] == 'TEMPO'
        assert result['fueling_gate']['action'] == 'LOCK'
        assert result['fueling_gate']['phase'] == 3

    def test_no_contract_check_for_non_vo2_session(self, gov):
        plan = {'session_type': 'TEMPO', 'duration_min': 60}
        result = gov.apply_constraints(plan, _vo2_context())
        assert 'vo2_eligibility' not in result


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compatibility: coaching_data keys consumed by orchestration
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestrationBoundaryBackwardCompat:
    """
    Ensure that coaching_data keys used by DailyCoach remain stable.

    DailyCoach passes these keys to Telegram from today_session (post-governance):
      - governance_locks_applied  (list)
      - governance_clean          (bool)
      - vo2_eligibility           (dict | absent)
      - fueling_gate              (dict | absent)
      - intensity_gate_result     (dict | absent)
    """

    REQUIRED_ALWAYS = ('governance_locks_applied', 'governance_clean')

    def test_required_keys_always_present(self, gov):
        plan = {'session_type': 'EASY', 'duration_min': 45}
        result = gov.apply_constraints(plan, context={})
        for key in self.REQUIRED_ALWAYS:
            assert key in result, f'Missing required coaching_data key: {key!r}'

    def test_governance_locks_applied_is_list(self, gov):
        plan = {'session_type': 'EASY', 'duration_min': 45}
        result = gov.apply_constraints(plan, context={})
        assert isinstance(result['governance_locks_applied'], list)

    def test_governance_clean_is_bool(self, gov):
        plan = {'session_type': 'EASY', 'duration_min': 45}
        result = gov.apply_constraints(plan, context={})
        assert isinstance(result['governance_clean'], bool)

    def test_governance_clean_true_means_no_locks(self, gov):
        plan = {'session_type': 'EASY', 'duration_min': 45}
        result = gov.apply_constraints(plan, context={'fueling_confirmed': True})
        assert result['governance_clean'] is (len(result['governance_locks_applied']) == 0)

    def test_vo2_eligibility_when_present_is_dict(self, gov):
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        result = gov.apply_constraints(plan, _vo2_context())
        assert isinstance(result['vo2_eligibility'], dict)

    def test_fueling_gate_when_present_has_action(self, gov):
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        result = gov.apply_constraints(plan, _vo2_context(fueling_confirmed=False))
        if 'fueling_gate' in result:
            assert 'action' in result['fueling_gate']

    def test_locks_applied_contains_only_known_codes(self, gov):
        """All lock codes must be from the canonical set."""
        known_codes = {
            'INTENSITY_GATE_RED', 'INTENSITY_GATE_YELLOW',
            'READINESS_2OF4_DOWNGRADE', 'HARD_STOP_SAFETY_GATES',
            'VO2_ELIGIBILITY_GATE', 'FUELING_GATE_LOCK', 'FUELING_GATE_FLAG',
            'PARASYMPATHETIC_GUARD', 'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
            'STARTUP_DATA_CONFIDENCE_CEILING',
        }
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        contexts = [
            _vo2_context(acwr=0.5),
            _vo2_context(fueling_confirmed=False),
            _vo2_context(fatigue_level='HIGH'),
        ]
        for ctx in contexts:
            result = gov.apply_constraints(plan.copy(), ctx)
            for lock in result['governance_locks_applied']:
                assert lock in known_codes, f'Unknown lock code: {lock!r}'

    def test_vo2_eligibility_six_field_shape_stable(self, gov):
        """vo2_eligibility always exposes exactly the 6 canonical fields."""
        expected_keys = {
            'eligible', 'failed_conditions', 'original_session',
            'downgraded_to', 'detailed_failed_conditions', 'reason',
        }
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        for ctx in [_vo2_context(), _vo2_context(acwr=0.1), _vo2_context(fatigue_level='HIGH')]:
            result = gov.apply_constraints(plan.copy(), ctx)
            vo2 = result['vo2_eligibility']
            assert set(vo2.keys()) >= expected_keys, (
                f'vo2_eligibility missing fields: {expected_keys - set(vo2.keys())}'
            )


class _StubDB:
    def get_override_ratio(self, days=14):
        return 0.95


class _StubCsTracker:
    confidence = 0.40


class TestAdaptivePriorityOrder:
    """APL priority_vector should control relative ordering for override vs CS lock."""

    def test_default_order_keeps_override_before_cs(self, gov):
        plan = {'session_type': 'RACE', 'duration_min': 30}
        context = {
            'db': _StubDB(),
            'cs_tracker': _StubCsTracker(),
            'afi_constraints': {'parasympathetic_guard': {'triggered': False}},
        }
        result = gov.apply_constraints(plan, context)
        assert result['governance_locks_applied'].index('OVERRIDE_LOCKDOWN') < \
            result['governance_locks_applied'].index('CS_CONFIDENCE_LOCK')

    def test_priority_vector_can_promote_cs_before_override(self, gov):
        plan = {'session_type': 'RACE', 'duration_min': 30}
        context = {
            'db': _StubDB(),
            'cs_tracker': _StubCsTracker(),
            'afi_constraints': {'parasympathetic_guard': {'triggered': False}},
            'priority_vector': {
                'PARASYMPATHETIC_GUARD': 1,
                'CS_CONFIDENCE_LOCK': 2,
                'OVERRIDE_LOCKDOWN': 3,
            },
        }
        result = gov.apply_constraints(plan, context)
        assert result['governance_locks_applied'].index('CS_CONFIDENCE_LOCK') < \
            result['governance_locks_applied'].index('OVERRIDE_LOCKDOWN')


def test_startup_data_confidence_low_applies_easy_ceiling(gov):
    plan = {'session_type': 'HAMMER', 'duration_min': 45, 'max_zone': 5}
    result = gov.apply_constraints(plan, {'data_confidence_low': True})

    assert result['session_type'] == 'EASY'
    assert result['max_zone'] <= 2
    assert 'STARTUP_DATA_CONFIDENCE_CEILING' in result['governance_locks_applied']


def test_startup_data_confidence_false_does_not_apply_easy_ceiling(gov):
    plan = {'session_type': 'HAMMER', 'duration_min': 45, 'max_zone': 5}
    result = gov.apply_constraints(plan, {'data_confidence_low': False, 'fueling_confirmed': True, 'days_since_last_vo2': 3, 'acwr': 1.1, 'readiness_score': 72, 'glycogen_debt': 3.0, 'fatigue_level': 'LOW'})

    assert result['session_type'] == 'HAMMER'
    assert 'STARTUP_DATA_CONFIDENCE_CEILING' not in result['governance_locks_applied']


# ─────────────────────────────────────────────────────────────────────────────
# OBS-028 / T5-63: missing-data policy — acwr=None and readiness_score=None
# must produce conservative (ineligible) gate outcome, never optimistic default
# ─────────────────────────────────────────────────────────────────────────────

class TestVo2EligibilityMissingDataPolicy:
    """acwr=None and readiness_score=None must each trigger a conservative fail."""

    def test_acwr_none_in_context_triggers_v1_fail(self, gov):
        """Explicit None for acwr (key present, value None) → V1 ineligible."""
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        ctx = _vo2_context(acwr=None)
        result = gov.apply_constraints(plan, ctx)
        vo2 = result['vo2_eligibility']
        assert vo2['eligible'] is False, "acwr=None must not be treated as safe default 1.0"
        assert 'V1' in vo2['failed_conditions']
        assert 'VO2_ELIGIBILITY_GATE' in result['governance_locks_applied']

    def test_acwr_absent_from_context_triggers_v1_fail(self, gov):
        """Absent acwr key (not present in context at all) → V1 ineligible."""
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        ctx = {k: v for k, v in _vo2_context().items() if k != 'acwr'}
        result = gov.apply_constraints(plan, ctx)
        vo2 = result['vo2_eligibility']
        assert vo2['eligible'] is False, "absent acwr must not be treated as safe default 1.0"
        assert 'V1' in vo2['failed_conditions']
        assert 'VO2_ELIGIBILITY_GATE' in result['governance_locks_applied']

    def test_readiness_score_none_in_context_triggers_v2_fail(self, gov):
        """Explicit None for readiness_score (key present, value None) → V2 ineligible."""
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        ctx = _vo2_context(readiness_score=None)
        result = gov.apply_constraints(plan, ctx)
        vo2 = result['vo2_eligibility']
        assert vo2['eligible'] is False, "readiness_score=None must not be treated as safe default 100"
        assert 'V2' in vo2['failed_conditions']
        assert 'VO2_ELIGIBILITY_GATE' in result['governance_locks_applied']

    def test_readiness_score_absent_from_context_triggers_v2_fail(self, gov):
        """Absent readiness_score key (not present in context at all) → V2 ineligible."""
        plan = {'session_type': 'HAMMER', 'duration_min': 45}
        ctx = {k: v for k, v in _vo2_context().items() if k != 'readiness_score'}
        result = gov.apply_constraints(plan, ctx)
        vo2 = result['vo2_eligibility']
        assert vo2['eligible'] is False, "absent readiness_score must not be treated as safe default 100"
        assert 'V2' in vo2['failed_conditions']
        assert 'VO2_ELIGIBILITY_GATE' in result['governance_locks_applied']

    def test_both_none_triggers_v1_and_v2_fail(self, gov):
        """Both acwr=None and readiness_score=None → V1 + V2 ineligible (contract-valid)."""
        plan = {'session_type': 'RACE', 'duration_min': 90}
        ctx = _vo2_context(acwr=None, readiness_score=None)
        result = gov.apply_constraints(plan, ctx)
        vo2 = result['vo2_eligibility']
        assert vo2['eligible'] is False
        assert 'V1' in vo2['failed_conditions']
        assert 'V2' in vo2['failed_conditions']
        # Downgrade must be applied
        assert result['session_type'] == 'TEMPO'

"""Mirrored test for titan/science/governance_contracts.py — T5-79."""
from __future__ import annotations

import pytest

from titan.science.governance_contracts import (
    ContractViolation,
    assert_vo2_eligibility_contract,
    validate_vo2_eligibility,
)


def _valid_eligible() -> dict:
    return {
        "eligible": True,
        "failed_conditions": [],
        "original_session": "VO2MAX",
        "downgraded_to": None,
        "detailed_failed_conditions": [],
        "reason": "All gates passed.",
    }


@pytest.mark.unit
def test_module_imports_without_error() -> None:
    import titan.science.governance_contracts  # noqa: F401


@pytest.mark.unit
def test_assert_contract_valid_eligible_passes() -> None:
    assert_vo2_eligibility_contract(_valid_eligible())


@pytest.mark.unit
def test_validate_returns_none_on_valid() -> None:
    assert validate_vo2_eligibility(_valid_eligible()) is None


@pytest.mark.unit
def test_validate_returns_none_when_input_is_none() -> None:
    assert validate_vo2_eligibility(None) is None


@pytest.mark.unit
def test_assert_contract_missing_key_raises_contract_violation() -> None:
    bad = _valid_eligible()
    del bad["reason"]
    with pytest.raises(ContractViolation):
        assert_vo2_eligibility_contract(bad)


@pytest.mark.unit
def test_validate_returns_error_string_on_violation() -> None:
    bad = _valid_eligible()
    del bad["eligible"]
    err = validate_vo2_eligibility(bad)
    assert isinstance(err, str)

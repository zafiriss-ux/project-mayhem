"""
Governance output contracts — shape guards for cross-boundary dict validation.

These contracts enforce that governance outputs have a stable, predictable shape
before being consumed by orchestration (DailyCoach) and downstream (Telegram payload).
"""

from typing import Any

MODULE_VERSION = "1.0.0"

# ─────────────────────────────────────────────────────────────────────────────
# Contract: vo2_eligibility
# ─────────────────────────────────────────────────────────────────────────────

_VO2_REQUIRED_KEYS: list[str] = [
    "eligible",
    "failed_conditions",
    "original_session",
    "downgraded_to",
    "detailed_failed_conditions",
    "reason",
]

_VALID_FAILURE_CODES = frozenset({"V1", "V2", "V3", "V4", "V5"})
_VALID_DETAIL_OPERATORS = frozenset({"numeric", "between", ">=", "<", "!=", "in"})


class ContractViolation(ValueError):
    """Raised when a governance output violates its declared contract."""


def assert_vo2_eligibility_contract(result: dict[str, Any]) -> None:
    """
    Assert that a vo2_eligibility dict satisfies the governance output contract.

    Checks:
    - All required keys are present with correct types
    - Structural invariants (eligible ↔ failed_conditions, downgraded_to)
    - All failure codes are from the canonical set {V1..V5}
    - detailed_failed_conditions entries each have a 'code' and 'metric'

    Raises ContractViolation on any violation.
    """
    if not isinstance(result, dict):
        raise ContractViolation(
            f"vo2_eligibility result must be dict, got {type(result).__name__}"
        )

    missing = [k for k in _VO2_REQUIRED_KEYS if k not in result]
    if missing:
        raise ContractViolation(f"vo2_eligibility missing required keys: {missing}")

    if not isinstance(result["eligible"], bool):
        raise ContractViolation(
            f"vo2_eligibility['eligible'] must be bool, got {type(result['eligible']).__name__}"
        )
    if not isinstance(result["failed_conditions"], list):
        raise ContractViolation(
            f"vo2_eligibility['failed_conditions'] must be list, got {type(result['failed_conditions']).__name__}"
        )
    if not isinstance(result["original_session"], str):
        raise ContractViolation(
            f"vo2_eligibility['original_session'] must be str, got {type(result['original_session']).__name__}"
        )
    if result["downgraded_to"] is not None and not isinstance(result["downgraded_to"], str):
        raise ContractViolation(
            f"vo2_eligibility['downgraded_to'] must be str or None, got {type(result['downgraded_to']).__name__}"
        )
    if not isinstance(result["detailed_failed_conditions"], list):
        raise ContractViolation(
            f"vo2_eligibility['detailed_failed_conditions'] must be list, "
            f"got {type(result['detailed_failed_conditions']).__name__}"
        )
    if not isinstance(result["reason"], str):
        raise ContractViolation(
            f"vo2_eligibility['reason'] must be str, got {type(result['reason']).__name__}"
        )

    # Structural invariants
    if result["eligible"] and result["failed_conditions"]:
        raise ContractViolation("eligible=True but failed_conditions is non-empty")
    if not result["eligible"] and not result["failed_conditions"]:
        raise ContractViolation("eligible=False but failed_conditions is empty")
    if result["eligible"] and result["downgraded_to"] is not None:
        raise ContractViolation("eligible=True but downgraded_to is set")
    if not result["eligible"] and result["downgraded_to"] is None:
        raise ContractViolation("eligible=False but downgraded_to is None")

    # Failure code validity
    for code in result["failed_conditions"]:
        if code not in _VALID_FAILURE_CODES:
            raise ContractViolation(f"Unknown failure code {code!r} in failed_conditions")

    # detailed_failed_conditions structure
    for i, detail in enumerate(result["detailed_failed_conditions"]):
        if not isinstance(detail, dict):
            raise ContractViolation(
                f"detailed_failed_conditions[{i}] must be dict, got {type(detail).__name__}"
            )
        for required_field in ("code", "metric", "operator"):
            if required_field not in detail:
                raise ContractViolation(
                    f"detailed_failed_conditions[{i}] missing required field {required_field!r}"
                )
        if detail["code"] not in _VALID_FAILURE_CODES:
            raise ContractViolation(
                f"detailed_failed_conditions[{i}] has unknown code {detail['code']!r}"
            )
        if detail["operator"] not in _VALID_DETAIL_OPERATORS:
            raise ContractViolation(
                f"detailed_failed_conditions[{i}] has invalid operator {detail['operator']!r}"
            )

    # failed_conditions and detailed_failed_conditions must agree
    detail_codes = [d["code"] for d in result["detailed_failed_conditions"]]
    if result["failed_conditions"] != detail_codes:
        raise ContractViolation(
            f"failed_conditions {result['failed_conditions']} does not match "
            f"codes in detailed_failed_conditions {detail_codes}"
        )


def validate_vo2_eligibility(result: dict[str, Any] | None) -> str | None:
    """
    Validate a vo2_eligibility dict against the contract.

    Returns None on success, or an error description string on violation.
    Does not raise — safe to call in production paths.
    """
    if result is None:
        return None
    try:
        assert_vo2_eligibility_contract(result)
    except ContractViolation as exc:
        return str(exc)
    else:
        return None

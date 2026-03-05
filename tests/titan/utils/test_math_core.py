"""Behavior invariants for titan.utils.math_core."""

from titan.utils.math_core import MathCore


def test_format_pace_returns_na_for_non_positive_inputs() -> None:
    """Invariant: non-positive pace is clamped to N/A."""
    assert MathCore.format_pace(0) == "N/A"
    assert MathCore.format_pace(-5) == "N/A"


def test_weight_function_from_profile_uses_default_target_when_none() -> None:
    """Invariant: None target_weight falls back to 75.0 for threshold evaluation."""
    status = MathCore.weight_function_from_profile(
        weight=74.4,
        night_drop=0.2,
        epoc=100,
        target_weight=None,
    )

    assert status == "AGGRESSIVE_CORRECTION"


def test_weight_function_from_profile_emergency_mode_between_thresholds() -> None:
    """Invariant: weight below target but above critical threshold maps to EMERGENCY_MODE."""
    status = MathCore.weight_function_from_profile(
        weight=74.8,
        night_drop=0.2,
        epoc=100,
        target_weight=75.0,
        critical_margin=0.5,
    )

    assert status == "EMERGENCY_MODE"


def test_weight_function_from_profile_night_drop_alert_overrides_safe_zone() -> None:
    """Invariant: night drop above threshold triggers NIGHT_DROP_ALERT."""
    status = MathCore.weight_function_from_profile(
        weight=75.0,
        night_drop=1.21,
        epoc=100,
        target_weight=75.0,
    )

    assert status == "NIGHT_DROP_ALERT"


def test_weight_function_from_profile_epoc_override_when_drop_is_safe() -> None:
    """Invariant: EPOC > 350 triggers EPOC_OVERRIDE when higher-priority checks are clear."""
    status = MathCore.weight_function_from_profile(
        weight=75.0,
        night_drop=1.0,
        epoc=351,
        target_weight=75.0,
    )

    assert status == "EPOC_OVERRIDE"


def test_weight_function_from_profile_safe_drop_rule_at_upper_boundary() -> None:
    """Invariant: weight at target + 0.5 remains clamped to SAFE_DROP_RULE."""
    status = MathCore.weight_function_from_profile(
        weight=75.5,
        night_drop=0.5,
        epoc=300,
        target_weight=75.0,
    )

    assert status == "SAFE_DROP_RULE"

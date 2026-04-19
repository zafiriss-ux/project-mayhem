"""Mirrored test for titan/science/ml_safety.py — T5-79."""
from __future__ import annotations

import pytest

from titan.science.ml_safety import (
    ExplainableOutput,
    enforce_ml_kill_switch,
    is_ml_kill_switch_enabled,
)


def test_module_imports_without_error() -> None:
    import titan.science.ml_safety  # noqa: F401


def test_kill_switch_enabled_by_default() -> None:
    assert is_ml_kill_switch_enabled() is True


def test_kill_switch_disabled_when_env_is_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TITAN_ML_KILL_SWITCH", "0")
    assert is_ml_kill_switch_enabled() is False


def test_enforce_raises_when_athlete_facing_and_enabled() -> None:
    with pytest.raises(RuntimeError, match="kill-switch"):
        enforce_ml_kill_switch("test_path", athlete_facing=True)


def test_enforce_passes_when_not_athlete_facing() -> None:
    enforce_ml_kill_switch("test_path", athlete_facing=False)


def test_explainable_output_instantiation() -> None:
    output = ExplainableOutput(
        top_feature_contributions=(("hrv", 0.5), ("tsb", 0.3), ("rhr", 0.2)),
        confidence_range=(0.7, 0.9),
        plain_text_reason="HRV is the primary driver.",
        data_freshness_ok=True,
    )
    assert output.data_freshness_ok is True
    assert output.confidence_range == (0.7, 0.9)

"""T5-37/T5-38 Migration Unit 1: Pattern 1 gate + validating meta-test."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from titan.config.thresholds import (
    HARD_STOP_HRV_DELTA,
    HARD_STOP_RHR_DELTA,
    HARD_STOP_TSB_FLOOR,
    SUBJECTIVE_FATIGUE_EXTREME,
)


def _threshold_sentinel_values() -> set[float]:
    return {
        float(HARD_STOP_HRV_DELTA),
        float(HARD_STOP_RHR_DELTA),
        float(HARD_STOP_TSB_FLOOR),
        float(SUBJECTIVE_FATIGUE_EXTREME),
    }


def _assert_no_inline_threshold_literals(module_source: str, module_label: str) -> None:
    """Fail when governed threshold values appear inline as numeric literals."""
    sentinel_values = _threshold_sentinel_values()
    tree = ast.parse(module_source)
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float):
            literal_value = float(node.value)
            if literal_value in sentinel_values:
                violations.append(f"Line {node.lineno}: inline threshold literal {node.value!r}")

    if violations:
        details = "\n".join(violations)
        raise AssertionError(
            f"{module_label} violates threshold source-of-truth enforcement:\n{details}"
        )


def test_ci_gate_threshold_source_of_truth_enforcement() -> None:
    """CI gate: governance gate code must not inline governed threshold values."""
    source = Path("titan/science/governance_engine.py").read_text(encoding="utf-8")
    _assert_no_inline_threshold_literals(source, "titan/science/governance_engine.py")


def test_meta_threshold_source_of_truth_gate_rejects_known_bad_input() -> None:
    """Validating meta-test: gate fails on known-bad inline threshold literal."""
    bad_source = """
def gate_logic(readiness: float) -> bool:
    return readiness <= -8
"""

    with pytest.raises(
        AssertionError,
        match="violates threshold source-of-truth enforcement",
    ):
        _assert_no_inline_threshold_literals(bad_source, "known_bad_sample.py")

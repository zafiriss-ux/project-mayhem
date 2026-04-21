"""INV-05 system-wide enforcement: missing data must not default optimistically."""

import ast
from pathlib import Path

import pytest

from titan.science.governance_engine import GovernanceEngine

GOVERNANCE_CRITICAL_MODULES = [
    "titan/science/governance_engine.py",
    "titan/science/outcome_tracker.py",
    "titan/orchestration/coaching_pipeline.py",
    "titan/orchestration/daily_coach.py",
]

OPTIMISTIC_DEFAULTS = {
    "acwr": (1.0, "ACWR=1.0 is a safe band center and masks missing data"),
    "readiness_score": (100, "readiness=100 is maximally optimistic"),
    "sleep_score": (100, "sleep=100 is maximally optimistic"),
    "cs_confidence": (1.0, "cs_confidence=1.0 implies fully calibrated"),
    "drift_pct": (0.0, "drift_pct=0.0 implies ideal trend"),
}


def _base_context(**overrides):
    context = {
        "acwr": 1.1,
        "readiness_score": 80,
        "sleep_score": 80,
        "glycogen_debt": 1.5,
        "fatigue_level": "LOW",
        "days_since_last_vo2": 4,
        "fueling_confirmed": True,
        "today_hrv": 52.0,
        "baseline_hrv": 50.0,
        "today_rhr": 48.0,
        "baseline_rhr": 50.0,
    }
    context.update(overrides)
    return context


def _base_session(**overrides):
    session = {"session_type": "INTERVALS", "duration_min": 45, "zone": 4, "max_zone": 4}
    session.update(overrides)
    return session


class TestADR0051PolicyAST:
    """AST-level verification that governance modules avoid optimistic defaults."""

    @pytest.mark.parametrize("module_path", GOVERNANCE_CRITICAL_MODULES)
    def test_no_optimistic_get_defaults_in_governance_modules(self, module_path):
        source = Path(module_path).read_text(encoding="utf-8")
        tree = ast.parse(source)
        violations = []

        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get"
                and len(node.args) >= 2
            ):
                continue

            field_arg = node.args[0]
            default_arg = node.args[1]
            if not isinstance(field_arg, ast.Constant):
                continue

            field_name = field_arg.value
            if field_name not in OPTIMISTIC_DEFAULTS or not isinstance(default_arg, ast.Constant):
                continue

            optimistic_default, reason = OPTIMISTIC_DEFAULTS[field_name]
            if default_arg.value == optimistic_default:
                violations.append(
                    f"{module_path}:{node.lineno} context.get({field_name!r}, {optimistic_default!r}) — {reason}"
                )

        assert not violations, "ADR-0051 violation(s):\n" + "\n".join(violations)


class TestADR0051RuntimePolicy:
    """Runtime verification of conservative-fail behavior for missing data."""

    def test_none_acwr_downgrades_vo2_session(self):
        engine = GovernanceEngine()
        result = engine.apply_constraints(
            _base_session(session_type="HAMMER", max_zone=5),
            _base_context(acwr=None),
        )

        assert result["session_type"] != "HAMMER"
        assert "VO2_ELIGIBILITY_GATE" in result.get("governance_locks_applied", [])

    def test_none_hrv_applies_easy_ceiling(self):
        engine = GovernanceEngine()
        result = engine.apply_constraints(
            _base_session(session_type="INTERVALS"),
            _base_context(today_hrv=None),
        )

        assert result["session_type"] == "EASY"
        assert any(
            "DATA_MISSING_CONSERVATIVE_H2" in lock
            for lock in result.get("governance_locks_applied", [])
        )

    def test_missing_sleep_score_is_conservative_for_2of4(self):
        engine = GovernanceEngine()
        count, indicators = engine._evaluate_2of4_indicators(
            _base_context(sleep_score=None, readiness_score=40)
        )

        assert count >= 2
        assert "I2_sleep" in indicators
        assert "I3_readiness" in indicators

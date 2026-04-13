"""
Architectural fitness functions — Phase 9 entry gates.
These tests enforce structural invariants that functional tests cannot catch.
"""

from __future__ import annotations

import ast
from pathlib import Path

# ── Item 1 — Hard-stop gate exclusion from ThresholdAdapter ───────────────────


def test_get_soft_threshold_never_called_on_hard_stop_gates() -> None:
    """
    AST fitness: _get_soft_threshold() in governance_engine.py must never
    be called with a constant whose name starts with HARD_STOP_.
    INV hard-stop bypass invariant (ADR-0052).
    """
    try:
        from titan.science.threshold_adapter import HARD_STOP_GATE_NAMES
    except ImportError:
        # threshold_adapter scaffold not yet promoted; fall back to the canonical
        # exclusion set in thresholds.py (same values, same invariant).
        from titan.config.thresholds import (
            HARD_STOP_THRESHOLD_KEYS as HARD_STOP_GATE_NAMES,  # type: ignore[no-redef]
        )

    source = Path("titan/science/governance_engine.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_get_soft_threshold"
            and node.args
            and isinstance(node.args[0], ast.Constant)
        ):
            arg = node.args[0]
            assert arg.value not in HARD_STOP_GATE_NAMES, (
                f"_get_soft_threshold() called with hard-stop gate "
                f"'{arg.value}' at line {node.lineno} — "
                "hard-stop gates must bypass ThresholdAdapter (ADR-0052)."
            )


# ── Item 2 — OutcomeTracker queries always scoped to athlete_id ───────────────


def test_outcome_tracker_queries_always_scoped_to_athlete() -> None:
    """
    Every SQL string in outcome_tracker.py that references
    governance_outcomes must contain 'athlete_id'.
    INV-04 partial enforcement (full enforcement: T5-07-L3-B).
    """
    source = Path("titan/science/outcome_tracker.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            sql = node.value
            if "governance_outcomes" in sql and "SELECT" in sql.upper():
                assert "athlete_id" in sql, (
                    f"governance_outcomes query at line {node.lineno} "
                    f"missing athlete_id scope — INV-04 violation:\n{sql}"
                )


# ── Item 3 — coaching_pipeline.py must not import DailyCoach directly ─────────


def test_coaching_pipeline_no_direct_dailycoach_import() -> None:
    """
    coaching_pipeline.py must not import DailyCoach directly.
    Enforces T5-07-L3-D (coach:Any elimination).
    """
    source = Path("titan/orchestration/coaching_pipeline.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [a.name for a in node.names]
                if isinstance(node, ast.Import)
                else [node.module or ""]
            )
            for name in names:
                assert "DailyCoach" not in name and "daily_coach" not in name, (
                    f"coaching_pipeline.py imports DailyCoach at line {node.lineno}. "
                    "Use explicit callable Protocol instead (T5-07-L3-D)."
                )

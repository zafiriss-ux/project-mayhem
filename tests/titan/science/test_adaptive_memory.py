"""Mirrored test for titan/science/adaptive_memory.py — T5-79."""
from __future__ import annotations

from datetime import datetime

from titan.science.adaptive_memory import AdaptiveMemory


def test_module_imports_without_error() -> None:
    import titan.science.adaptive_memory  # noqa: F401


def test_adaptive_memory_instantiation_defaults() -> None:
    mem = AdaptiveMemory()
    assert mem.supercomp_status == "BASELINE"
    assert mem.monotony_index == 1.2
    assert mem.session_history == []


def test_check_monotony_high_variance_healthy() -> None:
    mem = AdaptiveMemory()
    result = mem.check_monotony(load_7d=100.0, std_dev_load=80.0)
    assert "VARIATION" in result or "HEALTHY" in result or "WATCH" in result


def test_supercompensation_window_peak_at_60h() -> None:
    mem = AdaptiveMemory()
    result = mem.supercompensation_window(last_hard_session_hours=60.0)
    assert "PEAK" in result or "SUPER" in result


def test_mechanical_load_risk_no_flags_returns_ok() -> None:
    mem = AdaptiveMemory()
    result = mem.mechanical_load_risk(
        easy_pace_today_sec=300.0, easy_pace_baseline_sec=300.0
    )
    assert "OK" in result

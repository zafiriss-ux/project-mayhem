"""Regression: StubSimpleEngine and StubAutonomic must not share mutable state."""
from __future__ import annotations

from tests.e2e.conftest import StubAutonomic, StubSimpleEngine


def test_stub_simple_engine_hrv_log_not_shared_between_instances():
    a = StubSimpleEngine()
    b = StubSimpleEngine()
    a.hrv_log.append("measurement")
    assert b.hrv_log == [], "hrv_log must be per-instance, not class-level"


def test_stub_autonomic_hrr_log_not_shared_between_instances():
    a = StubAutonomic()
    b = StubAutonomic()
    a.hrr_log.append(("2026-01-01", 55))
    assert b.hrr_log == [], "hrr_log must be per-instance, not class-level"

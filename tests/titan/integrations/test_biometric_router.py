"""Tests for BiometricRouter and ManualEntryAdapter (ADR-0055 / T5-100)."""
from unittest.mock import MagicMock

import pytest

from titan.integrations.biometric_router import BiometricRouter, ManualEntryAdapter


class _FakeDB:
    """Minimal DatabaseManager stub for testing."""

    def __init__(self, row: dict | None = None) -> None:
        self._row = row

    def get_daily_metric(self, date: str, athlete_id: str = "owner") -> dict | None:
        return self._row


# ── Test 1: Router uses Garmin when data is fresh ───────────────────────────

def test_router_uses_garmin_when_fresh():
    db = _FakeDB(None)
    manual = ManualEntryAdapter(db)
    router = BiometricRouter(garmin_age_hours=12.0, manual_adapter=manual)

    assert router.using_fallback is False
    assert router.active_source == "garmin"
    result = router.get_hrv("2026-05-09", garmin_value=65.0)
    assert result == 65.0


# ── Test 2: Router switches to manual when Garmin is stale ──────────────────

def test_router_switches_to_manual_when_stale():
    manual_row = {
        "date": "2026-05-09",
        "hrv_rmssd": 58.0,
        "resting_hr": 52,
        "sleep_hours": 7.5,
        "weight_kg": 72.0,
        "data_source": "manual_entry",
    }
    db = _FakeDB(manual_row)
    manual = ManualEntryAdapter(db)
    router = BiometricRouter(garmin_age_hours=72.0, manual_adapter=manual)

    assert router.using_fallback is True
    result = router.get_hrv("2026-05-09", garmin_value=65.0)
    assert result == 58.0


# ── Test 3: Router returns None when manual entry is empty ───────────────────

def test_router_returns_none_when_manual_empty():
    db = _FakeDB(None)
    manual = ManualEntryAdapter(db)
    router = BiometricRouter(garmin_age_hours=72.0, manual_adapter=manual)

    assert router.using_fallback is True
    result = router.get_hrv("2026-05-09", garmin_value=65.0)
    assert result is None


# ── Test 4: ManualEntryAdapter only reads manual_entry rows ─────────────────

def test_manual_adapter_reads_only_manual_source():
    garmin_row = {
        "date": "2026-05-09",
        "hrv_rmssd": 71.0,
        "resting_hr": 48,
        "sleep_hours": 8.0,
        "weight_kg": 73.0,
        "data_source": "garmin_api",
    }
    db = _FakeDB(garmin_row)
    manual = ManualEntryAdapter(db)

    assert manual.get_hrv("2026-05-09") is None
    assert manual.get_rhr("2026-05-09") is None
    assert manual.get_sleep_hours("2026-05-09") is None
    assert manual.get_weight_kg("2026-05-09") is None


# ── Test 5: ManualEntryAdapter reads manual_entry rows correctly ─────────────

def test_manual_adapter_reads_manual_entry():
    manual_row = {
        "date": "2026-05-09",
        "hrv_rmssd": 62.0,
        "resting_hr": 50,
        "sleep_hours": 7.0,
        "weight_kg": 71.5,
        "data_source": "manual_entry",
    }
    db = _FakeDB(manual_row)
    manual = ManualEntryAdapter(db)

    assert manual.get_hrv("2026-05-09") == 62.0
    assert manual.get_rhr("2026-05-09") == 50.0
    assert manual.get_sleep_hours("2026-05-09") == 7.0
    assert manual.get_weight_kg("2026-05-09") == 71.5


# ── Test 6: Router active_source label reflects arbitration ─────────────────

def test_router_active_source_label():
    db_empty = _FakeDB(None)
    manual_fresh = ManualEntryAdapter(db_empty)

    router_fresh = BiometricRouter(garmin_age_hours=12.0, manual_adapter=manual_fresh)
    assert router_fresh.active_source == "garmin"

    router_stale = BiometricRouter(garmin_age_hours=72.0, manual_adapter=manual_fresh)
    assert router_stale.active_source == "manual_entry"

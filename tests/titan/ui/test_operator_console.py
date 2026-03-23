"""Tests for OperatorConsoleService.garmin_sync_indicator — ADR-0050 / T5-12 Pass 2."""

import pytest

from titan.ui.operator_console import OperatorConsoleService


class TestGarminSyncIndicator:
    """ADR-0050 D2 — dashboard indicator appearance and clear conditions."""

    # ── Clear condition ──────────────────────────────────────────────────────

    def test_all_clear_returns_not_visible(self):
        """Indicator is hidden when all three clear conditions hold."""
        result = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=False,
            has_baseline=True,
            data_age_hours=1.0,
            trust_level="TRUSTED",
            last_successful_sync_at="2026-03-23T07:00:00",
        )
        assert result["visible"] is False
        assert result["message"] is None

    def test_clear_requires_all_three_conditions(self):
        """Indicator stays visible if any one clear condition fails."""
        # trust not TRUSTED
        r = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=False,
            has_baseline=True,
            data_age_hours=1.0,
            trust_level="SUSPECT",
            last_successful_sync_at="2026-03-23T07:00:00",
        )
        assert r["visible"] is True

        # age stale
        r = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=False,
            has_baseline=True,
            data_age_hours=999.0,
            trust_level="TRUSTED",
            last_successful_sync_at="2026-03-01T07:00:00",
        )
        assert r["visible"] is True

        # is_degraded
        r = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=True,
            has_baseline=True,
            data_age_hours=1.0,
            trust_level="TRUSTED",
            last_successful_sync_at="2026-03-23T07:00:00",
        )
        assert r["visible"] is True

    # ── Appearance condition — active degradation ────────────────────────────

    def test_degraded_with_baseline_shows_last_valid_data_age(self):
        """Active degradation with baseline: indicator shows last valid data age."""
        result = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=True,
            has_baseline=True,
            data_age_hours=4.5,
            trust_level="INVALID",
            last_successful_sync_at="2026-03-23T03:00:00",
        )
        assert result["visible"] is True
        assert "last valid data: 4.5h ago" in result["message"]
        assert "Garmin sync degraded" in result["message"]

    def test_degraded_no_baseline_shows_no_baseline_message(self):
        """Active degradation without baseline: no-baseline wording."""
        result = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=True,
            has_baseline=False,
            data_age_hours=None,
            trust_level="INVALID",
            last_successful_sync_at=None,
        )
        assert result["visible"] is True
        assert "no valid Garmin baseline available" in result["message"]

    def test_degraded_with_baseline_but_no_sync_timestamp_shows_no_baseline(self):
        """Active degradation with baseline flag but no timestamp uses no-baseline wording."""
        result = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=True,
            has_baseline=True,
            data_age_hours=10.0,
            trust_level="INVALID",
            last_successful_sync_at=None,  # no recorded timestamp
        )
        assert result["visible"] is True
        assert "no valid Garmin baseline available" in result["message"]

    # ── Appearance condition — trust degraded, not actively degraded ─────────

    def test_trust_invalid_not_degraded_shows_invalid_message(self):
        """Trust INVALID (not actively degraded): conservative coaching mode wording."""
        result = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=False,
            has_baseline=True,
            data_age_hours=30.0,
            trust_level="INVALID",
            last_successful_sync_at="2026-03-22T07:00:00",
        )
        assert result["visible"] is True
        assert "invalid/stale" in result["message"]
        assert "conservative coaching mode" in result["message"]

    def test_trust_suspect_not_degraded_shows_stale_message(self):
        """Trust SUSPECT (not actively degraded): stale-data wording."""
        result = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=False,
            has_baseline=True,
            data_age_hours=13.0,
            trust_level="SUSPECT",
            last_successful_sync_at="2026-03-22T18:00:00",
        )
        assert result["visible"] is True
        assert "stale" in result["message"]

    def test_stale_age_without_trust_degraded_shows_stale_message(self):
        """Data age stale alone (trust TRUSTED but age above threshold): stale wording."""
        result = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=False,
            has_baseline=True,
            data_age_hours=50.0,
            trust_level="TRUSTED",
            last_successful_sync_at="2026-03-21T07:00:00",
        )
        assert result["visible"] is True
        assert "stale" in result["message"]

    def test_no_data_age_is_treated_as_stale(self):
        """None data_age_hours is treated as stale (unknown age)."""
        result = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=False,
            has_baseline=False,
            data_age_hours=None,
            trust_level="TRUSTED",
            last_successful_sync_at=None,
        )
        # age_stale=True, trust_degraded=False → stale path
        assert result["visible"] is True
        assert "stale" in result["message"]

    # ── Custom threshold ─────────────────────────────────────────────────────

    def test_custom_trusted_age_threshold(self):
        """Custom trusted_age_threshold_hours overrides the default."""
        # 5h age with threshold 4h → stale
        r = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=False,
            has_baseline=True,
            data_age_hours=5.0,
            trust_level="TRUSTED",
            last_successful_sync_at="2026-03-23T02:00:00",
            trusted_age_threshold_hours=4.0,
        )
        assert r["visible"] is True

        # 3h age with threshold 4h → clear
        r = OperatorConsoleService.garmin_sync_indicator(
            is_degraded=False,
            has_baseline=True,
            data_age_hours=3.0,
            trust_level="TRUSTED",
            last_successful_sync_at="2026-03-23T04:00:00",
            trusted_age_threshold_hours=4.0,
        )
        assert r["visible"] is False

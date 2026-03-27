"""
T5-46: HRV deduplication on overlapping Garmin syncs.

Tests that add_hrv_measurement deduplicates by date, keeping the most recent
entry per date, so overlapping Garmin syncs do not inflate the baseline log.
"""

from titan.science.hrv_engine import HRVGuidedEngine


class TestHRVDeduplication:
    """Tests for HRV deduplication behaviour on overlapping syncs."""

    def test_duplicate_date_keeps_only_one_entry(self):
        """Adding the same date twice should result in only one entry."""
        engine = HRVGuidedEngine()
        engine.add_hrv_measurement("2024-01-01", 60.0)
        engine.add_hrv_measurement("2024-01-01", 70.0)

        dates = [date for date, _ in engine.hrv_log]
        assert dates.count("2024-01-01") == 1, (
            "Duplicate date entries inflate the baseline log — expected exactly 1 entry"
        )

    def test_duplicate_date_keeps_most_recent_value(self):
        """When a date is added twice, the most recent value (last write) is kept."""
        engine = HRVGuidedEngine()
        engine.add_hrv_measurement("2024-01-01", 60.0)
        engine.add_hrv_measurement("2024-01-01", 70.0)

        entry = next((rmssd for date, rmssd in engine.hrv_log if date == "2024-01-01"), None)
        assert entry == 70.0, f"Expected most recent value 70.0, got {entry}"

    def test_different_dates_all_retained(self):
        """Entries for distinct dates must all be preserved."""
        engine = HRVGuidedEngine()
        engine.add_hrv_measurement("2024-01-01", 60.0)
        engine.add_hrv_measurement("2024-01-02", 65.0)
        engine.add_hrv_measurement("2024-01-03", 70.0)

        assert len(engine.hrv_log) == 3, (
            f"Expected 3 distinct-date entries, got {len(engine.hrv_log)}"
        )

    def test_multiple_overlapping_syncs_for_same_date(self):
        """Multiple overlapping syncs for the same date should still yield one entry."""
        engine = HRVGuidedEngine()
        for value in [55.0, 60.0, 65.0, 70.0]:
            engine.add_hrv_measurement("2024-01-01", value)

        dates = [date for date, _ in engine.hrv_log]
        assert dates.count("2024-01-01") == 1

        entry = next(rmssd for date, rmssd in engine.hrv_log if date == "2024-01-01")
        assert entry == 70.0, f"Expected most recent value 70.0, got {entry}"

    def test_mixed_dates_with_duplicates(self):
        """Mix of new and duplicate dates: each date appears exactly once, latest value kept."""
        engine = HRVGuidedEngine()
        engine.add_hrv_measurement("2024-01-01", 60.0)
        engine.add_hrv_measurement("2024-01-02", 65.0)
        engine.add_hrv_measurement("2024-01-01", 62.0)  # duplicate, should replace
        engine.add_hrv_measurement("2024-01-03", 70.0)

        assert len(engine.hrv_log) == 3, (
            f"Expected 3 unique dates, got {len(engine.hrv_log)}"
        )
        val_jan1 = next(rmssd for date, rmssd in engine.hrv_log if date == "2024-01-01")
        assert val_jan1 == 62.0, f"Expected updated value 62.0 for 2024-01-01, got {val_jan1}"

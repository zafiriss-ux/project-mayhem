"""
T5-66: save_daily_metric — Garmin re-sync must not destroy manual subjective fields.

Acceptance criterion: a Garmin re-sync on a date where mood_score and
soreness_score were manually entered does NOT zero those fields.
"""

import pytest


@pytest.fixture()
def db(db_manager_factory):
    """Provide an isolated DatabaseManager for each test."""
    return db_manager_factory()


def _fetch_row(db, date: str) -> dict:
    """Return daily_metrics row for a given date as a dict."""
    row = db.conn.execute(
        "SELECT weight_kg, hrv_rmssd, resting_hr, sleep_hours, sleep_quality, "
        "soreness, fatigue_level, mood, notes, quality_flag "
        "FROM daily_metrics WHERE date = ?",
        (date,),
    ).fetchone()
    if row is None:
        return {}
    keys = [
        "weight_kg", "hrv_rmssd", "resting_hr", "sleep_hours", "sleep_quality",
        "soreness", "fatigue_level", "mood", "notes", "quality_flag",
    ]
    return dict(zip(keys, row, strict=True))


class TestSaveDailyMetricUpsert:
    """Verify per-column UPSERT semantics for save_daily_metric."""

    # ------------------------------------------------------------------
    # T5-66 acceptance criterion
    # ------------------------------------------------------------------

    @pytest.mark.integration
    def test_garmin_resync_does_not_zero_mood_and_soreness(self, db):
        """Re-syncing Garmin data must preserve manually entered mood/soreness."""
        # Step 1: athlete manually enters subjective data (no Garmin fields)
        db.save_daily_metric(
            date="2026-01-15",
            mood=4,
            soreness=2,
            fatigue=3,
            notes="felt good",
        )

        # Step 2: Garmin re-sync arrives (hrv/rhr/sleep — no subjective fields)
        db.save_daily_metric(
            date="2026-01-15",
            hrv=52.3,
            rhr=48,
            sleep_hours=7.5,
            sleep_quality=80,
        )

        row = _fetch_row(db, "2026-01-15")
        assert row.get("mood") == 4, f"mood zeroed: {row}"
        assert row.get("soreness") == 2, f"soreness zeroed: {row}"
        assert row.get("fatigue_level") == 3, f"fatigue_level zeroed: {row}"
        assert row.get("notes") == "felt good", f"notes zeroed: {row}"

    @pytest.mark.integration
    def test_garmin_resync_does_not_zero_notes(self, db):
        """Notes must also survive Garmin re-sync."""
        db.save_daily_metric(date="2026-01-16", mood=5, notes="rest day")
        db.save_daily_metric(date="2026-01-16", hrv=55.0, rhr=46)
        row = _fetch_row(db, "2026-01-16")
        assert row.get("mood") == 5
        assert row.get("notes") == "rest day"

    # ------------------------------------------------------------------
    # Garmin columns are correctly overwritten on re-sync
    # ------------------------------------------------------------------

    @pytest.mark.integration
    def test_garmin_fields_overwritten_on_resync(self, db):
        """Garmin-sourced fields are updated when new data arrives."""
        db.save_daily_metric(date="2026-01-17", hrv=50.0, rhr=50, sleep_hours=6.0)
        db.save_daily_metric(date="2026-01-17", hrv=55.0, rhr=47, sleep_hours=7.5)
        row = _fetch_row(db, "2026-01-17")
        assert row.get("hrv_rmssd") == pytest.approx(55.0)
        assert row.get("resting_hr") == 47
        assert row.get("sleep_hours") == pytest.approx(7.5)

    # ------------------------------------------------------------------
    # First insert sets all fields correctly
    # ------------------------------------------------------------------

    @pytest.mark.integration
    def test_first_insert_sets_all_fields(self, db):
        """Initial insert stores both Garmin and subjective fields."""
        db.save_daily_metric(
            date="2026-01-18",
            hrv=48.0,
            rhr=52,
            mood=3,
            soreness=1,
        )
        row = _fetch_row(db, "2026-01-18")
        assert row.get("hrv_rmssd") == pytest.approx(48.0)
        assert row.get("resting_hr") == 52
        assert row.get("mood") == 3
        assert row.get("soreness") == 1

    # ------------------------------------------------------------------
    # Null incoming Garmin fields do not wipe existing Garmin data
    # ------------------------------------------------------------------

    @pytest.mark.integration
    def test_none_incoming_garmin_field_does_not_overwrite_existing(self, db):
        """Passing hrv=None on second call should not overwrite the stored HRV."""
        db.save_daily_metric(date="2026-01-19", hrv=60.0)
        db.save_daily_metric(date="2026-01-19", hrv=None, rhr=49)
        row = _fetch_row(db, "2026-01-19")
        assert row.get("hrv_rmssd") == pytest.approx(60.0), (
            "Existing HRV should not be overwritten with NULL"
        )

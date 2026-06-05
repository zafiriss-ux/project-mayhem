"""
T5-69: Duplicate sync_activities() calls must not produce duplicate rows.

Acceptance criterion: a duplicate call to sync_activities() for the same
window does not produce duplicate rows in training_log when activityId
is present in the Garmin payload.

Follows the T5-46 HRV deduplication pattern:
  - activity_id extracted in sync_activities() → saved as garmin_activity_id
  - training_log.garmin_activity_id has a partial UNIQUE index (WHERE NOT NULL)
  - save_session() uses INSERT OR IGNORE, so duplicate inserts are silent no-ops
"""

import pytest

from titan.core.database import DatabaseManager


@pytest.fixture()
def db(db_manager_factory):
    return db_manager_factory()


def _count_sessions(db, activity_id: str) -> int:
    """Return the number of training_log rows matching a garmin_activity_id."""
    row = db.conn.execute(
        "SELECT COUNT(*) FROM training_log WHERE garmin_activity_id = ?",
        (activity_id,),
    ).fetchone()
    return row[0]


def _count_all_sessions(db) -> int:
    row = db.conn.execute("SELECT COUNT(*) FROM training_log").fetchone()
    return row[0]


class TestActivityDeduplication:
    """Verify that duplicate save_session() calls on the same garmin_activity_id
    produce exactly one row (INSERT OR IGNORE + UNIQUE index)."""

    # ------------------------------------------------------------------
    # T5-69 acceptance criterion
    # ------------------------------------------------------------------

    @pytest.mark.integration
    def test_duplicate_save_session_does_not_insert_duplicate_row(self, db):
        """Two save_session() calls with the same garmin_activity_id → 1 row."""
        kwargs = {
            "date": "2026-01-20",
            "session_type": "EASY",
            "distance_km": 10.0,
            "duration_sec": 3600,
            "garmin_activity_id": "ACT_001",
        }
        db.save_session(**kwargs)
        db.save_session(**kwargs)  # second call — same window re-sync

        assert _count_sessions(db, "ACT_001") == 1, (
            "Duplicate garmin_activity_id produced more than one row"
        )

    @pytest.mark.integration
    def test_three_resync_calls_produce_single_row(self, db):
        """Three overlapping syncs for same activity → still exactly one row."""
        for _ in range(3):
            db.save_session(
                date="2026-01-21",
                session_type="TEMPO",
                distance_km=8.0,
                duration_sec=2400,
                garmin_activity_id="ACT_002",
            )
        assert _count_sessions(db, "ACT_002") == 1

    # ------------------------------------------------------------------
    # Distinct activity IDs each get their own row
    # ------------------------------------------------------------------

    @pytest.mark.integration
    def test_different_activity_ids_each_produce_a_row(self, db):
        """Two different activityIds → two rows."""
        db.save_session(
            date="2026-01-22",
            session_type="EASY",
            distance_km=5.0,
            duration_sec=1800,
            garmin_activity_id="ACT_003",
        )
        db.save_session(
            date="2026-01-22",
            session_type="INTERVALS",
            distance_km=7.0,
            duration_sec=2700,
            garmin_activity_id="ACT_004",
        )
        assert _count_sessions(db, "ACT_003") == 1
        assert _count_sessions(db, "ACT_004") == 1
        assert _count_all_sessions(db) == 2

    # ------------------------------------------------------------------
    # Sessions without activityId are not deduplicated (NULL rows allowed)
    # ------------------------------------------------------------------

    @pytest.mark.integration
    def test_null_activity_id_rows_are_not_deduplicated(self, db):
        """Rows without garmin_activity_id (NULL) are never considered duplicates."""
        db.save_session(
            date="2026-01-23",
            session_type="EASY",
            distance_km=6.0,
            duration_sec=2100,
            garmin_activity_id=None,
        )
        db.save_session(
            date="2026-01-23",
            session_type="EASY",
            distance_km=6.0,
            duration_sec=2100,
            garmin_activity_id=None,
        )
        # Both rows inserted because NULL ≠ NULL in UNIQUE partial index
        assert _count_all_sessions(db) == 2

    # ------------------------------------------------------------------
    # activity_id column exists in schema
    # ------------------------------------------------------------------

    @pytest.mark.integration
    def test_garmin_activity_id_column_exists(self, db):
        """training_log schema has garmin_activity_id column."""
        cols = [
            row[1]
            for row in db.conn.execute("PRAGMA table_info(training_log)").fetchall()
        ]
        assert "garmin_activity_id" in cols, (
            f"garmin_activity_id column missing from training_log; columns: {cols}"
        )

    @pytest.mark.integration
    def test_unique_index_on_garmin_activity_id(self, db):
        """A partial UNIQUE index on garmin_activity_id must exist."""
        indices = [
            row[1]
            for row in db.conn.execute(
                "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='training_log'"
            ).fetchall()
        ]
        assert any("garmin" in idx.lower() for idx in indices), (
            f"No garmin_activity_id index found; indices: {indices}"
        )

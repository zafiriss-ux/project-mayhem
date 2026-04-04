"""HD-06 / OBS-039: DegradedModeTracker SQLite persistence tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from titan.core.database import DatabaseManager
from titan.orchestration.daily_coach import DegradedModeTracker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(tmp_path: Path) -> DatabaseManager:
    """Create a real on-disk DatabaseManager in a temp directory."""
    return DatabaseManager(db_name="test_degraded.db", db_dir=tmp_path)


def _table_row_count(db: DatabaseManager, failure_type: str) -> int:
    """Return number of rows in degraded_mode_state for the given failure_type."""
    row = db.conn.cursor().execute(
        "SELECT COUNT(*) FROM degraded_mode_state WHERE failure_type = ?",
        (failure_type,),
    ).fetchone()
    return row[0] if row else 0


def _read_degraded_since(db: DatabaseManager, failure_type: str) -> str | None:
    """Return the raw degraded_since string for a failure_type, or None."""
    row = db.conn.cursor().execute(
        "SELECT degraded_since FROM degraded_mode_state WHERE failure_type = ?",
        (failure_type,),
    ).fetchone()
    return row[0] if row else None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDegradedModePersistence:
    def test_new_degradation_is_persisted(self, tmp_path: Path) -> None:
        """When a new degradation flag is set, the row must appear in the DB."""
        db = _make_db(tmp_path)
        tracker = DegradedModeTracker(db=db)

        tracker.update({"GARMIN_SYNC": True}, alert_fn=lambda _: None)

        assert _table_row_count(db, "GARMIN_SYNC") == 1
        db.close()

    def test_cleared_degradation_is_removed_from_db(self, tmp_path: Path) -> None:
        """When a flag clears, the corresponding DB row must be deleted."""
        db = _make_db(tmp_path)
        tracker = DegradedModeTracker(db=db)

        tracker.update({"GARMIN_SYNC": True}, alert_fn=lambda _: None)
        assert _table_row_count(db, "GARMIN_SYNC") == 1

        tracker.update({"GARMIN_SYNC": False}, alert_fn=lambda _: None)
        assert _table_row_count(db, "GARMIN_SYNC") == 0
        db.close()

    def test_restart_simulation_timer_preserved(self, tmp_path: Path) -> None:
        """Degradation timer must survive a process restart (DB open → close → reopen)."""
        original_ts = datetime(2026, 4, 3, 8, 0, 0, tzinfo=UTC)

        # First process: set degradation with a known timestamp
        db1 = _make_db(tmp_path)
        tracker1 = DegradedModeTracker(db=db1)
        tracker1._degraded_since["GARMIN_SYNC"] = original_ts
        tracker1._persist_state("GARMIN_SYNC", original_ts)
        db1.close()

        # Second process: open fresh DB, hydrate tracker
        db2 = _make_db(tmp_path)
        tracker2 = DegradedModeTracker(db=db2)

        assert "GARMIN_SYNC" in tracker2._degraded_since
        restored_ts = tracker2._degraded_since["GARMIN_SYNC"]
        assert restored_ts == original_ts, (
            f"Expected {original_ts.isoformat()}, got {restored_ts.isoformat()}"
        )
        db2.close()

    def test_degraded_mode_restored_event_emitted_on_hydration(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """degraded_mode_restored structured event must be emitted when DB has state."""
        import json
        import logging

        ts = datetime(2026, 4, 3, 8, 0, 0, tzinfo=UTC)

        # Seed the DB directly
        db_seed = _make_db(tmp_path)
        db_seed.conn.cursor().execute(
            "INSERT OR REPLACE INTO degraded_mode_state (failure_type, degraded_since) VALUES (?, ?)",
            ("GARMIN_SYNC", ts.isoformat()),
        )
        db_seed.conn.commit()
        db_seed.close()

        # Hydration
        db = _make_db(tmp_path)
        with caplog.at_level(logging.INFO, logger="titan.orchestration.daily_coach"):
            DegradedModeTracker(db=db)

        messages = [r.getMessage() for r in caplog.records]
        restored_events = [
            m for m in messages
            if "degraded_mode_restored" in m
        ]
        assert restored_events, "Expected degraded_mode_restored event"

        payload = json.loads(restored_events[0])
        assert payload["action"] == "degraded_mode_restored"
        assert "GARMIN_SYNC" in payload["failure_types"]
        db.close()

    def test_no_restored_event_when_db_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """No degraded_mode_restored event when the degraded_mode_state table is empty."""
        import logging

        db = _make_db(tmp_path)
        with caplog.at_level(logging.INFO, logger="titan.orchestration.daily_coach"):
            DegradedModeTracker(db=db)

        messages = [r.getMessage() for r in caplog.records]
        assert not any("degraded_mode_restored" in m for m in messages)
        db.close()

    def test_tracker_without_db_behaves_as_before(self) -> None:
        """DegradedModeTracker(db=None) must have identical in-memory behaviour."""
        tracker = DegradedModeTracker()  # no db arg — original usage

        alerts: list[str] = []
        tracker.update({"GARMIN_SYNC": True}, alert_fn=alerts.append)
        assert "GARMIN_SYNC" in tracker._degraded_since

        tracker.update({"GARMIN_SYNC": False}, alert_fn=alerts.append)
        assert "GARMIN_SYNC" not in tracker._degraded_since

    def test_degraded_mode_state_table_created_by_migration(self, tmp_path: Path) -> None:
        """Migration v9 must create the degraded_mode_state table."""
        db = _make_db(tmp_path)
        result = db.conn.cursor().execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='degraded_mode_state'"
        ).fetchone()
        assert result is not None, "degraded_mode_state table was not created by migration"
        db.close()

    def test_schema_version_is_nine(self, tmp_path: Path) -> None:
        """After migration, PRAGMA user_version must equal 9."""
        db = _make_db(tmp_path)
        version = db.conn.cursor().execute("PRAGMA user_version").fetchone()[0]
        assert version == 9
        db.close()

    def test_persist_state_tolerates_db_error_gracefully(self, tmp_path: Path) -> None:
        """_persist_state must not raise when the DB call fails; logs WARNING."""
        import logging

        db = _make_db(tmp_path)
        tracker = DegradedModeTracker(db=db)

        # Close the connection to force a DB error on next write
        db.conn.close()

        # Must not raise
        tracker._persist_state("GARMIN_SYNC", datetime.now(UTC))
        db2 = DatabaseManager(db_name="test_degraded.db", db_dir=tmp_path)
        db2.close()

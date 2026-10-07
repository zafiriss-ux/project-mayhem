"""Operations domain SQL: sync outcomes and freshness, degraded-mode state
(HD-06) and nutrition preferences."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager


class OperationsRepository:
    """Operations SQL, on the owning DatabaseManager's connection and lock."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def get_nutrition_preferences(self, athlete_id: str = 'owner') -> dict | None:
        """Return nutrition preferences for athlete_id, or None if not set."""
        with self._db._lock:
            self._db._ensure_open_locked()
            c = self._db.conn.cursor()
            c.execute(
                'SELECT * FROM nutrition_preferences WHERE athlete_id = ?',
                (athlete_id,)
            )
            row = c.fetchone()
            if not row:
                return None
            cols = [d[0] for d in c.description]
            return dict(zip(cols, row, strict=True))

    def save_nutrition_preferences(
        self, athlete_id: str = 'owner', prefs: dict = None
    ) -> None:
        """Upsert nutrition preferences for athlete_id."""
        if not prefs:
            return
        with self._db._lock:
            self._db._ensure_open_locked()
            c = self._db.conn.cursor()
            c.execute('''
                INSERT INTO nutrition_preferences (
                    athlete_id, training_time, fasted_training,
                    dietary_style, meal_frequency, biological_sex,
                    menstrual_tracking, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(athlete_id) DO UPDATE SET
                    training_time=excluded.training_time,
                    fasted_training=excluded.fasted_training,
                    dietary_style=excluded.dietary_style,
                    meal_frequency=excluded.meal_frequency,
                    biological_sex=excluded.biological_sex,
                    menstrual_tracking=excluded.menstrual_tracking,
                    updated_at=excluded.updated_at
            ''', (
                athlete_id,
                prefs.get('training_time', 'variable'),
                prefs.get('fasted_training', 'easy_only'),
                prefs.get('dietary_style', 'standard'),
                prefs.get('meal_frequency', 3),
                prefs.get('biological_sex', 'male'),
                prefs.get('menstrual_tracking', 'no'),
            ))
            self._db.conn.commit()

    def get_all_degraded_mode_states(self, athlete_id: str = "default") -> list[tuple[str, str]]:
        """Return all (failure_type, degraded_since) rows for the given athlete."""
        with self._db._lock:
            return self._db.conn.cursor().execute(
                "SELECT failure_type, degraded_since "
                "FROM degraded_mode_state WHERE athlete_id = ?",
                (athlete_id,),
            ).fetchall()

    def upsert_degraded_mode_state(
        self, failure_type: str, degraded_since: str, athlete_id: str = "default"
    ) -> None:
        """Insert or replace a degraded-mode row keyed by failure_type."""
        with self._db._lock:
            self._db.conn.cursor().execute(
                "INSERT OR REPLACE INTO degraded_mode_state "
                "(failure_type, degraded_since, athlete_id) VALUES (?, ?, ?)",
                (failure_type, degraded_since, athlete_id),
            )
            self._db.conn.commit()

    def delete_degraded_mode_state(
        self, failure_type: str, athlete_id: str = "default"
    ) -> None:
        """Delete the degraded-mode row for a failure_type (degradation resolved)."""
        with self._db._lock:
            self._db.conn.cursor().execute(
                "DELETE FROM degraded_mode_state "
                "WHERE failure_type = ? AND athlete_id = ?",
                (failure_type, athlete_id),
            )
            self._db.conn.commit()

    def record_sync_outcome(
        self,
        *,
        source: str,
        attempted_at: datetime,
        success: bool,
        error_class: str | None = None,
    ) -> None:
        """Persist latest sync attempt outcome for a source system."""
        attempted_iso = attempted_at.astimezone(UTC).isoformat()
        success_iso = attempted_iso if success else None

        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """INSERT INTO sync_metadata (
                        source,
                        last_attempt_ts,
                        last_success_ts,
                        last_sync_ok,
                        last_error_class
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        last_attempt_ts = excluded.last_attempt_ts,
                        last_success_ts = CASE
                            WHEN excluded.last_sync_ok = 1 THEN excluded.last_success_ts
                            ELSE sync_metadata.last_success_ts
                        END,
                        last_sync_ok = excluded.last_sync_ok,
                        last_error_class = excluded.last_error_class""",
                (source, attempted_iso, success_iso, 1 if success else 0, error_class),
            )
            self._db.conn.commit()

    def get_last_sync_outcome(self, source: str) -> dict[str, Any] | None:
        """Return latest sync outcome metadata for a source."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT last_attempt_ts, last_success_ts, last_sync_ok, last_error_class
                   FROM sync_metadata WHERE source = ?""",
                (source,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        attempted_at = None
        success_at = None
        if row[0]:
            with suppress(ValueError, TypeError):
                attempted_at = datetime.fromisoformat(row[0])
        if row[1]:
            with suppress(ValueError, TypeError):
                success_at = datetime.fromisoformat(row[1])

        return {
            "last_attempt_ts": attempted_at,
            "last_success_ts": success_at,
            "last_sync_ok": bool(row[2]),
            "last_error_class": row[3],
        }

    def get_last_garmin_sync_timestamp(self) -> datetime | None:
        """Return a datetime representing the most recent data written by Garmin sync.

        Checks the latest date in both daily_metrics and training_log and returns
        the more recent of the two, parsed as a midnight-UTC datetime.

        Returns None if no data exists in either table.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                "SELECT MAX(date) FROM daily_metrics WHERE date IS NOT NULL"
            )
            dm_row = cursor.fetchone()
            cursor.execute(
                "SELECT MAX(date) FROM training_log WHERE date IS NOT NULL"
            )
            tl_row = cursor.fetchone()

        latest: str | None = None
        for row in (dm_row, tl_row):
            if row and row[0] and (latest is None or row[0] > latest):
                latest = row[0]

        if not latest:
            return None

        try:
            return datetime.fromisoformat(latest).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None

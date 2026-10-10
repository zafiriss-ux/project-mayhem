"""Physiology domain SQL: daily metrics (morning check-in), HRV, resting HR,
HRR, glycogen debt and weight history."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager


class PhysiologyRepository:
    """Physiology SQL, on the owning DatabaseManager's connection and lock."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def save_daily_metric(
        self,
        date: str,
        weight: float | None = None,
        hrv: float | None = None,
        rhr: int | None = None,
        sleep_hours: float | None = None,
        sleep_quality: int | None = None,
        soreness: int | None = None,
        fatigue: int | None = None,
        mood: int | None = None,
        notes: str | None = None,
        quality_flag: str | None = None,
        data_source: str = "garmin_api",
        athlete_id: str = "owner",
    ) -> None:
        """
        Save morning check-in data.

        Args:
            date: Date in ISO format (YYYY-MM-DD)
            weight: Weight in kg
            hrv: HRV RMSSD in ms
            rhr: Resting heart rate in bpm
            sleep_hours: Sleep duration in hours
            sleep_quality: Sleep quality score (0-100)
            soreness: Soreness level (0-5 scale)
            fatigue: Fatigue level (0-5 scale)
            mood: Mood score (0-5 scale)
            notes: Optional text notes
            data_source: Provenance tag — 'garmin_api' or 'manual_entry'
            athlete_id: Athlete scope for the row (multi-athlete isolation)
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            # T5-66: Per-column UPSERT semantics.
            # Garmin-sourced columns (hrv_rmssd, resting_hr, sleep_hours,
            # sleep_quality, weight_kg, quality_flag) are overwritten on re-sync.
            # Manual subjective fields (soreness, fatigue_level, mood, notes) are
            # preserved when a row already exists — a Garmin re-sync must not zero
            # values the athlete manually entered.
            # T5-115: data_source is preserved if already set to 'manual_entry' so
            # an automated Garmin re-sync never silently overwrites intentional
            # manual provenance.
            cursor.execute("""
                INSERT INTO daily_metrics
                (athlete_id, date, weight_kg, hrv_rmssd, resting_hr, sleep_hours,
                 sleep_quality, soreness, fatigue_level, mood, notes, quality_flag,
                 data_source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(athlete_id, date) DO UPDATE SET
                    weight_kg    = CASE WHEN excluded.weight_kg    IS NOT NULL THEN excluded.weight_kg    ELSE weight_kg    END,
                    hrv_rmssd    = CASE WHEN excluded.hrv_rmssd    IS NOT NULL THEN excluded.hrv_rmssd    ELSE hrv_rmssd    END,
                    resting_hr   = CASE WHEN excluded.resting_hr   IS NOT NULL THEN excluded.resting_hr   ELSE resting_hr   END,
                    sleep_hours  = CASE WHEN excluded.sleep_hours  IS NOT NULL THEN excluded.sleep_hours  ELSE sleep_hours  END,
                    sleep_quality= CASE WHEN excluded.sleep_quality IS NOT NULL THEN excluded.sleep_quality ELSE sleep_quality END,
                    quality_flag = CASE WHEN excluded.quality_flag IS NOT NULL THEN excluded.quality_flag ELSE quality_flag END,
                    data_source  = CASE WHEN data_source = 'manual_entry' THEN data_source ELSE excluded.data_source END
            """, (athlete_id, date, weight, hrv, rhr, sleep_hours, sleep_quality, soreness, fatigue, mood, notes, quality_flag, data_source))
            if self._db._transaction_depth == 0:
                self._db.conn.commit()

    def save_daily_metric_if_missing(
        self, date: str, hrv: float | None = None, athlete_id: str = "owner"
    ) -> None:
        """Persist HRV for a historical date only if no row exists yet.

        Uses INSERT OR IGNORE so that manually entered data for past dates is
        never overwritten by backfill from Garmin sync.

        Args:
            date:       Date in ISO format (YYYY-MM-DD)
            hrv:        HRV RMSSD in ms
            athlete_id: Athlete scope for row-level isolation (ADR-0033)
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """
                INSERT OR IGNORE INTO daily_metrics (athlete_id, date, hrv_rmssd, data_source)
                VALUES (?, ?, ?, 'garmin_api')
                """,
                (athlete_id, date, hrv),
            )
            if self._db._transaction_depth == 0:
                self._db.conn.commit()

    def replace_garmin_hrv(self, date: str, hrv: float, athlete_id: str = "owner") -> None:
        """Set HRV for a date from Garmin, unless the row was entered by hand (D-056).

        Creates the row when the date has none. A ``manual_entry`` row is left alone.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """
                UPDATE daily_metrics SET hrv_rmssd = ?
                WHERE athlete_id = ? AND date = ? AND COALESCE(data_source, 'garmin_api') != 'manual_entry'
                """,
                (hrv, athlete_id, date),
            )
            cursor.execute(
                """
                INSERT OR IGNORE INTO daily_metrics (athlete_id, date, hrv_rmssd, data_source)
                VALUES (?, ?, ?, 'garmin_api')
                """,
                (athlete_id, date, hrv),
            )
            if self._db._transaction_depth == 0:
                self._db.conn.commit()

    def save_hrr(self, date: str, hrr_60: int, hrr_120: int = 0, athlete_id: str = "owner") -> None:
        """
        Save Heart Rate Recovery values for a date.
        Updates existing daily_metrics row (call after save_daily_metric).

        Args:
            date:       Date in ISO format (YYYY-MM-DD)
            hrr_60:     BPM recovered at 60 seconds post-effort
            hrr_120:    BPM recovered at 120 seconds post-effort
            athlete_id: Athlete scope for row-level isolation (ADR-0033)
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                "UPDATE daily_metrics SET hrr_60 = ?, hrr_120 = ? WHERE athlete_id = ? AND date = ?",
                (hrr_60, hrr_120, athlete_id, date),
            )
            self._db.conn.commit()
            if cursor.rowcount == 0:
                # deferred: titan.core.database imports this module
                from titan.core.database import _database_event

                _database_event(
                    "save_hrr_no_row_updated",
                    level=logging.WARNING,
                    date=date,
                    hrr_60=hrr_60,
                    hrr_120=hrr_120,
                    athlete_id=athlete_id,
                )

    def get_hrr_history(
        self, days: int = 28, athlete_id: str = "owner"
    ) -> list[tuple[str, int, int]]:
        """
        Get HRR history for the last N days.

        Returns:
            List of (date, hrr_60, hrr_120) tuples, ordered DESC.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT date, hrr_60, hrr_120 FROM daily_metrics
                   WHERE athlete_id = ?
                   AND hrr_60 IS NOT NULL AND hrr_60 > 0
                   AND date >= date('now', '-' || ? || ' days')
                   ORDER BY date DESC""",
                (athlete_id, days),
            )
            return cursor.fetchall()

    def update_glycogen_debt(self, date: str, debt_score: float, athlete_id: str = "owner") -> None:
        """
        Persist today's glycogen debt score (0–10) to daily_metrics.
        Updates existing row for the date.

        Args:
            date:       Date in ISO format (YYYY-MM-DD)
            debt_score: Glycogen debt value (0–10)
            athlete_id: Athlete scope for row-level isolation (ADR-0033)
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                "UPDATE daily_metrics SET glycogen_debt = ? WHERE athlete_id = ? AND date = ?",
                (round(debt_score, 2), athlete_id, date),
            )
            self._db.conn.commit()
            if cursor.rowcount == 0:
                # deferred: titan.core.database imports this module
                from titan.core.database import _database_event

                _database_event(
                    "update_glycogen_debt_no_row_updated",
                    level=logging.WARNING,
                    date=date,
                    debt_score=debt_score,
                    athlete_id=athlete_id,
                )

    def get_previous_glycogen_debt(
        self, before_date: str, athlete_id: str = "owner",
    ) -> tuple[str, float] | None:
        """Return ``(date, debt)`` of the latest stored glycogen debt before *before_date*, or None."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT date, glycogen_debt FROM daily_metrics
                   WHERE athlete_id = ? AND date < ? AND glycogen_debt IS NOT NULL
                   ORDER BY date DESC LIMIT 1""",
                (athlete_id, before_date),
            )
            row = cursor.fetchone()
        return (str(row[0]), float(row[1])) if row else None

    def get_baseline_rhr(self, days: int = 7, athlete_id: str = "owner") -> float | None:
        """Return rolling N-day average resting HR from daily_metrics, or None."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
            cursor.execute(
                """SELECT AVG(resting_hr) FROM daily_metrics
                   WHERE athlete_id = ? AND date >= ? AND resting_hr IS NOT NULL AND resting_hr > 0""",
                (athlete_id, cutoff),
            )
            row = cursor.fetchone()
        if row and row[0]:
            from titan.science.physiological_bounds import (
                validate_single,  # deferred: avoids circular import
            )
            raw = round(float(row[0]), 1)
            return validate_single("rhr_bpm", raw, "baseline_rhr")
        return None

    def get_hrv_history(self, days: int = 14, athlete_id: str = "owner") -> list[tuple[str, float]]:
        """Return (date, hrv_rmssd) rows from the last N days, newest-first.

        Values are validated against physiological bounds (ADR-0023 / T1-18).
        Rows with sensor-artefact HRV (nulled by bounds check) are excluded.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT date, hrv_rmssd FROM daily_metrics
                   WHERE athlete_id = ? AND hrv_rmssd IS NOT NULL AND hrv_rmssd > 0
                   ORDER BY date DESC LIMIT ?""",
                (athlete_id, days),
            )
            rows = cursor.fetchall()

        from titan.science.physiological_bounds import (
            validate_single,  # deferred: avoids circular import
        )
        validated = []
        for date_str, rmssd in rows:
            clean = validate_single("hrv_ms", float(rmssd), "hrv_history")
            if clean is not None:
                validated.append((date_str, clean))
        return validated

    def get_recent_hrv_mean(self, days: int = 30) -> float | None:
        """Return rolling mean HRV over recent days, or None when unavailable."""
        with self._db._lock:
            hrv_history = self._db.get_hrv_history(days=days)
            if not hrv_history:
                return None
            values = [entry[1] for entry in hrv_history]
            return round(sum(values) / len(values), 2)

    def get_weight_history(self, days: int = 30, athlete_id: str = "owner") -> list[tuple[str, float]]:
        """Return (date, weight_kg) rows from the last N days, newest-first."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT date, weight_kg FROM daily_metrics
                   WHERE athlete_id = ? AND weight_kg IS NOT NULL AND weight_kg > 0
                   ORDER BY date DESC LIMIT ?""",
                (athlete_id, days),
            )
            rows = cursor.fetchall()

        from titan.science.physiological_bounds import (
            validate_single,  # deferred: avoids circular import
        )
        validated = []
        for date_str, weight_kg in rows:
            clean = validate_single("weight_kg", float(weight_kg), "weight_history")
            if clean is not None:
                validated.append((date_str, clean))
        return validated

    def get_daily_metric(self, date: str, athlete_id: str = "owner") -> dict | None:
        """Return a single daily_metrics row for *date* as a dict, or None if absent."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT date, hrv_rmssd, resting_hr, sleep_hours, weight_kg, data_source
                   FROM daily_metrics
                   WHERE athlete_id = ? AND date = ?""",
                (athlete_id, date),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "date": row[0],
            "hrv_rmssd": row[1],
            "resting_hr": row[2],
            "sleep_hours": row[3],
            "weight_kg": row[4],
            "data_source": row[5],
        }

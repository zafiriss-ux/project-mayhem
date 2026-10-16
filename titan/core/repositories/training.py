"""Training domain SQL: training log and load history (CTL/ATL/TSB), shoes
(gear_usage), personal bests and CS calibration performances."""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from titan.config.thresholds import ATL_DECAY_DAYS, CTL_DECAY_DAYS

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager


class TrainingRepository:
    """Training SQL, on the owning DatabaseManager's connection and lock."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def update_shoe_mileage(self, shoe_id: int, distance_km: float, date: str) -> None:
        """
        Update shoe mileage after a run.

        Args:
            shoe_id: ID of the shoe
            distance_km: Distance added in km
            date: Date of the run (ISO format)
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute("""
                UPDATE gear_usage
                SET total_km = total_km + ?, last_used = ?
                WHERE id = ?
            """, (distance_km, date, shoe_id))
            self._db.conn.commit()

    def add_shoe(self, name: str, shoe_type: str = "DAILY", max_km: int = 800) -> int:
        """
        Add new shoe to database.

        Args:
            name: Descriptive name (e.g., "Nike Pegasus 40")
            shoe_type: Type of shoe ("DAILY", "RACE", "RECOVERY", "TRAIL")
            max_km: Maximum recommended mileage

        Returns:
            ID of the newly added shoe
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute("""
                INSERT INTO gear_usage (shoe_name, shoe_type, max_km_limit)
                VALUES (?, ?, ?)
            """, (name, shoe_type, max_km))
            self._db.conn.commit()
        return cursor.lastrowid

    def get_active_shoes(self) -> list[tuple]:
        """
        Get all active shoes.

        Returns:
            List of tuples: (id, name, total_km, max_km, last_used, type)
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute("""
                SELECT id, shoe_name, total_km, max_km_limit, last_used, shoe_type
                FROM gear_usage
                WHERE status = 'ACTIVE'
                ORDER BY shoe_name
            """)
            return cursor.fetchall()

    def check_shoe_availability(self, shoe_id: int) -> tuple[bool, str]:
        """
        Check if shoe is available for use.

        Considers:
        1. Mileage limit (shoe lifespan)
        2. Compression recovery (24h rest for foam to decompress)

        Foam compression science:
        - EVA foam takes 24-48h to fully recover shape
        - Using shoes on consecutive days accelerates breakdown
        - Rotation extends shoe life by ~20-30%

        Args:
            shoe_id: ID of the shoe to check

        Returns:
            Tuple of (is_available, message)

        References:
            - Malisoux et al. (2013) - Shoe rotation and injury prevention
            - Kong et al. (2009) - Running shoe cushioning degradation
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute("""
                SELECT last_used, compression_recovery_hours, total_km, max_km_limit
                FROM gear_usage
                WHERE id = ?
            """, (shoe_id,))
            result = cursor.fetchone()

        if not result:
            return False, "Shoe not found"

        last_used, recovery_hours, total_km, max_km = result

        # Check mileage limit
        if total_km >= max_km:
            return False, f"Shoe exceeded mileage limit ({total_km}/{max_km} km)"

        # Check compression recovery
        if last_used:
            last_used_date = datetime.fromisoformat(last_used)
            hours_since = (datetime.now(UTC) - last_used_date).total_seconds() / 3600

            if hours_since < recovery_hours:
                hours_left = recovery_hours - hours_since
                return False, f"Foam needs {hours_left:.1f}h recovery (compression set)"

        return True, "Available"

    def save_personal_best(
        self,
        distance_km: float,
        time_sec: int,
        date: str,
        race_name: str | None = None
    ) -> None:
        """
        Save a personal best.

        Args:
            distance_km: Distance in kilometers
            time_sec: Time in seconds
            date: Date of the performance (ISO format)
            race_name: Optional race name

        Raises:
            ValueError: distance_km or time_sec is not positive (F10).
        """
        if not distance_km or distance_km <= 0 or not time_sec or time_sec <= 0:
            raise ValueError(
                f"personal best needs a positive distance and time, got "
                f"distance_km={distance_km!r}, time_sec={time_sec!r}"
            )
        pace_per_km = time_sec / distance_km

        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute("""
                INSERT INTO personal_bests
                (distance_km, time_sec, pace_sec_per_km, date, race_name)
                VALUES (?, ?, ?, ?, ?)
            """, (distance_km, time_sec, pace_per_km, date, race_name))
            self._db.conn.commit()

    def get_pr(self, distance_km: float) -> tuple[int, str, str | None] | None:
        """
        Get personal best for a distance.

        Args:
            distance_km: Distance in kilometers

        Returns:
            Tuple of (time_sec, date, race_name) or None if no PR exists
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute("""
                SELECT time_sec, date, race_name
                FROM personal_bests
                WHERE distance_km = ?
                ORDER BY time_sec ASC
                LIMIT 1
            """, (distance_km,))
            return cursor.fetchone()

    def log_cs_performance(
        self,
        date: str,
        distance_m: float,
        time_sec: float,
        surface: str = 'ROAD',
        wind_adjusted: bool = False,
        athlete_id: str = "owner",
    ) -> None:
        """
        Log a time-trial / race performance for CS/D' model calibration.

        Args:
            date:         Date in ISO format
            distance_m:   Distance in metres (e.g. 3000, 5000, 10000)
            time_sec:     Elapsed time in seconds
            surface:      ROAD / TRACK / TRAIL
            wind_adjusted: True if pace was corrected for wind
            athlete_id:   Athlete the performance belongs to (v28, D-037)
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """INSERT INTO cs_performances
                   (date, distance_m, time_sec, surface, wind_adjusted, athlete_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (date, distance_m, time_sec, surface, int(wind_adjusted), athlete_id),
            )
            self._db.conn.commit()

    def get_cs_performances(
        self, limit: int = 10, athlete_id: str = "owner"
    ) -> list[tuple[str, float, float]]:
        """
        Retrieve the athlete's most recent CS calibration performances.

        Returns:
            List of (date, distance_m, time_sec) tuples, ordered DESC.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT date, distance_m, time_sec FROM cs_performances
                   WHERE athlete_id = ?
                   ORDER BY date DESC LIMIT ?""",
                (athlete_id, limit),
            )
            return cursor.fetchall()

    def save_session(
        self,
        date: str,
        session_type: str,
        distance_km: float,
        duration_sec: int,
        avg_hr: int | None = None,
        max_hr: int | None = None,
        rpe: int | None = None,
        shoe_id: int | None = None,
        surface: str | None = None,
        temperature_c: float | None = None,
        notes: str | None = None,
        garmin_activity_id: str | None = None,
        quality_flag: str | None = None,
        training_load: int | None = None,
        athlete_id: str = "owner",
        avg_pace_sec_per_km: float | None = None,
        # Backward-compatible alias — will be removed in a future version
        temperature: float | None = None,
    ) -> None:
        """
        Save training session.

        Args:
            date:          Date in ISO format (YYYY-MM-DD)
            session_type:  Type of session (EASY, TEMPO, INTERVALS, etc.)
            distance_km:   Distance in kilometres
            duration_sec:  Duration in seconds
            avg_hr:        Average heart rate in bpm
            max_hr:        Maximum heart rate in bpm
            rpe:           Rate of Perceived Exertion (1-10 scale)
            shoe_id:       ID of shoe used
            surface:       Running surface (TRACK, ROAD, TRAIL, etc.)
            temperature_c: Air temperature in °C  ← canonical name
            notes:         Optional text notes
            garmin_activity_id: Stable Garmin external activity identity
            athlete_id:    Athlete identifier for row-level isolation (ADR-0033)
            temperature:   Deprecated alias for temperature_c

        Training Load Calculation:
            sRPE (session RPE) = RPE × duration (minutes)
            Based on Foster et al. (2001)
        """
        # Resolve deprecated alias; temperature_c takes precedence
        if temperature_c is None and temperature is not None:
            import warnings
            warnings.warn(
                "save_session(temperature=...) is deprecated; use temperature_c= instead.",
                DeprecationWarning,
                stacklevel=3,  # caller of DatabaseManager.save_session
            )
            temperature_c = temperature

        # Calculate training load: prefer explicit override, fall back to sRPE
        computed_load = (rpe * (duration_sec / 60)) if rpe else 0
        training_load = training_load if training_load is not None else int(computed_load)

        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO training_log
                (athlete_id, date, session_type, distance_km, duration_sec, avg_hr, max_hr, rpe,
                 training_load, shoe_id, surface, temperature_c, notes, garmin_activity_id,
                 quality_flag, avg_pace_sec_per_km)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (athlete_id, date, session_type, distance_km, duration_sec, avg_hr, max_hr, rpe,
                  training_load, shoe_id, surface, temperature_c, notes, garmin_activity_id,
                  quality_flag, avg_pace_sec_per_km))
            if cursor.rowcount == 1 and shoe_id and distance_km:
                cursor.execute("""
                    UPDATE gear_usage SET total_km = total_km + ?, last_used = ? WHERE id = ?
                """, (distance_km, date, shoe_id))
            if self._db._transaction_depth == 0:
                self._db.conn.commit()

    def get_recent_activities(
        self, limit: int = 90, athlete_id: str = "owner"
    ) -> list[dict]:
        """Return recent training sessions from training_log for the data browser.

        Reads from ``training_log`` (the canonical session store for all
        imported and synced activities).  The result is sorted newest-first
        so the caller can slice with ``[-N:]`` or display directly.

        Args:
            limit:      Maximum rows to return (default 90 — ~3 months).
            athlete_id: Row-level isolation key (ADR-0033).

        Returns:
            List of dicts with keys: date, session_type, distance_km,
            duration_sec, avg_hr, training_load.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """
                SELECT date, session_type, distance_km, duration_sec,
                       avg_hr, training_load, avg_pace_sec_per_km
                FROM training_log
                WHERE athlete_id = ?
                ORDER BY date DESC
                LIMIT ?
                """,
                (athlete_id, limit),
            )
            rows = cursor.fetchall()
        return [
            {
                "date": r[0],
                "session_type": r[1],
                "distance_km": r[2] or 0.0,
                "duration_sec": r[3] or 0,
                "avg_hr": r[4] or 0,
                "training_load": r[5] or 0,
                "avg_pace_sec_per_km": r[6] or 0,
            }
            for r in rows
        ]

    def get_training_load_history(
        self, days: int | None = None, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        """
        Get training load for last N days (for TSB calculation).

        Args:
            days: Number of days to retrieve (default 42 for CTL)
            athlete_id: Athlete identifier for row-level isolation (ADR-0033-L3-D-RESOLVED).

        Returns:
            List of tuples (date, training_load)
        """
        lookback_days = CTL_DECAY_DAYS if days is None else days

        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute("""
                SELECT date, SUM(training_load) as training_load
                FROM training_log
                WHERE athlete_id = ?
                  AND training_load IS NOT NULL
                  AND training_load > 0
                  AND date >= date('now', '-' || ? || ' days')
                GROUP BY date
                ORDER BY date ASC
            """, (athlete_id, lookback_days))
            rows = cursor.fetchall()

        from titan.science.physiological_bounds import (
            validate_single,  # deferred: avoids circular import
        )
        validated: list[tuple[str, float]] = []
        for date_str, training_load in rows:
            if training_load is None:
                continue
            clean = validate_single("training_load", float(training_load), "training_load_history")
            if clean is not None:
                validated.append((date_str, clean))
        return validated

    def get_ctl_atl_tsb(self, athlete_id: str = "owner") -> tuple[float, float, float]:
        """
        Calculate Training Stress Balance from database history.

        Implements the Banister/Coggan model:
        - CTL (Chronic Training Load): 42-day exponential moving average (Fitness)
        - ATL (Acute Training Load): 7-day exponential moving average (Fatigue)
        - TSB (Training Stress Balance): CTL - ATL (Form)

        TSB Interpretation:
            -10 to +5: Race ready (optimal freshness)
            -30 or lower: Overtraining risk
            +25 or higher: Detraining risk

        Returns:
            Tuple of (CTL, ATL, TSB)

        Scientific Basis:
            - Banister et al. (1975) - Systems model of training
            - Coggan (2003) - Training Stress Score/Balance
            - Busso (2003) - Variable dose-response model
        """
        with self._db._lock:
            from titan.observability.metrics import get_metrics
            from titan.science.tsb_engine import (  # deferred: avoids circular import
                LOAD_HISTORY_DAYS,
                compute_ctl_atl_tsb,
            )
            t0 = time.monotonic()
            loads = self._db.get_training_load_history(LOAD_HISTORY_DAYS, athlete_id=athlete_id)
            ctl, atl, tsb = compute_ctl_atl_tsb(
                daily_loads=loads,
                ctl_decay_days=CTL_DECAY_DAYS,
                atl_decay_days=ATL_DECAY_DAYS,
            )
            elapsed_ms = (time.monotonic() - t0) * 1000
            get_metrics().histogram("ctl_recompute_ms", elapsed_ms, {"athlete": athlete_id})
            get_metrics().gauge("tsb_value", tsb, {"athlete": athlete_id})

            from titan.science.physiological_bounds import (
                validate_single,  # deferred: avoids circular import
            )
            ctl_out = validate_single("ctl", ctl, "ctl_atl_tsb")
            atl_out = validate_single("atl", atl, "ctl_atl_tsb")
            # Return zero-safe defaults when validation nulls a value (ADR-0023 §3)
            return (
                ctl_out if ctl_out is not None else 0.0,
                atl_out if atl_out is not None else 0.0,
                tsb,
            )

    def replay_tsb(
        self,
        athlete_id: str,
        as_of_date: date,
    ) -> tuple[float, float, float]:
        from titan.science.tsb_engine import (
            replay_tsb as _replay,  # deferred: avoids circular import
        )
        return _replay(
            db=self,
            athlete_id=athlete_id,
            as_of_date=as_of_date,
        )

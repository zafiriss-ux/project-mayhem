"""Training domain SQL: shoes (gear_usage), personal bests and CS calibration
performances. The training log moves here in the next plan #18 PR."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

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
        """
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
    ) -> None:
        """
        Log a time-trial / race performance for CS/D' model calibration.

        Args:
            date:         Date in ISO format
            distance_m:   Distance in metres (e.g. 3000, 5000, 10000)
            time_sec:     Elapsed time in seconds
            surface:      ROAD / TRACK / TRAIL
            wind_adjusted: True if pace was corrected for wind
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """INSERT INTO cs_performances
                   (date, distance_m, time_sec, surface, wind_adjusted)
                   VALUES (?, ?, ?, ?, ?)""",
                (date, distance_m, time_sec, surface, int(wind_adjusted)),
            )
            self._db.conn.commit()

    def get_cs_performances(self, limit: int = 10) -> list[tuple[str, float, float]]:
        """
        Retrieve most recent CS calibration performances.

        Returns:
            List of (date, distance_m, time_sec) tuples, ordered DESC.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT date, distance_m, time_sec FROM cs_performances
                   ORDER BY date DESC LIMIT ?""",
                (limit,),
            )
            return cursor.fetchall()

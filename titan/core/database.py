"""
TITAN Database Management
Persistent storage for training data, athlete profiles, and performance metrics
"""

import contextlib
import logging
import sqlite3
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import threading

from titan.core.athlete import UniversalAthleteProfile

_log = logging.getLogger(__name__)


class DatabaseManager:
    """
    Permanent memory system for TITAN.

    Manages SQLite database for storing:
    - Daily metrics (morning check-in data)
    - Training log (complete session history)
    - Gear usage (shoe tracking with compression recovery)
    - Personal bests (PR tracking)

    Database Tables:
    1. daily_metrics: Weight, HRV, sleep, soreness, mood
    2. training_log: Complete training history with HR, RPE, load
    3. gear_usage: Shoe mileage and lifecycle management
    4. personal_bests: PR tracking by distance

    Scientific Integration:
    - CTL/ATL/TSB calculation (Banister model)
    - ACWR tracking (Gabbett, 2016)
    - Compression recovery tracking (24h foam set)
    """

    def __init__(self, db_name: str = "titan_core.db", db_dir: Optional[Path] = None):
        """
        Initialize database connection.

        Args:
            db_name: Name of the SQLite database file
            db_dir: Directory to store database (default: ~/Documents/TITAN/)

        Note:
            - Production: Database stored in ~/Documents/TITAN/ (persistent across updates)
            - Development: Can override db_dir for testing
        """
        if db_dir is None:
            # Use launcher's get_data_directory for frozen-safe path resolution
            try:
                from launcher.validator import get_data_directory
                base_dir = get_data_directory()
            except ImportError:
                # Fallback for standalone titan module usage (development)
                import os
                import platform
                if platform.system() == 'Windows':
                    base = Path(os.environ.get('USERPROFILE', Path.home()))
                else:
                    base = Path.home()
                base_dir = base / 'Documents' / 'TITAN'
        else:
            base_dir = db_dir

        # Ensure directory exists
        base_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = base_dir / db_name

        # Thread-safe connection: allow access from multiple threads
        # (Garmin sync, Telegram callback, and main thread all share one DB)
        self.conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
        )
        self._lock = threading.Lock()  # Serialise all writes

        # Enable WAL mode for concurrent read/write access
        # WAL = Write-Ahead Logging (better concurrency than default rollback journal)
        # Critical for frozen builds where multiple threads access DB simultaneously
        cursor = self.conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        journal_row = cursor.fetchone()
        journal_mode = journal_row[0] if journal_row else "WAL"

        # Setter PRAGMA may not return a row; read it explicitly afterwards.
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA synchronous")
        synchronous_row = cursor.fetchone()
        synchronous = synchronous_row[0] if synchronous_row else "NORMAL"

        # Busy timeout: wait up to 5 seconds if DB is locked
        # Prevents "database is locked" errors during concurrent access
        cursor.execute("PRAGMA busy_timeout=5000")

        # Log PRAGMA results for debugging (frozen mode validation)
        try:
            import logging
            logger = logging.getLogger('titan.database')
            logger.info(f"Database initialized: {self.db_path}")
            logger.info(f"PRAGMA journal_mode: {journal_mode}")
            logger.info(f"PRAGMA synchronous: {synchronous}")
            logger.info("PRAGMA busy_timeout: 5000")
        except Exception:
            # Best-effort logging (don't fail if logger not configured)
            pass

        self.create_tables()

    def create_tables(self) -> None:
        """Create all database tables if they don't exist."""
        self.create_database()

    def create_database(self) -> None:
        """
        Initialize database with all tables.

        Table Schemas:
        - daily_metrics: Morning wellness data
        - training_log: Session details with load calculation
        - gear_usage: Shoe tracking with compression recovery
        - personal_bests: PR history
        """
        cursor = self.conn.cursor()

        # Table 1: Daily Metrics (Morning Check-in)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL UNIQUE,
                weight_kg REAL,
                hrv_rmssd REAL,
                resting_hr INTEGER,
                sleep_hours REAL,
                sleep_quality INTEGER,
                soreness INTEGER,
                fatigue_level INTEGER,
                mood INTEGER,
                notes TEXT
            )
        """)

        # Table 2: Training Log (Complete History)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS training_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                session_type TEXT,
                distance_km REAL,
                duration_sec INTEGER,
                avg_hr INTEGER,
                max_hr INTEGER,
                rpe INTEGER,
                training_load INTEGER,
                shoe_id INTEGER,
                surface TEXT,
                temperature_c REAL,
                zone_distribution TEXT,
                notes TEXT,
                FOREIGN KEY (shoe_id) REFERENCES gear_usage(id)
            )
        """)

        # Table 3: Gear Usage (Shoe Tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS gear_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shoe_name TEXT NOT NULL,
                total_km REAL DEFAULT 0,
                last_used TEXT,
                compression_recovery_hours INTEGER DEFAULT 24,
                status TEXT DEFAULT 'ACTIVE',
                shoe_type TEXT,
                max_km_limit REAL DEFAULT 800
            )
        """)

        # Table 4: Personal Bests
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS personal_bests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                distance_km REAL NOT NULL,
                time_sec INTEGER NOT NULL,
                pace_sec_per_km REAL,
                date TEXT NOT NULL,
                race_name TEXT
            )
        """)

        # Table 5: CS Calibration Performances (Critical Speed / D' model)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cs_performances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                distance_m REAL NOT NULL,
                time_sec REAL NOT NULL,
                surface TEXT DEFAULT 'ROAD',
                wind_adjusted INTEGER DEFAULT 0
            )
        """)

        # Table 6: Override Audit Log (governance — discipline engine)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS override_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                prescribed_type TEXT,
                actual_type TEXT,
                reason TEXT
            )
        """)

        self.conn.commit()
        self._run_migrations(cursor)

    def _run_migrations(self, cursor) -> None:
        """
        Apply additive schema migrations (idempotent — safe to run on every startup).
        Wraps each ALTER TABLE in try/except to handle already-migrated databases.
        """
        new_columns = [
            "ALTER TABLE daily_metrics ADD COLUMN hrr_60 INTEGER",
            "ALTER TABLE daily_metrics ADD COLUMN hrr_120 INTEGER",
            "ALTER TABLE daily_metrics ADD COLUMN glycogen_debt REAL",
        ]
        for sql in new_columns:
            with contextlib.suppress(Exception):  # Column already exists — safe to skip
                cursor.execute(sql)
        self.conn.commit()

    # --- DAILY METRICS ---

    def save_daily_metric(
        self,
        date: str,
        weight: Optional[float] = None,
        hrv: Optional[float] = None,
        rhr: Optional[int] = None,
        sleep_hours: Optional[float] = None,
        sleep_quality: Optional[int] = None,
        soreness: Optional[int] = None,
        fatigue: Optional[int] = None,
        mood: Optional[int] = None,
        notes: Optional[str] = None
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
        """
        cursor = self.conn.cursor()

        with self._lock:
            cursor.execute("""
                INSERT OR REPLACE INTO daily_metrics
                (date, weight_kg, hrv_rmssd, resting_hr, sleep_hours, sleep_quality,
                 soreness, fatigue_level, mood, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date, weight, hrv, rhr, sleep_hours, sleep_quality, soreness, fatigue, mood, notes))
            self.conn.commit()

    # --- TRAINING LOG ---

    def save_session(
        self,
        date: str,
        session_type: str,
        distance_km: float,
        duration_sec: int,
        avg_hr: Optional[int] = None,
        max_hr: Optional[int] = None,
        rpe: Optional[int] = None,
        shoe_id: Optional[int] = None,
        surface: Optional[str] = None,
        temperature_c: Optional[float] = None,
        notes: Optional[str] = None,
        # Backward-compatible alias — will be removed in a future version
        temperature: Optional[float] = None,
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
                stacklevel=2,
            )
            temperature_c = temperature

        cursor = self.conn.cursor()

        # Calculate training load (RPE * duration in minutes)
        training_load = (rpe * (duration_sec / 60)) if rpe else 0

        with self._lock:
            cursor.execute("""
                INSERT INTO training_log
                (date, session_type, distance_km, duration_sec, avg_hr, max_hr, rpe,
                 training_load, shoe_id, surface, temperature_c, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (date, session_type, distance_km, duration_sec, avg_hr, max_hr, rpe,
                  training_load, shoe_id, surface, temperature_c, notes))
            if shoe_id and distance_km:
                cursor.execute("""
                    UPDATE gear_usage SET total_km = total_km + ?, last_used = ? WHERE id = ?
                """, (distance_km, date, shoe_id))
            self.conn.commit()

    def get_training_load_history(self, days: int = 42) -> List[Tuple[str, float]]:
        """
        Get training load for last N days (for TSB calculation).

        Args:
            days: Number of days to retrieve (default 42 for CTL)

        Returns:
            List of tuples (date, training_load)
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT date, training_load
            FROM training_log
            WHERE date >= date('now', '-' || ? || ' days')
            ORDER BY date DESC
        """, (days,))

        return cursor.fetchall()

    def get_ctl_atl_tsb(self) -> Tuple[float, float, float]:
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
        loads = self.get_training_load_history(42)

        if not loads:
            return 0.0, 0.0, 0.0

        # Training history query returns newest-first (DESC). EMA must be
        # applied oldest→newest to reflect how fitness/fatigue evolve over time.
        chronological_loads = list(reversed(loads))

        # Calculate CTL (42-day EMA)
        ctl = 0.0
        ctl_decay = 2 / (42 + 1)

        for _date, load in chronological_loads:
            ctl = (load * ctl_decay) + (ctl * (1 - ctl_decay))

        # Calculate ATL (7-day EMA, recent 7 entries)
        recent_loads = [load for _d, load in chronological_loads][-7:]
        atl = 0.0
        atl_decay = 2 / (7 + 1)

        for load in recent_loads:
            atl = (load * atl_decay) + (atl * (1 - atl_decay))

        # Calculate TSB
        tsb = ctl - atl

        return round(ctl, 1), round(atl, 1), round(tsb, 1)

    # --- GEAR MANAGEMENT ---

    def update_shoe_mileage(self, shoe_id: int, distance_km: float, date: str) -> None:
        """
        Update shoe mileage after a run.

        Args:
            shoe_id: ID of the shoe
            distance_km: Distance added in km
            date: Date of the run (ISO format)
        """
        cursor = self.conn.cursor()
        with self._lock:
            cursor.execute("""
                UPDATE gear_usage
                SET total_km = total_km + ?, last_used = ?
                WHERE id = ?
            """, (distance_km, date, shoe_id))
            self.conn.commit()

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
        cursor = self.conn.cursor()

        with self._lock:
            cursor.execute("""
                INSERT INTO gear_usage (shoe_name, shoe_type, max_km_limit)
                VALUES (?, ?, ?)
            """, (name, shoe_type, max_km))
            self.conn.commit()
        return cursor.lastrowid

    def get_active_shoes(self) -> List[Tuple]:
        """
        Get all active shoes.

        Returns:
            List of tuples: (id, name, total_km, max_km, last_used, type)
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT id, shoe_name, total_km, max_km_limit, last_used, shoe_type
            FROM gear_usage
            WHERE status = 'ACTIVE'
            ORDER BY shoe_name
        """)

        return cursor.fetchall()

    def check_shoe_availability(self, shoe_id: int) -> Tuple[bool, str]:
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
        cursor = self.conn.cursor()

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
            hours_since = (datetime.now() - last_used_date).total_seconds() / 3600

            if hours_since < recovery_hours:
                hours_left = recovery_hours - hours_since
                return False, f"Foam needs {hours_left:.1f}h recovery (compression set)"

        return True, "Available"

    # --- PERSONAL BESTS ---

    def save_personal_best(
        self,
        distance_km: float,
        time_sec: int,
        date: str,
        race_name: Optional[str] = None
    ) -> None:
        """
        Save a personal best.

        Args:
            distance_km: Distance in kilometers
            time_sec: Time in seconds
            date: Date of the performance (ISO format)
            race_name: Optional race name
        """
        cursor = self.conn.cursor()

        pace_per_km = time_sec / distance_km

        with self._lock:
            cursor.execute("""
                INSERT INTO personal_bests
                (distance_km, time_sec, pace_sec_per_km, date, race_name)
                VALUES (?, ?, ?, ?, ?)
            """, (distance_km, time_sec, pace_per_km, date, race_name))
            self.conn.commit()

    def get_pr(self, distance_km: float) -> Optional[Tuple[int, str, Optional[str]]]:
        """
        Get personal best for a distance.

        Args:
            distance_km: Distance in kilometers

        Returns:
            Tuple of (time_sec, date, race_name) or None if no PR exists
        """
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT time_sec, date, race_name
            FROM personal_bests
            WHERE distance_km = ?
            ORDER BY time_sec ASC
            LIMIT 1
        """, (distance_km,))

        return cursor.fetchone()

    # --- HRR (Heart Rate Recovery) ---

    def save_hrr(self, date: str, hrr_60: int, hrr_120: int = 0) -> None:
        """
        Save Heart Rate Recovery values for a date.
        Updates existing daily_metrics row (call after save_daily_metric).

        Args:
            date:    Date in ISO format (YYYY-MM-DD)
            hrr_60:  BPM recovered at 60 seconds post-effort
            hrr_120: BPM recovered at 120 seconds post-effort
        """
        cursor = self.conn.cursor()
        with self._lock:
            cursor.execute(
                "UPDATE daily_metrics SET hrr_60 = ?, hrr_120 = ? WHERE date = ?",
                (hrr_60, hrr_120, date),
            )
            self.conn.commit()

    def get_hrr_history(self, days: int = 28) -> List[Tuple[str, int, int]]:
        """
        Get HRR history for the last N days.

        Returns:
            List of (date, hrr_60, hrr_120) tuples, ordered DESC.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT date, hrr_60, hrr_120 FROM daily_metrics
               WHERE hrr_60 IS NOT NULL AND hrr_60 > 0
               AND date >= date('now', '-' || ? || ' days')
               ORDER BY date DESC""",
            (days,),
        )
        return cursor.fetchall()

    # --- GLYCOGEN DEBT ---

    def update_glycogen_debt(self, date: str, debt_score: float) -> None:
        """
        Persist today's glycogen debt score (0–10) to daily_metrics.
        Updates existing row for the date.
        """
        cursor = self.conn.cursor()
        with self._lock:
            cursor.execute(
                "UPDATE daily_metrics SET glycogen_debt = ? WHERE date = ?",
                (round(debt_score, 2), date),
            )
            self.conn.commit()

    # --- CS CALIBRATION PERFORMANCES ---

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
        cursor = self.conn.cursor()
        with self._lock:
            cursor.execute(
                """INSERT INTO cs_performances
                   (date, distance_m, time_sec, surface, wind_adjusted)
                   VALUES (?, ?, ?, ?, ?)""",
                (date, distance_m, time_sec, surface, int(wind_adjusted)),
            )
            self.conn.commit()

    def get_cs_performances(self, limit: int = 10) -> List[Tuple[str, float, float]]:
        """
        Retrieve most recent CS calibration performances.

        Returns:
            List of (date, distance_m, time_sec) tuples, ordered DESC.
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT date, distance_m, time_sec FROM cs_performances
               ORDER BY date DESC LIMIT ?""",
            (limit,),
        )
        return cursor.fetchall()

    # --- OVERRIDE AUDIT LOG ---

    def log_override(
        self,
        date: str,
        prescribed: str,
        actual: str,
        reason: str = '',
    ) -> None:
        """
        Record a session override (athlete deviated from prescribed session).
        Used by GovernanceEngine to calculate override_ratio.

        Args:
            date:       Date in ISO format
            prescribed: Prescribed session type (e.g. 'REST')
            actual:     Actual session performed (e.g. 'INTERVALS')
            reason:     Optional athlete-supplied reason
        """
        cursor = self.conn.cursor()
        with self._lock:
            cursor.execute(
                """INSERT INTO override_log (date, prescribed_type, actual_type, reason)
                   VALUES (?, ?, ?, ?)""",
                (date, prescribed, actual, reason),
            )
            self.conn.commit()

    def get_override_ratio(self, days: int = 14) -> float:
        """
        Calculate the fraction of days in the last N days with an override.

        Returns:
            Float 0.0–1.0 (1.0 = overrode every day in the window).
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT COUNT(*) FROM override_log
               WHERE date >= date('now', '-' || ? || ' days')""",
            (days,),
        )
        row = cursor.fetchone()
        overrides = row[0] if row else 0
        return round(overrides / days, 3)

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()


class AthleteDatabase:
    """
    Multi-athlete management with JSON storage.

    Manages multiple athlete profiles with file-based persistence.
    Each athlete is stored as a separate JSON file for easy portability.

    Directory Structure:
        athletes/
        ├── ATH_20260213120000.json
        ├── ATH_20260213120100.json
        └── ...
    """

    def __init__(self, db_path: str = "athletes"):
        """
        Initialize athlete database.

        Args:
            db_path: Directory name for athlete storage
        """
        # Get the directory where the script is running
        try:
            base_dir = Path(__file__).parent.parent.parent.absolute()
        except NameError:
            # Fallback for IDLE/Jupyter
            base_dir = Path.cwd()

        self.db_path = base_dir / db_path
        self.db_path.mkdir(exist_ok=True)
        self.athletes: Dict[str, UniversalAthleteProfile] = {}
        self.current_athlete_id: Optional[str] = None
        self.load_all()

    def create_athlete(
        self,
        name: str,
        gender: str,
        age: int,
        height_cm: float,
        weight_kg: float
    ) -> UniversalAthleteProfile:
        """
        Create a new athlete profile.

        Args:
            name: Athlete's name
            gender: "M" or "F"
            age: Age in years
            height_cm: Height in centimeters
            weight_kg: Weight in kilograms

        Returns:
            Created UniversalAthleteProfile instance
        """
        profile = UniversalAthleteProfile(name=name)
        profile.set_demographics(gender, age, height_cm, weight_kg)

        self.athletes[profile.athlete_id] = profile
        self.current_athlete_id = profile.athlete_id
        self.save_athlete(profile)

        return profile

    def switch_athlete(self, athlete_id: str) -> Optional[UniversalAthleteProfile]:
        """
        Switch to a different athlete.

        Args:
            athlete_id: ID of the athlete to switch to

        Returns:
            UniversalAthleteProfile instance or None if not found
        """
        if athlete_id in self.athletes:
            self.current_athlete_id = athlete_id
            return self.athletes[athlete_id]
        return None

    def get_current(self) -> Optional[UniversalAthleteProfile]:
        """
        Get current active athlete.

        Returns:
            UniversalAthleteProfile instance or None if no athlete selected
        """
        if self.current_athlete_id and self.current_athlete_id in self.athletes:
            return self.athletes[self.current_athlete_id]
        return None

    def list_all(self) -> List[Dict[str, Any]]:
        """
        List all athletes with basic info.

        Returns:
            List of dictionaries with athlete summary data
        """
        athletes_list = []
        for aid, prof in self.athletes.items():
            athletes_list.append({
                "id": aid,
                "name": prof.name,
                "age": prof.age,
                "gender": prof.gender,
                "goal": prof.current_goal
            })
        return athletes_list

    def save_athlete(self, profile: UniversalAthleteProfile) -> None:
        """
        Save athlete profile to JSON file.

        Args:
            profile: UniversalAthleteProfile to save
        """
        filepath = self.db_path / f"{profile.athlete_id}.json"
        with open(filepath, 'w') as f:
            json.dump(profile.to_dict(), f, indent=2)

    def load_all(self) -> None:
        """Load all athlete profiles from disk."""
        if not self.db_path.exists():
            return

        for filepath in self.db_path.glob("*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                self._validate_profile_schema(data)
                profile = UniversalAthleteProfile.from_dict(data)
                self.athletes[profile.athlete_id] = profile
            except Exception as e:
                _log.warning("Skipped corrupted athlete file: %s (%s)", filepath.name, type(e).__name__)

    @staticmethod
    def _validate_profile_schema(data: Any) -> None:

        """Lightweight schema validation before profile deserialization."""
        if not isinstance(data, dict):
            raise TypeError("Athlete profile must be a JSON object")

        athlete_id = data.get("athlete_id")
        if not isinstance(athlete_id, str) or not athlete_id.strip():
            raise ValueError("Invalid field: athlete_id")

        typed_fields = {
            "name": str,

        """Validate shape/types for athlete JSON before profile deserialization."""
        if not isinstance(data, dict):
            raise TypeError("Athlete profile must be a JSON object")

        required_fields = {
            "athlete_id": str,
            "name": str,
        }
        for field, expected_type in required_fields.items():
            value = data.get(field)
            if not isinstance(value, expected_type) or not value.strip():
                raise ValueError(f"Invalid field: {field}")

        typed_fields = {

            "gender": str,
            "age": int,
            "height_cm": (int, float),
            "weight_kg": (int, float),
            "resting_hr": int,
            "max_hr": int,
            "threshold_hr": int,
            "vo2_max": (int, float),
            "race_day": str,
            "current_goal": str,
            "target_time": str,
            "personal_bests": dict,
            "weight_floor": (int, float),
            "paces": dict,
            "critical_speed_m_per_s": (int, float),
            "d_prime_m": (int, float),
        }
        for field, expected_type in typed_fields.items():

            value = data.get(field)
            if value is not None and not isinstance(value, expected_type):
                raise TypeError(f"Invalid type for field: {field}")

        race_day = data.get("race_day")
        if race_day:
            datetime.fromisoformat(race_day)

            if field in data and data[field] is not None and not isinstance(data[field], expected_type):
                raise TypeError(f"Invalid type for field: {field}")

        if "race_day" in data and data["race_day"] is not None:
            datetime.fromisoformat(data["race_day"])


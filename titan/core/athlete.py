"""
TITAN Athlete Profile Module
Complete athlete demographics, physiology, and training data
"""

import logging
from datetime import UTC, date, datetime
from itertools import count
from typing import Any
from uuid import uuid4

_log = logging.getLogger(__name__)

_ATHLETE_ID_SEQUENCE = count()

OWNER_ATHLETE_ID = "owner"

# One set of profile limits for the owner's console editor and the athlete_profiles table
# (#911, ADR-0067 D5.1). Inclusive bounds.
VALID_TRAINING_PHASES: frozenset[str] = frozenset({"BASE", "BUILD", "PEAK", "TAPER"})
VALID_TRAINING_GOALS: frozenset[str] = frozenset({"5K", "10K", "HM", "M"})
PROFILE_LIMITS: dict[str, tuple[float, float]] = {
    "age": (10, 100),
    "weight_kg": (20.0, 300.0),
    "height_cm": (100, 250),
    "max_hr": (100, 220),
    "threshold_hr": (80, 210),
}
MIN_ATHLETE_AGE = 18  # an athlete other than the owner is an adult (ADR-0067 D5.1)
PROFILE_FIELDS: tuple[str, ...] = (
    "birth_date", "sex", "weight_kg", "height_cm", "max_hr", "threshold_hr",
    "training_phase", "training_goal", "location_city", "location_country",
)


# Consent (ADR-0067 D4). The text of each version is docs/consent/<version>.md; a new version
# means a new file and a new value here, and nobody counts as consenting to it until they agree.
CONSENT_TYPE = "coaching"
CONSENT_TEXT_VERSION = "v1"
CONSENT_FREEZE_DAYS = 30  # after /stop: frozen, then deleted (D4.3); re-consent only within it (D4.4)


def _utc_day(timestamp: str) -> date:
    return datetime.fromisoformat(timestamp).astimezone(UTC).date()


def consent_is_current(rows: list[dict[str, Any]], today: date) -> bool:
    """True when the athlete may be coached on ``today`` (UTC) under ADR-0067 D4.

    A row counts only for CONSENT_TEXT_VERSION and only while not revoked. A consent given
    after a /stop takes effect from the next UTC day (D4.4); a first consent from its own day.
    """
    revocations = [_utc_day(row["revoked_at"]) for row in rows if row.get("revoked_at")]
    for row in rows:
        if row.get("revoked_at") or row.get("text_version") != CONSENT_TEXT_VERSION:
            continue
        granted = _utc_day(row["granted_at"])
        resumed = any(day <= granted for day in revocations)
        if (granted < today) if resumed else (granted <= today):
            return True
    return False


class AthleteNotReady(Exception):
    """The athlete cannot be coached: nothing may run or be called for them (ADR-0067 D7.1)."""

    def __init__(self, athlete_id: str, reason: str) -> None:
        super().__init__(f"athlete {athlete_id} is not ready: {reason}")
        self.athlete_id = athlete_id
        self.reason = reason


def age_on(birth_date: date, today: date) -> int:
    """Whole years from birth_date to today."""
    return today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))


def profile_problems(record: dict[str, Any], today: date) -> list[str]:
    """Every reason the athlete_profiles record cannot be used; empty when it is complete.

    A missing field is a problem: nothing falls back to a default (ADR-0067 D5.1, D5.3).
    """
    problems = [f"{field}: missing" for field in PROFILE_FIELDS if record.get(field) in (None, "")]
    if problems:
        return problems
    try:
        born = date.fromisoformat(str(record["birth_date"]))
    except ValueError:
        return ["birth_date: not an ISO date"]
    age = age_on(born, today)
    if age < MIN_ATHLETE_AGE:
        problems.append(f"birth_date: under {MIN_ATHLETE_AGE}")
    elif not PROFILE_LIMITS["age"][0] <= age <= PROFILE_LIMITS["age"][1]:
        problems.append("birth_date: age out of range")
    if record["sex"] not in ("M", "F"):
        problems.append("sex: must be M or F")
    for field in ("weight_kg", "height_cm", "max_hr", "threshold_hr"):
        lo, hi = PROFILE_LIMITS[field]
        try:
            value = float(record[field])
        except (TypeError, ValueError):
            problems.append(f"{field}: not a number")
            continue
        if not lo <= value <= hi:
            problems.append(f"{field}: must be between {lo} and {hi}")
    if str(record["training_phase"]).upper() not in VALID_TRAINING_PHASES:
        problems.append("training_phase: unknown")
    if str(record["training_goal"]).upper() not in VALID_TRAINING_GOALS:
        problems.append("training_goal: unknown")
    return problems


class UniversalAthleteProfile:
    """
    Complete athlete demographics and physiology.
    Replaces old TitanProfile with multi-athlete support.

    Manages all athlete-specific data including:
    - Demographics (age, gender, height, weight)
    - Physiological markers (HR, VO2max, thresholds)
    - Training paces and zones
    - Critical Speed and D' (anaerobic work capacity)
    - Personal bests and race goals

    Attributes:
        athlete_id: Unique identifier for the athlete
        name: Athlete's name
        gender: "M" or "F"
        age: Age in years
        height_cm: Height in centimeters
        weight_kg: Current weight in kilograms
        resting_hr: Resting heart rate (bpm)
        max_hr: Maximum heart rate (bpm)
        threshold_hr: Lactate threshold heart rate (bpm)
        vo2_max: VO2max in ml/kg/min
        race_day: Upcoming race date
        current_goal: Current training goal description
        target_time: Target race time
        personal_bests: Dictionary of PRs by distance
    """

    def __init__(self, athlete_id: str | None = None, name: str = "Default Athlete"):
        """
        Initialize athlete profile.

        Args:
            athlete_id: Unique identifier (auto-generated if None)
            name: Athlete's name
        """
        self.athlete_id = athlete_id or (
            f"ATH_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}{next(_ATHLETE_ID_SEQUENCE):04d}"
        )
        self.name = name

        # Demographics
        self.gender = "M"  # M/F
        self.age = 43
        self.height_cm = 180
        self.weight_kg = 75.0

        # Physiological markers
        self.resting_hr = 44
        self.max_hr = 191
        self.threshold_hr = 168
        self.vo2_max = 58.5

        # Training goals
        self.race_day = datetime(2026, 4, 26)
        self.current_goal = None
        self.target_time = None
        self.base_5k_time_str = "19:00"
        self.base_5k_sec = 228.0

        # Weight management
        self.weight_floor = 75.0
        self.weight_ceiling = 76.2
        self.weight_panic = 74.5

        # Training paces (min/km format)
        self.paces = {
            "EASY": "5:31",
            "LONG_RUN": "5:08",
            "TEMPO": "4:06",
            "VO2_MAX": "3:43",
            "HAMMER": "3:45-3:55",
            "RECOVERY": "6:00+"
        }

        # Critical Speed Model (Monod & Scherrer, 1965)
        # CS = sustainable speed indefinitely (theoretically)
        # D' = finite anaerobic work capacity above CS
        self.critical_speed_m_per_s = 4.1  # meters per second
        self.d_prime_m = 250.0  # meters (anaerobic capacity)

        # Personal bests
        self.personal_bests = {}

        # Metadata
        self.created_date = datetime.now(UTC)
        self.last_modified = datetime.now(UTC)

    # --- COMPATIBILITY BRIDGE ---
    # Maintains backward compatibility with legacy code
    @property
    def resting_hr_baseline(self) -> int:
        """Alias for resting_hr (backward compatibility)."""
        return self.resting_hr

    @resting_hr_baseline.setter
    def resting_hr_baseline(self, value: int):
        """Alias for resting_hr setter."""
        self.resting_hr = value

    @property
    def vo2_max_baseline(self) -> float:
        """Alias for vo2_max (backward compatibility)."""
        return self.vo2_max

    # --- PROFILE MANAGEMENT METHODS ---

    def set_demographics(
        self,
        gender: str,
        age: int,
        height_cm: float,
        weight_kg: float
    ) -> None:
        """
        Update athlete demographics.

        Args:
            gender: "M" or "F"
            age: Age in years
            height_cm: Height in centimeters
            weight_kg: Weight in kilograms
        """
        self.gender = gender.upper()
        self.age = age
        self.height_cm = height_cm
        self.weight_kg = weight_kg

        # Auto-calculate weight management thresholds
        if weight_kg:
            self.weight_floor = weight_kg - 0.5
            self.weight_ceiling = weight_kg + 1.2
            self.weight_panic = weight_kg - 1.5

        self.last_modified = datetime.now(UTC)

    def set_hr_data(
        self,
        resting_hr: int,
        max_hr: int | None = None
    ) -> None:
        """
        Update heart rate data and calculate threshold.

        Args:
            resting_hr: Resting heart rate in bpm
            max_hr: Maximum heart rate (calculated if None using age formula)
        """
        self.resting_hr = resting_hr

        if max_hr:
            self.max_hr = max_hr
        elif self.age:
            # Tanaka formula: HRmax = 208 - (0.7 × age)
            # More accurate than 220-age for trained athletes
            self.max_hr = int(208 - (0.7 * self.age))

        if self.max_hr:
            # Threshold HR typically ~88% of max HR
            self.threshold_hr = int(self.max_hr * 0.88)

        self.last_modified = datetime.now(UTC)

    def calculate_bmr(self) -> int:
        """
        Calculate Basal Metabolic Rate.

        Returns:
            BMR in kcal/day

        Note: Currently returns manual override value (2020 kcal).
        To use Mifflin-St Jeor equation, uncomment the formula below.
        """
        # Manual override for specific user
        return 2020

    def calculate_tdee(self) -> int:
        """
        Calculate Total Daily Energy Expenditure.

        Returns:
            TDEE in kcal/day

        Note: Currently returns manual override (2800 kcal max).
        """
        # Manual override for specific user
        return 2800

        # Activity multipliers:
        # bmr = self.calculate_bmr()
        # if not bmr:
        #     return None
        # multipliers = {
        #     "sedentary": 1.2,      # Little/no exercise
        #     "light": 1.375,        # 1-3 days/week
        #     "moderate": 1.55,      # 3-5 days/week
        #     "active": 1.725,       # 6-7 days/week
        #     "very_active": 1.9     # 2x per day training
        # }
        # return int(bmr * multipliers.get(activity_level, 1.725))

    # --- UTILITY METHODS ---

    @staticmethod
    def str_to_sec(time_str: str) -> int:
        """
        Convert time string to seconds.

        Args:
            time_str: Time in format "MM:SS" or "HH:MM:SS"

        Returns:
            Total seconds
        """
        try:
            parts = time_str.split(':')
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except Exception:
            return 0
        return 0

    @staticmethod
    def sec_to_str(seconds: int) -> str:
        """
        Convert seconds to time string.

        Args:
            seconds: Total seconds

        Returns:
            Time string in format "MM:SS"
        """
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"

    # --- SERIALIZATION METHODS ---

    def to_context(self) -> dict[str, Any]:
        """The athlete_profile entry of TitanContext (orchestration.contracts.AthleteProfile).

        The one place that projects this profile onto the coaching context, so the
        context never carries values of its own (T5-117).
        """
        return {
            "name": self.name,
            "age": self.age,
            "weight_kg": self.weight_kg,
            "height_cm": float(self.height_cm),
            "max_hr": self.max_hr,
            "threshold_hr": self.threshold_hr,
            "phase": self.training_phase,
            "goal": self.current_goal or "",
        }

    def to_dict(self) -> dict[str, Any]:
        """
        Convert profile to dictionary for JSON serialization.

        Returns:
            Dictionary containing all profile data
        """
        return {
            "athlete_id": self.athlete_id,
            "name": self.name,
            "gender": self.gender,
            "age": self.age,
            "height_cm": self.height_cm,
            "weight_kg": self.weight_kg,
            "resting_hr": self.resting_hr,
            "max_hr": self.max_hr,
            "threshold_hr": self.threshold_hr,
            "vo2_max": self.vo2_max,
            "race_day": self.race_day.isoformat() if self.race_day else None,
            "current_goal": self.current_goal,
            "target_time": self.target_time,
            "personal_bests": self.personal_bests,
            "weight_floor": self.weight_floor,
            "weight_ceiling": self.weight_ceiling,
            "weight_panic": self.weight_panic,
            "paces": self.paces,
            "critical_speed_m_per_s": self.critical_speed_m_per_s,
            "d_prime_m": self.d_prime_m
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'UniversalAthleteProfile':
        """
        Create profile from dictionary.

        Args:
            data: Dictionary containing profile data

        Returns:
            UniversalAthleteProfile instance
        """
        profile = cls(
            athlete_id=data.get("athlete_id"),
            name=data.get("name", "Default Athlete")
        )

        # Load demographics
        profile.gender = data.get("gender", "M")
        profile.age = data.get("age")
        profile.height_cm = data.get("height_cm")
        profile.weight_kg = data.get("weight_kg")

        # Load physiological data
        profile.resting_hr = data.get("resting_hr", 44)
        profile.max_hr = data.get("max_hr", 191)
        profile.threshold_hr = data.get("threshold_hr", 168)
        profile.vo2_max = data.get("vo2_max")

        # Load training data
        if data.get("race_day"):
            profile.race_day = datetime.fromisoformat(data["race_day"])
        profile.current_goal = data.get("current_goal")
        profile.target_time = data.get("target_time")
        profile.personal_bests = data.get("personal_bests", {})
        profile.weight_floor = data.get("weight_floor", 75.0)
        profile.weight_ceiling = data.get("weight_ceiling", 76.2)
        profile.weight_panic = data.get("weight_panic", 74.5)
        profile.paces = data.get("paces", profile.paces)
        profile.critical_speed_m_per_s = data.get("critical_speed_m_per_s", 4.1)
        profile.d_prime_m = data.get("d_prime_m", 250.0)

        return profile

    @classmethod
    def from_env(cls) -> "UniversalAthleteProfile":
        """Construct profile from environment variables.
        Falls back to physiologically safe defaults
        when vars are absent."""
        import os
        import sys

        _defaults = cls()

        def _parse(var: str, default, caster):
            raw = os.environ.get(var, str(default))
            try:
                return caster(raw)
            except (TypeError, ValueError):
                _log.error(
                    "startup_env_invalid",
                    extra={
                        "var": var,
                        "raw": raw,
                        "expected": caster.__name__,
                    },
                )
                sys.exit(1)

        profile = cls(name=os.environ.get("ATHLETE_NAME", "Athlete"))
        profile.age = _parse("ATHLETE_AGE", _defaults.age, int)
        profile.weight_kg = _parse("ATHLETE_WEIGHT", _defaults.weight_kg, float)
        profile.height_cm = _parse("ATHLETE_HEIGHT", _defaults.height_cm, float)
        profile.max_hr = _parse("ATHLETE_MAX_HR", _defaults.max_hr, int)
        profile.threshold_hr = _parse("ATHLETE_THRESHOLD_HR", _defaults.threshold_hr, int)
        profile.training_phase = os.environ.get("TRAINING_PHASE", "BUILD")
        profile.current_goal = os.environ.get("TRAINING_GOAL", "5K")
        return profile

    @classmethod
    def from_record(
        cls, athlete_id: str, display_name: str, record: dict[str, Any], *, today: date
    ) -> "UniversalAthleteProfile":
        """The profile of an athlete other than the owner, from their athlete_profiles row.

        Only stored values are used. Every value the constructor carries for the owner
        (resting HR, VO2max, paces, race day, Critical Speed) is cleared, so this athlete
        never receives the owner's values (ADR-0067 D7.1). Raises AthleteNotReady when
        the record is incomplete or out of range.
        """
        problems = profile_problems(record, today)
        if problems:
            raise AthleteNotReady(athlete_id, "; ".join(problems))
        profile = cls(athlete_id=athlete_id, name=display_name)
        profile.set_demographics(
            str(record["sex"]),
            age_on(date.fromisoformat(str(record["birth_date"])), today),
            float(record["height_cm"]),
            float(record["weight_kg"]),
        )
        profile.birth_date = str(record["birth_date"])
        profile.max_hr = int(record["max_hr"])
        profile.threshold_hr = int(record["threshold_hr"])
        profile.training_phase = str(record["training_phase"]).upper()
        profile.current_goal = str(record["training_goal"]).upper()
        profile.location_city = str(record["location_city"])
        profile.location_country = str(record["location_country"])
        profile.resting_hr = None
        profile.vo2_max = None
        profile.race_day = None
        profile.base_5k_time_str = None
        profile.base_5k_sec = None
        profile.paces = {}
        profile.critical_speed_m_per_s = None
        profile.d_prime_m = None
        return profile


def load_athlete_profile(db: Any, athlete_id: str, *, today: date | None = None) -> UniversalAthleteProfile:
    """The profile the morning uses for ``athlete_id`` (ADR-0067 D5, Phase 4 step 3).

    The owner reads ``.env`` as before (from_env). Any other athlete reads their
    athlete_profiles row; with no row, or an incomplete one, AthleteNotReady is raised
    before anything is built or called.
    """
    if athlete_id == OWNER_ATHLETE_ID:
        return UniversalAthleteProfile.from_env()
    stored = db.get_athlete_profile(athlete_id)
    if stored is None:
        raise AthleteNotReady(athlete_id, "no profile")
    display_name, record = stored
    return UniversalAthleteProfile.from_record(
        athlete_id, display_name, record, today=today or datetime.now(UTC).date()
    )

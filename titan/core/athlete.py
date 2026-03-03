"""
TITAN Athlete Profile Module
Complete athlete demographics, physiology, and training data
"""

from datetime import datetime
from typing import Any


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
        self.athlete_id = athlete_id or f"ATH_{datetime.now().strftime('%Y%m%d%H%M%S')}"
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
        self.created_date = datetime.now()
        self.last_modified = datetime.now()

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

        self.last_modified = datetime.now()

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

        self.last_modified = datetime.now()

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

        # Mifflin-St Jeor Equation:
        # Men: BMR = (10 × weight) + (6.25 × height) - (5 × age) + 5
        # Women: BMR = (10 × weight) + (6.25 × height) - (5 × age) - 161
        # if not all([self.weight_kg, self.height_cm, self.age]):
        #     return None
        # bmr = (10 * self.weight_kg) + (6.25 * self.height_cm) - (5 * self.age)
        # if self.gender == "M":
        #     bmr += 5
        # else:
        #     bmr -= 161
        # return int(bmr)

    def calculate_tdee(self, activity_level: str = "active") -> int:
        """
        Calculate Total Daily Energy Expenditure.

        Args:
            activity_level: One of "sedentary", "light", "moderate", "active", "very_active"

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
            elif len(parts) == 3:
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
        profile.paces = data.get("paces", profile.paces)

        return profile

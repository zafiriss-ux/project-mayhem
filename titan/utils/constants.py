"""
TITAN Core Constants and Configuration
Session types, HR zones, and system-wide constants
"""


class _Secret(str):
    """String subclass για sensitive δεδομένα (credentials).

    Η τιμή λειτουργεί κανονικά ως string σε όλες τις κλήσεις API,
    αλλά εμφανίζεται ως '***' σε repr/tracebacks ώστε να μην
    εκτίθεται σε logs ή exception messages.
    """
    __slots__ = ()

    def __repr__(self) -> str:
        return "'***'"


# Default Configuration
DEFAULT_CONFIG = {
    'hr_zones': {
        'z1': (0, 60),
        'z2': (60, 70),
        'z3': (70, 80),
        'z4': (80, 90),
        'z5': (90, 100)
    },
    'acwr': {
        'safe_min': 0.8,
        'safe_max': 1.3
    },
    'db_version': '1.0',
    'weather_timeout': 10
}

# Session Types
SESSION_TYPES = [
    "EASY",
    "LONG_RUN",
    "TEMPO",
    "INTERVALS",
    "VO2_MAX",
    "HAMMER",
    "RECOVERY",
    "PROGRESSIVE",
    "RACE"
]

# Training Intensity Categories
EASY_SESSIONS = ["EASY", "RECOVERY", "RECOVERY_EASY"]
MODERATE_SESSIONS = ["TEMPO", "LONG_RUN", "PROGRESSIVE"]
HARD_SESSIONS = ["INTERVALS", "VO2_MAX", "HAMMER"]

# HR Zone Thresholds (% of max HR)
HR_ZONE_RANGES = {
    'Z1': (0, 60),      # Recovery
    'Z2': (60, 70),     # Easy aerobic
    'Z3': (70, 80),     # Moderate aerobic
    'Z4': (80, 90),     # Threshold
    'Z5': (90, 100)     # VO2max / Anaerobic
}

# Weight Management Constants
WEIGHT_FLOOR_DEFAULT = 75.0  # kg
WEIGHT_PANIC_THRESHOLD = 74.5  # kg
NIGHT_DROP_ALERT = 1.2  # kg
WEIGHT_DROP_CRITICAL = 1.2  # % drop

# EPOC (Excess Post-exercise Oxygen Consumption) Thresholds
EPOC_OVERRIDE_THRESHOLD = 350  # kcal

# Training Load Constants
ACWR_INJURY_RISK = 1.5  # >1.5 = 2-4x injury risk

# TSB (Training Stress Balance) Ranges
TSB_RACE_READY_MIN = -10
TSB_RACE_READY_MAX = 5
TSB_OVERTRAINED = -30

# CTL/ATL Time Constants
CTL_DAYS = 42  # Chronic Training Load (fitness)
ATL_DAYS = 7   # Acute Training Load (fatigue)

# HRV Status Thresholds
HRV_STATUS_LOW = "LOW"
HRV_STATUS_NORMAL = "NORMAL"
HRV_STATUS_HIGH = "HIGH"

# Sleep Quality Thresholds
SLEEP_CRITICAL = 60
SLEEP_SUBOPTIMAL = 65

# Pain/Soreness Scale
PAIN_CRITICAL = 3  # 0-5 scale
PAIN_ELEVATED = 2

# HR Drift / Decoupling
HR_DRIFT_EXCELLENT = 5.0  # % - Less than 5% is excellent aerobic base
HR_DRIFT_WARNING = 10.0   # % - More than 10% indicates decoupling

# Shoe/Equipment Constants
SHOE_MAX_KM_DEFAULT = 800
SHOE_COMPRESSION_RECOVERY_HOURS = 24

# Glycogen Depletion Estimates (kcal/km at different intensities)
GLYCOGEN_COST_EASY = 60  # kcal/km
GLYCOGEN_COST_TEMPO = 75  # kcal/km
GLYCOGEN_COST_HARD = 90   # kcal/km

# Training Phase Days
PHASE_TAPER_DAYS = 10
PHASE_PEAK_DAYS = 35
PHASE_BUILD_DAYS = 70

# Database defaults
DB_NAME_DEFAULT = "titan_core.db"
ATHLETE_DB_PATH = "athletes"

# Logging
LOG_DIR = "logs"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5MB
LOG_BACKUP_COUNT = 3

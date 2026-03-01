import math
from datetime import datetime, timedelta
import json
from pathlib import Path

# --- ΕΛΕΓΧΟΣ ΒΙΒΛΙΟΘΗΚΩΝ ---
try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from sklearn.ensemble import RandomForestRegressor
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    
# ==============================================================================
# TITAN OS v47 "THE COMPLETE SCIENTIFIC ENGINE"
# - Norwegian / Kenyan / Polarized Training Kernel
# - Critical Speed & D Engine
# - HR Drift / Decoupling Engine
# - Session Density Index
# - Explicit Fatigue Buckets
# - Lactate Logic (LT1 / LT2 without lactate meter)
# - Mechanical Load / Injury Risk Proxy
# - Glycogen State Awareness
# - Adaptive Memory (Zones / Loads / Readiness)
# - Medical / Nutrition / Heat / Post-Race Evolution
#
# ===== v46 FEATURES =====
#  Decision Rules Engine (Seiler / Mujika)
#  Neuromuscular Load Management (Norwegian / Ingebrigtsen)
#  Fuel Timing Matrix (Jeukendrup / Burke)
#  Daily Monitoring System
#  Race Week Entropy Engine
#
# ===== NEW IN v47: COMPLETE SCIENCE INTEGRATION =====
#  TIER 1 - INJURY PREVENTION & LOAD MANAGEMENT:
#     ACWR (Acute:Chronic Workload Ratio) - Gabbett (2016)
#       - Sweet spot: 0.8-1.3 (optimal adaptation)
#       - >1.5 = 2-4x injury risk increase
#     TSB/CTL/ATL (Training Stress Balance) - Banister/Coggan
#       - CTL = Chronic Training Load (42-day fitness)
#       - ATL = Acute Training Load (7-day fatigue)
#       - TSB = Form (-10 to +5 = race ready)
#     HRV-Guided Training - Kiviniemi (2007), Plews (2013)
#       - Auto-adjust sessions based on morning HRV
#       - 8.3% vs 5.6% VO2max improvement
#
#  TIER 2 - PERFORMANCE TRACKING:
#     Durability Index - Maunder et al. (2021)
#       - How well you maintain pace when fatigued
#       - Fresh vs depleted performance ratio
#       - The "new frontier" in endurance science
#     Efficiency Factor (EF) - Friel (2009), Esteve-Lanao (2005)
#       - Speed/HR ratio (aerobic fitness proxy)
#       - Decoupling <5% = excellent aerobic base
#       - Track improvements week-to-week
#
#  TIER 3 - ADVANCED METRICS:
#     TRIMP (Training Impulse) - Banister (1975), Edwards (1993)
#       - HR-weighted load quantification
#       - Better than simple volume/duration
#     RCP Detection (Respiratory Compensation Point) - Meyer (2005)
#       - More precise than LTHR for threshold work
#       - Field-test based estimation
#     Session RPE (sRPE) - Foster (2001)
#       - Simple: Duration  RPE
#       - r=0.85 correlation with TRIMP
#     Glycogen Depletion Model - Impellizzeri & Marcora (2007)
#       - Estimate glycogen cost per session
#       - Refueling recommendations
#
#  SCIENTIFIC REFERENCES (28 peer-reviewed studies):
# See documentation for complete bibliography
# ==============================================================================

# ------------------------------------------------------------------------------
# PROFILE & CONSTANTS
# ------------------------------------------------------------------------------


# ============================================================================
# CRITICAL ENHANCEMENTS
# ============================================================================
from sklearn.preprocessing import StandardScaler
import logging
from logging.handlers import RotatingFileHandler
import os

# Logging setup
if not os.path.exists('logs'): os.makedirs('logs')
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                    handlers=[RotatingFileHandler('logs/titan.log', maxBytes=5*1024*1024, backupCount=3), logging.StreamHandler()])
logger = logging.getLogger('TITAN')

# Configuration
DEFAULT_CONFIG = {'hr_zones':{'z1':(0,60),'z2':(60,70),'z3':(70,80),'z4':(80,90),'z5':(90,100)}, 'acwr':{'safe_min':0.8,'safe_max':1.3}, 'db_version':'1.0', 'weather_timeout':10}
try:
    with open('config.json','r') as cf: CONFIG=json.load(cf)
    logger.info('Config loaded')
except: CONFIG=DEFAULT_CONFIG

class UniversalAthleteProfile:
    """
    Complete athlete demographics and physiology
    Replaces old TitanProfile with multi-athlete support
    Corrected & Bridged for TITAN v48
    """
    
    def __init__(self, athlete_id=None, name="Default Athlete"):
        self.athlete_id = athlete_id or f"ATH_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.name = name
        
        # Demographics
        self.gender = "M"  # M/F
        self.age = 43
        self.height_cm = 180
        self.weight_kg = 75.0
        
        # Physiological
        self.resting_hr = 44
        self.max_hr = 191
        self.threshold_hr = 168
        self.vo2_max = 58.5
        
        # Training
        self.race_day = datetime(2026, 4, 26)
        self.current_goal = None
        self.target_time = None
        self.base_5k_time_str = "19:00"
        self.base_5k_sec = 228.0
        
        # Weight management
        self.weight_floor = 75.0
        self.weight_ceiling = 76.2
        self.weight_panic = 74.5
        
        # Pacing
        self.paces = {
            "EASY": "5:31",
            "LONG_RUN": "5:08",
            "TEMPO": "4:06",
            "VO2_MAX": "3:43",
            "HAMMER": "3:45-3:55",
            "RECOVERY": "6:00+"
        }
        
        # Critical Speed
        self.critical_speed_m_per_s = 4.1
        self.d_prime_m = 250.0
        
        # Personal bests
        self.personal_bests = {}
        
        # Metadata
        self.created_date = datetime.now()
        self.last_modified = datetime.now()

    # --- COMPATIBILITY BRIDGE (Η Σωτηρία για τα Menu 1, 7, 14) ---
    @property
    def resting_hr_baseline(self):
        return self.resting_hr
    
    @resting_hr_baseline.setter
    def resting_hr_baseline(self, value):
        self.resting_hr = value
        
    @property
    def vo2_max_baseline(self):
        return self.vo2_max
    # -------------------------------------------------------------
    
    def set_demographics(self, gender, age, height_cm, weight_kg):
        self.gender = gender.upper()
        self.age = age
        self.height_cm = height_cm
        self.weight_kg = weight_kg
        if weight_kg:
            self.weight_floor = weight_kg - 0.5
            self.weight_ceiling = weight_kg + 1.2
            self.weight_panic = weight_kg - 1.5
        self.last_modified = datetime.now()
    
    def set_hr_data(self, resting_hr, max_hr=None):
        self.resting_hr = resting_hr
        if max_hr:
            self.max_hr = max_hr
        elif self.age:
            self.max_hr = int(208 - (0.7 * self.age))
        if self.max_hr:
            self.threshold_hr = int(self.max_hr * 0.88)
        self.last_modified = datetime.now()
    
    def calculate_bmr(self):
        # Manual Override για τον χρήστη (2020 kcal)
        # Αν θες τον τύπο Mifflin, σβήσε το 'return 2020' και ξε-σχολίασε τα από κάτω
        return 2020 
        # if not all([self.weight_kg, self.height_cm, self.age]): return None
        # bmr = (10 * self.weight_kg) + (6.25 * self.height_cm) - (5 * self.age)
        # if self.gender == "M": bmr += 5
        # else: bmr -= 161
        # return int(bmr)
    
    def calculate_tdee(self, activity_level="active"):
        # Manual Override (2800 kcal max)
        return 2800
        # bmr = self.calculate_bmr()
        # if not bmr: return None
        # multipliers = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}
        # return int(bmr * multipliers.get(activity_level, 1.725))
    
    @staticmethod
    def str_to_sec(time_str):
        try:
            parts = time_str.split(':')
            if len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except: return 0
        return 0
    
    @staticmethod
    def sec_to_str(seconds):
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"
    
    def to_dict(self):
        return {
            "athlete_id": self.athlete_id, "name": self.name, "gender": self.gender,
            "age": self.age, "height_cm": self.height_cm, "weight_kg": self.weight_kg,
            "resting_hr": self.resting_hr, "max_hr": self.max_hr, "threshold_hr": self.threshold_hr,
            "vo2_max": self.vo2_max, "race_day": self.race_day.isoformat() if self.race_day else None,
            "current_goal": self.current_goal, "target_time": self.target_time,
            "personal_bests": self.personal_bests, "weight_floor": self.weight_floor,
            "paces": self.paces, "critical_speed_m_per_s": self.critical_speed_m_per_s,
            "d_prime_m": self.d_prime_m
        }
    
    @classmethod
    def from_dict(cls, data):
        profile = cls(athlete_id=data.get("athlete_id"), name=data.get("name"))
        profile.gender = data.get("gender", "M")
        profile.age = data.get("age")
        profile.height_cm = data.get("height_cm")
        profile.weight_kg = data.get("weight_kg")
        profile.resting_hr = data.get("resting_hr", 44)
        profile.max_hr = data.get("max_hr", 191)
        profile.threshold_hr = data.get("threshold_hr", 168)
        profile.vo2_max = data.get("vo2_max")
        if data.get("race_day"): profile.race_day = datetime.fromisoformat(data["race_day"])
        profile.current_goal = data.get("current_goal")
        profile.target_time = data.get("target_time")
        profile.personal_bests = data.get("personal_bests", {})
        profile.weight_floor = data.get("weight_floor", 75.0)
        profile.paces = data.get("paces", profile.paces)
        return profile

class PeriodizationManager:
    """
    Race goal and training phase management
    """
    
    def __init__(self, athlete_profile):
        self.athlete = athlete_profile
        self.goals = []
        self.current_goal = None
        self.completed_goals = []
    
    def add_goal(self, distance_km, target_time_str, race_date_str):
        """Add race goal"""
        goal = {
            "goal_id": f"GOAL_{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "distance_km": distance_km,
            "target_time": target_time_str,
            "race_date": datetime.strptime(race_date_str, "%Y-%m-%d"),
            "status": "ACTIVE",
            "created": datetime.now()
        }
        
        self.goals.append(goal)
        self.current_goal = goal
        self.athlete.current_goal = f"{distance_km}K in {target_time_str}"
        self.athlete.race_day = goal["race_date"]
        self.athlete.target_time = target_time_str
        
        return goal
    
    def calculate_phase(self, race_date):
        """Calculate training phase"""
        today = datetime.now()
        days_to_race = (race_date - today).days
        
        if days_to_race < 0:
            return "POST_RACE"
        elif days_to_race <= 10:
            return "TAPER"
        elif days_to_race <= 35:
            return "PEAK"
        elif days_to_race <= 70:
            return "BUILD"
        else:
            return "BASE"
    
    def complete_goal(self, goal_id, actual_time_str):
        """Mark goal complete and suggest next"""
        goal = next((g for g in self.goals if g["goal_id"] == goal_id), None)
        if not goal:
            return None
        
        goal["status"] = "COMPLETED"
        goal["actual_time"] = actual_time_str
        goal["completion_date"] = datetime.now()
        
        self.completed_goals.append(goal)
        self.goals = [g for g in self.goals if g["goal_id"] != goal_id]
        
        # Suggest next goals
        dist = goal["distance_km"]
        suggestions = [
            {"type": "IMPROVE", "distance": dist, "description": f"Improve {dist}K time by 2-5 percent"},
            {"type": "STEP_UP", "distance": dist * 2, "description": f"Step up to {dist*2}K"}
        ]
        
        return {"completed": goal, "suggestions": suggestions}


class NutritionScience:
    """
    BMR, TDEE, and Energy Availability calculations
    """
    
    @staticmethod
    def calculate_ffm(weight_kg, body_fat_percent=None):
        """Fat-Free Mass"""
        if body_fat_percent is None:
            body_fat_percent = 12  # Default estimate
        
        ffm = weight_kg * (1 - body_fat_percent / 100)
        return round(ffm, 1)
    
    @staticmethod
    def calculate_exercise_ee(duration_min, avg_hr, resting_hr, weight_kg, age, gender):
        """
        Exercise Energy Expenditure (Keytel 2005)
        """
        if gender == "M":
            kcal_per_min = ((-55.0969 + (0.6309 * avg_hr) + (0.1988 * weight_kg) + (0.2017 * age)) / 4.184)
        else:
            kcal_per_min = ((-20.4022 + (0.4472 * avg_hr) - (0.1263 * weight_kg) + (0.074 * age)) / 4.184)
        
        total_kcal = kcal_per_min * duration_min
        return max(0, int(total_kcal))
    
    @staticmethod
    def calculate_energy_availability(energy_intake_kcal, exercise_ee_kcal, ffm_kg):
        """
        Energy Availability = (EI - EEE) / FFM
        
        Thresholds (Loucks 2011):
        - EA less than 30: RED-S risk
        - EA 30-45: Suboptimal
        - EA greater than 45: Optimal
        """
        if ffm_kg == 0:
            return None, "INVALID", "Cannot calculate"
        
        ea = (energy_intake_kcal - exercise_ee_kcal) / ffm_kg
        
        if ea < 30:
            status = "[!!] RED-S RISK"
            recommendation = "CRITICAL: Increase intake immediately"
        elif ea < 45:
            status = "[WARN] SUBOPTIMAL EA"
            recommendation = "Increase calorie intake"
        else:
            status = "[OK] OPTIMAL EA"
            recommendation = "Energy availability sufficient"
        
        return round(ea, 1), status, recommendation


class SleepArchitecture:
    """
    Sleep phase tracking (Deep/REM separate)
    Walker (2017) - Why We Sleep
    """
    
    def __init__(self):
        self.sleep_log = []
    
    def add_sleep_session(self, date, total_min, deep_min, rem_min, quality_rating=None):
        """Log sleep with Deep and REM separate"""
        light_min = total_min - deep_min - rem_min
        
        deep_pct = (deep_min / total_min * 100) if total_min > 0 else 0
        rem_pct = (rem_min / total_min * 100) if total_min > 0 else 0
        
        session = {
            "date": date,
            "total_min": total_min,
            "deep_min": deep_min,
            "rem_min": rem_min,
            "light_min": max(0, light_min),
            "deep_pct": round(deep_pct, 1),
            "rem_pct": round(rem_pct, 1),
            "quality_rating": quality_rating
        }
        
        self.sleep_log.append(session)
        return session
    
    def analyze_quality(self, session):
        """
        Analyze sleep quality
        Optimal: Deep 13-23%, REM 20-25%
        """
        issues = []
        score = 100
        
        if session["total_min"] < 420:
            score -= 20
            issues.append("Total sleep less than 7h")
        
        if session["deep_pct"] < 13:
            score -= 15
            issues.append("Low deep sleep (less than 13 percent)")
        
        if session["rem_pct"] < 18:
            score -= 15
            issues.append("Low REM sleep (less than 18 percent)")
        
        if score >= 85:
            status = "[OK] EXCELLENT RECOVERY"
        elif score >= 70:
            status = "[OK] GOOD RECOVERY"
        else:
            status = "[WARN] POOR RECOVERY"
        
        return score, status, issues


class CardiacDecouplingDetailed:
    """
    Detailed aerobic efficiency analysis
    Esteve-Lanao (2005)
    """
    
    @staticmethod
    def calculate_decoupling(pace_first_half, hr_first_half, pace_second_half, hr_second_half):
        """
        Decoupling = (EF_second - EF_first) / EF_first * 100
        EF = Speed / HR
        """
        if hr_first_half == 0 or hr_second_half == 0:
            return None, "Invalid HR data"
        
        speed_first = 1000.0 / pace_first_half
        speed_second = 1000.0 / pace_second_half
        
        ef_first = speed_first / hr_first_half
        ef_second = speed_second / hr_second_half
        
        decoupling_pct = ((ef_second - ef_first) / ef_first) * 100
        
        if abs(decoupling_pct) < 5:
            status = "[OK] EXCELLENT aerobic efficiency"
        elif abs(decoupling_pct) < 10:
            status = "[WARN] MODERATE drift"
        else:
            status = "[!] HIGH decoupling"
        
        return round(decoupling_pct, 1), status


class CNSReadinessTest:
    """
    Central Nervous System readiness tests
    """
    
    def __init__(self):
        self.test_history = []
        self.baselines = {
            "tap_test": None,
            "grip_strength": None,
            "vertical_jump": None
        }
    
    def add_tap_test(self, date, taps_in_10_sec):
        """Finger tap test for neuromuscular fatigue"""
        test = {
            "date": date,
            "type": "TAP_TEST",
            "value": taps_in_10_sec
        }
        
        self.test_history.append(test)
        
        # Set baseline from first 3 tests
        tap_tests = [t for t in self.test_history if t["type"] == "TAP_TEST"]
        if len(tap_tests) >= 3 and self.baselines["tap_test"] is None:
            self.baselines["tap_test"] = sum(t["value"] for t in tap_tests[:3]) / 3
        
        if self.baselines["tap_test"]:
            percent = (taps_in_10_sec / self.baselines["tap_test"]) * 100
            
            if percent >= 100:
                status = "[OK] CNS FRESH"
            elif percent >= 95:
                status = "[OK] CNS GOOD"
            elif percent >= 90:
                status = "[WARN] CNS FATIGUED"
            else:
                status = "[!] CNS DEPLETED"
            
            return {"test": test, "baseline": self.baselines["tap_test"], "percent": round(percent, 1), "status": status}
        
        return {"test": test, "message": "Building baseline"}
    
    def add_grip_strength(self, date, force_kg):
        """Grip strength test"""
        test = {
            "date": date,
            "type": "GRIP_STRENGTH",
            "value": force_kg
        }
        
        self.test_history.append(test)
        
        grip_tests = [t for t in self.test_history if t["type"] == "GRIP_STRENGTH"]
        if len(grip_tests) >= 3 and self.baselines["grip_strength"] is None:
            self.baselines["grip_strength"] = max(t["value"] for t in grip_tests[:3])
        
        if self.baselines["grip_strength"]:
            percent = (force_kg / self.baselines["grip_strength"]) * 100
            
            if percent >= 95:
                status = "[OK] STRENGTH OPTIMAL"
            else:
                status = "[WARN] STRENGTH REDUCED"
            
            return {"test": test, "baseline": self.baselines["grip_strength"], "percent": round(percent, 1), "status": status}
        
        return {"test": test, "message": "Building baseline"}
    
    def add_vertical_jump(self, date, height_cm):
        """Vertical jump test"""
        test = {
            "date": date,
            "type": "VERTICAL_JUMP",
            "value": height_cm
        }
        
        self.test_history.append(test)
        
        jump_tests = [t for t in self.test_history if t["type"] == "VERTICAL_JUMP"]
        if len(jump_tests) >= 3 and self.baselines["vertical_jump"] is None:
            self.baselines["vertical_jump"] = max(t["value"] for t in jump_tests[:3])
        
        if self.baselines["vertical_jump"]:
            percent = (height_cm / self.baselines["vertical_jump"]) * 100
            
            if percent >= 95:
                status = "[OK] POWER OPTIMAL"
            else:
                status = "[WARN] POWER REDUCED"
            
            return {"test": test, "baseline": self.baselines["vertical_jump"], "percent": round(percent, 1), "status": status}
        
        return {"test": test, "message": "Building baseline"}


class DataImporter:
    """
    CSV import functionality
    """
    
    @staticmethod
    def import_csv(filepath):
        """Import training sessions from CSV"""
        try:
            if not PANDAS_AVAILABLE:
                return None, "pandas not installed"
            
            import pandas as pd
            df = pd.read_csv(filepath)
            
            sessions = []
            for _, row in df.iterrows():
                session = {
                    "date": pd.to_datetime(row.get("date")),
                    "duration_min": float(row.get("duration_min", 0)),
                    "distance_km": float(row.get("distance_km", 0)),
                    "avg_hr": float(row.get("avg_hr", 0)),
                    "rpe": float(row.get("rpe", 0)) if "rpe" in row else None,
                    "vert_osc": float(row.get("vert_osc", 0)) if "vert_osc" in row else 0.0,
                    "gct": float(row.get("gct", 0)) if "gct" in row else 0.0
                }
                sessions.append(session)
            
            return sessions, f"[OK] Imported {len(sessions)} sessions"
        
        except Exception as e:
            return None, f"[ERROR] {str(e)}"


class AthleteDatabase:
    """
    Multi-athlete management with JSON storage
    """
    
    def __init__(self, db_path="athletes"):
        # Βρες τον φάκελο που βρίσκεται το αρχείο .py
        try:
            base_dir = Path(__file__).parent.absolute()
        except NameError:
            # Fallback για IDLE/Jupyter
            base_dir = Path.cwd()
            
        self.db_path = base_dir / db_path
        self.db_path.mkdir(exist_ok=True)
        self.athletes = {}
        self.current_athlete_id = None
        self.load_all()
    
    def create_athlete(self, name, gender, age, height_cm, weight_kg):
        """Create new athlete"""
        profile = UniversalAthleteProfile(name=name)
        profile.set_demographics(gender, age, height_cm, weight_kg)
        
        self.athletes[profile.athlete_id] = profile
        self.current_athlete_id = profile.athlete_id
        self.save_athlete(profile)
        
        return profile
    
    def switch_athlete(self, athlete_id):
        """Switch to different athlete"""
        if athlete_id in self.athletes:
            self.current_athlete_id = athlete_id
            return self.athletes[athlete_id]
        return None
    
    def get_current(self):
        """Get current athlete"""
        if self.current_athlete_id and self.current_athlete_id in self.athletes:
            return self.athletes[self.current_athlete_id]
        return None
    
    def list_all(self):
        """List all athletes"""
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
    
    def save_athlete(self, profile):
        """Save athlete to JSON"""
        filepath = self.db_path / f"{profile.athlete_id}.json"
        with open(filepath, 'w') as f:
            json.dump(profile.to_dict(), f, indent=2)
    
    def load_all(self):
        """Load all athletes from disk"""
        if not self.db_path.exists():
            return
        
        for filepath in self.db_path.glob("*.json"):
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                profile = UniversalAthleteProfile.from_dict(data)
                self.athletes[profile.athlete_id] = profile
            except:
                pass

class TitanProfile:
    def __init__(self):
        self.athlete_name = "Zafiris"
        self.dob = "27/01/1983"
        self.race_day = datetime(2026, 4, 26)

        # PHYSIOLOGY
        self.max_hr = 191
        self.threshold_hr = 168
        self.resting_hr_baseline = 44
        self.vo2_max_baseline = 58.5

        # WEIGHT GUARD
        self.weight_floor = 75.0
        self.weight_ceiling = 76.2
        self.weight_panic = 74.5

        # PACING ANCHORS
        self.base_5k_time_str = "19:00"
        self.base_5k_sec = self.str_to_sec(self.base_5k_time_str) / 5.0

        # Initial paces (will be adapted)
        self.paces = {
            "EASY": "5:31",
            "LONG_RUN": "5:08",
            "TEMPO": "4:06",
            "VO2_MAX": "3:43",
            "HAMMER": "3:45-3:55",
            "RECOVERY": "6:00+"
        }

        # Critical Speed / D
        self.critical_speed_m_per_s = 4.1
        self.d_prime_m = 250.0

    @staticmethod
    def str_to_sec(time_str):
        try:
            parts = time_str.split(':')
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except:
            return 0
        return 0

    @staticmethod
    def sec_to_str(seconds):
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"


# ------------------------------------------------------------------------------
# MATHEMATICAL CORE (WEIGHT FUNCTION / STATUS)
# ------------------------------------------------------------------------------
class MathCore:
    @staticmethod
    def weight_function_Wf(weight, night_drop, epoc):
        if weight < 74.5:
            return "AGGRESSIVE_CORRECTION"
        if weight < 75.0:
            return "EMERGENCY_MODE"
        if night_drop > 1.2:
            return "NIGHT_DROP_ALERT"
        if epoc > 350:
            return "EPOC_OVERRIDE"
        if weight <= 75.5:
            return "SAFE_DROP_RULE"
        return "STABLE"

    @staticmethod
    def system_status_SSV(hrv_status, sleep_score, pain, weight, epoc, night_drop):
        critical_cond = (
            pain >= 3 or
            hrv_status == "LOW" or
            sleep_score < 60 or
            weight < 75.0 or
            epoc > 350
        )
        unstable_cond = (
            pain == 2 or
            60 <= sleep_score < 65 or
            night_drop > 1.0
        )
        if critical_cond:
            return "CRITICAL"
        if unstable_cond:
            return "UNSTABLE"
        return "STABLE"


# ------------------------------------------------------------------------------
# MEDICAL & CRISIS ENGINE
# ------------------------------------------------------------------------------
class MedicalEngine:
    @staticmethod
    def blood_work_verification(ferritin, vit_d, cpk):
        alerts = []
        if ferritin < 30:
            alerts.append(" FERRITIN CRITICAL: Force Iron Protocol x2.")
        if vit_d < 30:
            alerts.append(" VITAMIN D LOW: Supplement 4000 IU daily.")
        if cpk > 300:
            alerts.append(" CPK SPIKE: Muscle Damage. FORCE REST 48h.")
        return alerts

    @staticmethod
    def crisis_protocol(symptoms):
        s = symptoms.upper()
        if s == "FEVER":
            return " CRISIS MODE: ABSOLUTE REST. (Myocarditis Risk)."
        if s == "CHEST" or s == "BELOW_NECK":
            return " STOP: Do not train."
        if s == "HEAD" or s == "ABOVE_NECK":
            return " CAUTION: Easy Z1 Run allowed only."
        return " SYSTEM CLEAR"

    @staticmethod
    def check_supplements(date_str):
        d = datetime.strptime(date_str, "%Y-%m-%d")
        supps = [" CREATINE: 5g (Daily Monohydrate)"]
        if d.day % 2 == 0:
            supps.append(" IRON: 100mg + Vit C (Hepcidin Window).")
        else:
            supps.append(" NO IRON TODAY (Absorption Reset).")
        return supps


# ------------------------------------------------------------------------------
# NUTRITION & GLYCOGEN ENGINE
# ------------------------------------------------------------------------------
class GlycogenEngine:
    @staticmethod
    def glycogen_flag(low_carb_day: bool, back_to_back_quality: bool, weight: float):
        """
        - Low carb day  forbid hammer
        - Back-to-back quality  mandatory carbs  7 g/kg
        """
        flags = []
        hammer_allowed = True
        min_carbs = None

        if low_carb_day:
            hammer_allowed = False
            flags.append("LOW_GLYCOGEN: Hammer forbidden today.")

        if back_to_back_quality:
            min_carbs = int(7 * weight)
            flags.append(f"BACK-TO-BACK QUALITY: Carbs  {min_carbs}g required.")

        if not flags:
            flags.append("GLYCOGEN OK: Normal fueling rules.")

        return hammer_allowed, min_carbs, flags


class NutritionEngine:
    @staticmethod
    def calculate_plan(weight, session_type, gut_health, dew_point, phase,
                       low_carb_day=False, back_to_back_quality=False):
        protein = 1.8 * weight
        if session_type in ["TEMPO", "INTERVALS", "LONG_RUN", "PROGRESSIVE"]:
            carbs_g_kg = 6.0
        else:
            carbs_g_kg = 4.0

        hammer_allowed, min_carbs, glyc_flags = GlycogenEngine.glycogen_flag(
            low_carb_day, back_to_back_quality, weight
        )

        if min_carbs is not None and carbs_g_kg * weight < min_carbs:
            carbs_g_kg = max(carbs_g_kg, 7.0)

        plan = {
            "Protein_Target": f"{int(protein)}g",
            "Carb_Target": f"{int(carbs_g_kg * weight)}g",
            "Phase": phase,
            "Hammer_Allowed": hammer_allowed,
            "Glycogen_Flags": glyc_flags
        }

        if gut_health < 6:
            plan["Diet_Type"] = " WHITE DIET (Low Residue)"
            plan["Foods"] = "White Rice, Potato (peeled), White Bread, Honey."
            plan["Forbidden"] = "Fiber, Salads, Whole Grains, Dairy (except strained)."
        else:
            plan["Diet_Type"] = " PERFORMANCE DIET"
            plan["Foods"] = "Complex Carbs, Lean Protein, Healthy Fats."

        fluid_hr = 500
        sod_hr = 400
        if dew_point > 20:
            fluid_hr += 300
            sod_hr += 400
        elif dew_point > 16:
            fluid_hr += 200
            sod_hr += 200

        plan["Hydration_Strategy"] = f"{fluid_hr}ml/hr + {sod_hr}mg Sodium/hr"
        return plan


# ------------------------------------------------------------------------------
# SCIENTIFIC TRAINING KERNEL
# ------------------------------------------------------------------------------
class ScientificKernel:
    @staticmethod
    def get_methodology(session_type):
        st = session_type.upper()
        if st in ["TEMPO", "INTERVALS"]:
            return "NORWEGIAN (Sub-LT2): Control Lactate < 3.5mmol. Don't burn out."
        if st in ["LONG_RUN", "PROGRESSIVE"]:
            return "KENYAN (Pole-Pole): Start slow, finish fast naturally."
        if st in ["EASY", "RECOVERY_EASY"]:
            return "POLARIZED (80/20): Strict Zone 1/2."
        if "RACE" in st:
            return "RACE EXECUTION: Even pace, controlled aggression."
        return "GENERAL MIXED MODEL."


# ------------------------------------------------------------------------------
# ADAPTIVE MEMORY & LOAD ENGINE
# ------------------------------------------------------------------------------
class AdaptiveMemory:
    def __init__(self):
        self.session_history = []
        self.readiness_avg_14d = 85
        self.monotony_index = 1.2
        self.supercomp_status = "BASELINE"
        self.adaptive_pace_factor = 1.00
        self.last_quality_sessions = []
        self.last_3d_soreness = []

    def log_session(self, date, session_type, load, rpe, drift, success_flag, soreness=None):
        self.session_history.append({
            "date": date,
            "type": session_type,
            "load": load,
            "rpe": rpe,
            "drift": drift,
            "success": success_flag
        })
        if session_type in ["TEMPO", "INTERVALS", "LONG_RUN", "PROGRESSIVE"]:
            self.last_quality_sessions.append(date)
            self.last_quality_sessions = self.last_quality_sessions[-5:]
        if soreness is not None:
            self.last_3d_soreness.append(soreness)
            self.last_3d_soreness = self.last_3d_soreness[-3:]

    def calculate_neural_adaptation(self, target_pace_sec, actual_pace_sec, avg_hr, threshold_hr):
        if actual_pace_sec < target_pace_sec and avg_hr <= threshold_hr:
            improvement = target_pace_sec - actual_pace_sec
            self.adaptive_pace_factor *= 0.995
            return f" NEURAL GAIN: +{improvement:.1f}s/km faster. Pace factor -> {self.adaptive_pace_factor:.3f}"
        return "STABLE: Neural adaptation maintained."

    def check_monotony(self, load_7d, std_dev_load):
        if std_dev_load == 0:
            return " MONOTONY UNKNOWN (No variance)."
        monotony = load_7d / std_dev_load
        self.monotony_index = monotony
        if monotony > 2.5:
            return " DANGER: Very high monotony. Force variation / rest."
        if monotony > 2.0:
            return " RISK: High monotony. Add Fartlek or Rest."
        if monotony > 1.5:
            return " WATCH: Moderate monotony."
        return " LOAD VARIATION: Healthy."

    def supercompensation_window(self, last_hard_session_hours):
        if 24 <= last_hard_session_hours <= 48:
            self.supercomp_status = "RECOVERY"
            return " RECOVERY WINDOW (Protein Synthesis active)"
        if 48 < last_hard_session_hours <= 72:
            self.supercomp_status = "PEAK"
            return " SUPER-COMPENSATION PEAK (Go Hard Now)"
        self.supercomp_status = "BASELINE"
        return " BASELINE (Normal Training)"

    def session_density_index(self, now_dt):
        if len(self.last_quality_sessions) < 2:
            return "SDI: Not enough data."
        last = self.last_quality_sessions[-1]
        delta_h = (now_dt - last).total_seconds() / 3600.0
        if delta_h < 24:
            return " SDI: <24h since last quality. Force EASY."
        if delta_h < 36:
            return " SDI: <36h. Downgrade intensity."
        if delta_h < 48:
            return " SDI: <48h. Caution."
        return " SDI: Safe spacing."

    def mechanical_load_risk(self, easy_pace_today_sec, easy_pace_baseline_sec):
        """
        Proxy:
        - soreness trend 3 
        - pace drop  easy runs
        """
        risk_flags = []
        if len(self.last_3d_soreness) == 3 and sum(self.last_3d_soreness) / 3.0 >= 5:
            risk_flags.append("HIGH_SORENESS_TREND")
        if easy_pace_today_sec > easy_pace_baseline_sec * 1.08:
            risk_flags.append("EASY_PACE_DROP")
        if not risk_flags:
            return "MECH LOAD: OK"
        if "HIGH_SORENESS_TREND" in risk_flags and "EASY_PACE_DROP" in risk_flags:
            return " MECH LOAD: HIGH RISK (Consider Rest / Downgrade)."
        return " MECH LOAD: Watch (Adjust volume/intensity)."


# ------------------------------------------------------------------------------
# CRITICAL SPEED & D ENGINE
# ------------------------------------------------------------------------------
class CriticalSpeedEngine:
    @staticmethod
    def estimate_cs_and_dprime(perfs):
        if len(perfs) < 2:
            return None, None
        xs = []
        ys = []
        for dist_m, time_s in perfs:
            if time_s <= 0:
                continue
            xs.append(time_s)
            ys.append(dist_m)
        if len(xs) < 2:
            return None, None
        n = len(xs)
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xx = sum(x * x for x in xs)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        denom = n * sum_xx - sum_x * sum_x
        if denom == 0:
            return None, None
        a = (n * sum_xy - sum_x * sum_y) / denom
        b = (sum_y - a * sum_x) / n
        cs = a
        d_prime = b
        return cs, d_prime

    @staticmethod
    def time_to_exhaustion_at_pace(cs_m_per_s, d_prime_m, pace_sec_per_km):
        if cs_m_per_s is None or d_prime_m is None:
            return None
        if pace_sec_per_km <= 0:
            return None
        v = 1000.0 / pace_sec_per_km
        if v <= cs_m_per_s:
            return None
        t = d_prime_m / (v - cs_m_per_s)
        return t


# ------------------------------------------------------------------------------
# HR DRIFT / DECOUPLING ENGINE
# ------------------------------------------------------------------------------
class DriftEngine:
    @staticmethod
    def compute_drift(hr_first_half, hr_second_half):
        if hr_first_half <= 0:
            return 0.0
        drift = (hr_second_half - hr_first_half) / hr_first_half * 100.0
        return drift

    @staticmethod
    def drift_rule(drift_percent):
        if drift_percent > 5.0:
            return " DRIFT > 5%: Stop progression. No hammer today."
        if drift_percent < 3.0:
            return " DRIFT < 3%: Hammer extension allowed."
        return " DRIFT 35%: Maintain, no extra load."


# ------------------------------------------------------------------------------
# LACTATE LOGIC (LT1 / LT2 WITHOUT LACTATE METER)
# ------------------------------------------------------------------------------
class LactateLogic:
    @staticmethod
    def estimate_lt1(hr_percent_max, drift_percent):
        """
        LT1  drift < 3% + HR < 7578% HRmax
        """
        if drift_percent < 3.0 and hr_percent_max <= 78.0:
            return "LT1_ZONE: TRUE (Pure aerobic)."
        return "LT1_ZONE: FALSE."

    @staticmethod
    def estimate_lt2(hr_stable: bool, rpe: float):
        """
        LT2  tempo   HR & RPE 67
        """
        if hr_stable and 6.0 <= rpe <= 7.0:
            return "LT2_APPROX: TRUE (Threshold hit)."
        return "LT2_APPROX: FALSE."

    @staticmethod
    def tempo_volume_decision(is_lt2_true: bool):
        """
        ELSE  downgrade volume
        """
        if is_lt2_true:
            return "TEMPO VOLUME: OK (Full planned volume)."
        return "TEMPO VOLUME: DOWNGRADE (Cut reps or distance)."


# ------------------------------------------------------------------------------
# FATIGUE BUCKETS ENGINE
# ------------------------------------------------------------------------------
class FatigueEngine:
    @staticmethod
    def classify_fatigue(hr_suppression, rpe_mismatch, pace_hr_divergence, soreness):
        types = []
        if hr_suppression:
            types.append("CENTRAL")
        if rpe_mismatch:
            types.append("CENTRAL")
        if pace_hr_divergence:
            types.append("METABOLIC")
        if soreness >= 5:
            types.append("PERIPHERAL")
        if not types:
            return "LOW", ["NONE"]
        if "CENTRAL" in types and "METABOLIC" in types:
            return "HIGH", list(set(types))
        if "PERIPHERAL" in types and ("CENTRAL" in types or "METABOLIC" in types):
            return "MEDIUM", list(set(types))
        return "MEDIUM", list(set(types))



# ------------------------------------------------------------------------------
# DECISION RULES ENGINE (Seiler / Mujika / Elite Coaching)
# ------------------------------------------------------------------------------
class DecisionRulesEngine:
    """
    Elite decision rules based on Seiler, Mujika, and coaching practice:
    - HR drift management in steady/tempo
    - RPE vs HR mismatch detection (neuromuscular fatigue)
    - Morning weight + HRV decision logic
    """
    
    @staticmethod
    def check_hr_drift_pace_adjustment(drift_pct, session_type, current_pace_sec):
        """
        Rule: If HR drift >5% in steady/tempo  reduce pace by 5-10 seconds
        Returns: (should_adjust, new_pace_sec, message)
        """
        if drift_pct > 5.0 and session_type in ["TEMPO", "LONG_RUN", "PROGRESSIVE"]:
            adjustment_sec = 7.5
            new_pace = current_pace_sec + adjustment_sec
            msg = f" HR DRIFT >5% ({drift_pct:.1f}%)  SLOW DOWN {adjustment_sec:.0f}\" per km"
            return True, new_pace, msg
        return False, current_pace_sec, " HR Drift OK"
    
    @staticmethod
    def check_neuromuscular_fatigue(rpe, avg_hr, threshold_hr):
        """
        Rule: If RPE >7 in tempo while HR  LTHR  probable neuromuscular fatigue
        """
        if rpe > 7 and avg_hr <= threshold_hr:
            msg = " NEUROMUSCULAR FATIGUE DETECTED: RPE high but HR suppressed"
            return True, msg
        return False, " No NM fatigue signals"
    
    @staticmethod
    def check_morning_abort_hammer(weight_drop_pct, hrv_status):
        """
        Rule: If morning weight  >1.2% + HRV   cancel Hammer session
        """
        if weight_drop_pct > 1.2 and hrv_status == "LOW":
            msg = " ABORT HAMMER: Weight drop >1.2% + HRV low  systemic fatigue"
            return True, msg
        return False, " Hammer session cleared"


# ------------------------------------------------------------------------------
# NEUROMUSCULAR LOAD MANAGEMENT (Norwegian / Ingebrigtsen-style)
# ------------------------------------------------------------------------------
class NeuromuscularLoadEngine:
    """
    Tracks CNS load from high-intensity work:
    - Strides = 1 unit
    - Intervals <1k = 2 units
    - Hammer segment = 3 units
    Rule: >5 units/week  neuromuscular deload required
    """
    
    def __init__(self):
        self.session_log = []
    
    def add_session(self, date, session_type, has_strides=False, 
                   has_short_intervals=False, has_hammer=False):
        nli = 0
        details = []
        if has_strides:
            nli += 1
            details.append("Strides: +1")
        if has_short_intervals:
            nli += 2
            details.append("Short Intervals: +2")
        if has_hammer:
            nli += 3
            details.append("Hammer: +3")
        self.session_log.append((date, session_type, nli, details))
        return nli, details
    
    def calculate_weekly_nli(self, reference_date):
        from datetime import timedelta
        week_ago = reference_date - timedelta(days=7)
        weekly_total = sum(
            nli for date, _, nli, _ in self.session_log 
            if week_ago <= date <= reference_date
        )
        return weekly_total
    
    def check_deload_needed(self, weekly_nli):
        if weekly_nli > 5:
            return True, f" DELOAD REQUIRED: Weekly NLI = {weekly_nli} (threshold: 5)"
        return False, f" NM Load OK: Weekly NLI = {weekly_nli}"
    
    def get_status(self, reference_date):
        weekly = self.calculate_weekly_nli(reference_date)
        needs_deload, msg = self.check_deload_needed(weekly)
        return {
            "weekly_nli": weekly,
            "needs_deload": needs_deload,
            "message": msg
        }


# ------------------------------------------------------------------------------
# FUEL TIMING MATRIX (Jeukendrup / Burke)
# ------------------------------------------------------------------------------
class FuelTimingEngine:
    """
    Scientific fueling strategy based on session type
    """
    
    @staticmethod
    def get_fuel_strategy(session_type, has_hammer_segment=False):
        strategies = {
            "INTERVALS": {
                "pre_carbs": "MANDATORY (60-90g, 1-3h before)",
                "intra_carbs": "MANDATORY (30-60g/h during)",
                "protein": "Post-session (20-30g within 30min)",
                "priority": "Glycogen-dependent session"
            },
            "TEMPO": {
                "pre_carbs": "MANDATORY (60-90g, 1-3h before)",
                "intra_carbs": "NOT NEEDED",
                "protein": "Post-session (20-30g)",
                "priority": "Pre-fuel critical"
            },
            "LONG_RUN": {
                "pre_carbs": "MODERATE (30-60g if no Hammer)",
                "intra_carbs": "MANDATORY if Hammer segment (30-60g/h)",
                "protein": "Post-session priority",
                "priority": "Context-dependent"
            },
            "PROGRESSIVE": {
                "pre_carbs": "MANDATORY if Hammer (60-90g)",
                "intra_carbs": "ONLY during Hammer segment",
                "protein": "Post-session",
                "priority": "Fuel for the surge"
            },
            "EASY": {
                "pre_carbs": "OPTIONAL (fasted OK)",
                "intra_carbs": "NOT NEEDED",
                "protein": "PRIORITY (breakfast/post)",
                "priority": "Protein-first, fat adaptation OK"
            },
            "RECOVERY": {
                "pre_carbs": "OPTIONAL",
                "intra_carbs": "NOT NEEDED",
                "protein": "PRIORITY",
                "priority": "Repair over performance"
            }
        }
        base_strategy = strategies.get(session_type, strategies["EASY"])
        if session_type in ["LONG_RUN", "PROGRESSIVE"] and has_hammer_segment:
            base_strategy["intra_carbs"] = "MANDATORY (30-60g/h during Hammer)"
        return base_strategy


# ------------------------------------------------------------------------------
# DAILY MONITORING SYSTEM
# ------------------------------------------------------------------------------
class DailyMonitoring:
    """
    Track daily readiness metrics
    """
    
    def __init__(self):
        self.log = []
    
    def add_entry(self, date, weight, resting_hr, stiffness, sleep_quality):
        self.log.append({
            "date": date,
            "weight": weight,
            "resting_hr": resting_hr,
            "stiffness": stiffness,
            "sleep_quality": sleep_quality
        })
    
    def get_weight_change_pct(self, baseline_weight):
        if not self.log:
            return 0.0
        current = self.log[-1]["weight"]
        return abs((baseline_weight - current) / baseline_weight * 100)
    
    def get_status(self, baseline_weight, baseline_rhr):
        if not self.log:
            return "NO DATA"
        latest = self.log[-1]
        flags = []
        weight_change = abs((baseline_weight - latest["weight"]) / baseline_weight * 100)
        if weight_change > 1.2:
            flags.append(f" Weight deviation: {weight_change:.1f}%")
        rhr_change = latest["resting_hr"] - baseline_rhr
        if rhr_change > 5:
            flags.append(f" RHR elevated: +{rhr_change} bpm")
        if latest["stiffness"] >= 3:
            flags.append(f" High stiffness: {latest['stiffness']}/5")
        if latest["sleep_quality"] <= 2:
            flags.append(f" Poor sleep: {latest['sleep_quality']}/5")
        if not flags:
            return " ALL SYSTEMS READY"
        return " | ".join(flags)
    
    def display_metrics(self):
        if not self.log:
            print("No monitoring data logged.")
            return
        print("\n DAILY MONITORING (Last 7 Days)")
        print("=" * 70)
        print(f"{'Date':<12} {'Weight':<8} {'RHR':<6} {'Stiffness':<10} {'Sleep':<8}")
        print("-" * 70)
        recent = self.log[-7:] if len(self.log) > 7 else self.log
        for entry in recent:
            print(f"{entry['date'].strftime('%Y-%m-%d'):<12} "
                  f"{entry['weight']:<8.1f} "
                  f"{entry['resting_hr']:<6.0f} "
                  f"{entry['stiffness']:<10}/5 "
                  f"{entry['sleep_quality']:<8}/5")
        print("=" * 70)


# ------------------------------------------------------------------------------
# RACE WEEK ENTROPY ENGINE
# ------------------------------------------------------------------------------
class RaceWeekEngine:
    """
    Race week philosophy: NOT peak fitness, but peak PREDICTABILITY
    """
    
    @staticmethod
    def calculate_entropy_score(days_to_race, training_consistency, 
                               gut_health, sleep_avg, weight_stable):
        entropy = 0
        if days_to_race > 7:
            return 0, "Not in race week yet"
        if not training_consistency:
            entropy += 30
        if gut_health < 7:
            entropy += 20
        if sleep_avg < 3:
            entropy += 25
        if not weight_stable:
            entropy += 25
        if entropy == 0:
            status = " PERFECT PREDICTABILITY"
        elif entropy < 30:
            status = " LOW ENTROPY - Ready to race"
        elif entropy < 60:
            status = " MODERATE ENTROPY - Tighten protocols"
        else:
            status = " HIGH ENTROPY - Risk management mode"
        return entropy, status
    
    @staticmethod
    def race_week_protocol(days_to_race):
        protocols = {
            7: "Last quality session. After today: predictability > fitness.",
            6: "Easy run. Lock in nutrition routine.",
            5: "Easy run. Eliminate all novel foods/drinks.",
            4: "Easy run. Confirm race kit, test nothing new.",
            3: "Rest or very easy. Mental prep begins.",
            2: "Short shakeout. Course visualization.",
            1: "Minimal movement. Trust the taper.",
            0: "RACE DAY. Execute the plan."
        }
        return protocols.get(days_to_race, "Beyond race week - train normally")


# ==============================================================================
# TIER 1: INJURY PREVENTION & LOAD MANAGEMENT
# ==============================================================================

# ------------------------------------------------------------------------------
# ACWR ENGINE (Gabbett 2016 - Injury Prevention)
# ------------------------------------------------------------------------------
class ACWREngine:
    """
    Acute:Chronic Workload Ratio - Gold standard for injury prevention
    
    Scientific Basis:
    - Gabbett, T.J. (2016). Br J Sports Med, 50(5), 273-280.
    - Malone, S. et al. (2017). J Sci Med Sport, 20(6), 561-565.
    - Meta-analysis: 28,000+ athletes
    
    Key Findings:
    - ACWR 0.8-1.3: Optimal adaptation zone
    - ACWR >1.5: 2-4x increase in injury risk
    - ACWR <0.8: Detraining risk
    """
    
    @staticmethod
    def calculate_acwr(acute_load_7d, chronic_load_28d_avg):
        """
        ACWR = Acute Load (7 days) / Chronic Load (28-day average)
        
        Args:
            acute_load_7d: Sum of last 7 days load
            chronic_load_28d_avg: Average daily load over 28 days
        
        Returns:
            (acwr_value, status, recommendation)
        """
        if chronic_load_28d_avg == 0 or chronic_load_28d_avg is None:
            return None, "INSUFFICIENT DATA", "Need 28 days of training data"
        
        acwr = acute_load_7d / (chronic_load_28d_avg * 7)
        
        if acwr < 0.5:
            status = " SEVERE DETRAINING"
            recommendation = "Increase load gradually (max +10% per week)"
        elif acwr < 0.8:
            status = " DETRAINING RISK"
            recommendation = "Consider increasing weekly volume"
        elif 0.8 <= acwr <= 1.0:
            status = " MAINTENANCE ZONE"
            recommendation = "Stable - good for recovery weeks"
        elif 1.0 < acwr <= 1.3:
            status = " SWEET SPOT (Optimal)"
            recommendation = "Perfect adaptation stimulus - maintain this range"
        elif 1.3 < acwr <= 1.5:
            status = " MODERATE RISK"
            recommendation = "Monitor fatigue closely, consider easy week next"
        else:  # >1.5
            status = " HIGH INJURY RISK"
            recommendation = "REDUCE LOAD - Spike too large (2-4x injury risk)"
        
        return round(acwr, 2), status, recommendation
    
    @staticmethod
    def weekly_load_recommendation(current_chronic_avg, target_acwr=1.2):
        """
        Calculate safe weekly load target based on current chronic load
        """
        safe_weekly_load = current_chronic_avg * 7 * target_acwr
        return safe_weekly_load


# ------------------------------------------------------------------------------
# TSB/CTL/ATL ENGINE (Banister/Coggan - Performance Management Chart)
# ------------------------------------------------------------------------------
class TSBEngine:
    """
    Training Stress Balance - The "Performance Management Chart"
    
    Scientific Basis:
    - Banister, E.W. (1975). Impulse-Response Model
    - Busso, T. (2003). Med Sci Sports Exerc, 35(7), 1188-1195.
    - Coggan, A.R. (2010). Training and Racing with a Power Meter
    
    Components:
    - CTL (Chronic Training Load): 42-day exponential average = "Fitness"
    - ATL (Acute Training Load): 7-day exponential average = "Fatigue"
    - TSB (Training Stress Balance): CTL - ATL = "Form"
    
    Race Day Target: TSB = +5 to +10 (fresh but fit)
    """
    
    def __init__(self):
        self.ctl = 0
        self.atl = 0
        self.tsb = 0
        self.daily_loads = []
    
    def add_daily_load(self, date, load):
        """Add daily training load (can be TRIMP, sRPE, or kmRPE)"""
        self.daily_loads.append((date, load))
    
    def calculate_ctl(self, decay=42):
        """
        CTL = Exponentially Weighted Moving Average (42 days)
        Formula: CTL_today = CTL_yesterday + (Load_today - CTL_yesterday) / decay
        """
        if len(self.daily_loads) < 7:
            return None
        
        ctl = self.daily_loads[0][1]  # Start with first day
        alpha = 2.0 / (decay + 1)
        
        for _, load in self.daily_loads[1:]:
            ctl = (load * alpha) + (ctl * (1 - alpha))
        
        self.ctl = ctl
        return round(ctl, 1)
    
    def calculate_atl(self, decay=7):
        """
        ATL = Exponentially Weighted Moving Average (7 days)
        """
        if len(self.daily_loads) < 3:
            return None
        
        atl = self.daily_loads[0][1]
        alpha = 2.0 / (decay + 1)
        
        for _, load in self.daily_loads[1:]:
            atl = (load * alpha) + (atl * (1 - alpha))
        
        self.atl = atl
        return round(atl, 1)
    
    def calculate_tsb(self):
        """
        TSB = CTL - ATL
        """
        ctl = self.calculate_ctl()
        atl = self.calculate_atl()
        
        if ctl is None or atl is None:
            return None, "INSUFFICIENT DATA"
        
        tsb = ctl - atl
        self.tsb = tsb
        
        # Interpret TSB value
        if tsb > 25:
            status = " SEVERE DETRAINING"
        elif tsb > 15:
            status = " DETRAINING (losing fitness)"
        elif 5 < tsb <= 15:
            status = " FRESH (good for tune-up race)"
        elif -10 <= tsb <= 5:
            status = " RACE FORM (optimal for A-race)"
        elif -30 < tsb < -10:
            status = " PRODUCTIVE OVERLOAD (building fitness)"
        elif -50 < tsb <= -30:
            status = " FUNCTIONAL OVERREACH (plan recovery)"
        else:  # < -50
            status = " OVERREACHED/OVERTRAINED (force rest)"
        
        return round(tsb, 1), status
    
    def predict_race_day_tsb(self, days_until_race, planned_loads):
        """
        Predict TSB on race day given planned training loads
        Useful for taper planning
        """
        # This would need simulation - simplified version
        if not planned_loads or days_until_race > len(planned_loads):
            return None
        
        # Simulate future CTL/ATL
        temp_ctl = self.ctl
        temp_atl = self.atl
        
        for load in planned_loads[:days_until_race]:
            temp_atl = (load * (2/8)) + (temp_atl * (6/8))
            temp_ctl = (load * (2/43)) + (temp_ctl * (41/43))
        
        predicted_tsb = temp_ctl - temp_atl
        return round(predicted_tsb, 1)


# ------------------------------------------------------------------------------
# HRV-GUIDED TRAINING ENGINE (Kiviniemi 2007, Plews 2013)
# ------------------------------------------------------------------------------
class HRVGuidedEngine:
    """
    Adaptive training based on Heart Rate Variability
    
    Scientific Basis:
    - Kiviniemi, A.M. et al. (2007). Eur J Appl Physiol, 101(6), 743-751.
    - Plews, D.J. et al. (2013). Int J Sports Physiol Perform, 8(5), 512-521.
    - Vesterinen, V. et al. (2016). Med Sci Sports Exerc, 48(7), 1347-1354.
    
    Key Findings:
    - HRV-guided: +8.3% VO2max vs +5.6% predefined training
    - Fewer overtraining symptoms
    - Better psychological adherence
    
    Protocol (Kiviniemi):
    - HRV  baseline: Proceed with planned intensity
    - HRV < baseline: Downgrade to easy/rest
    
    Advanced (Plews - elite athletes):
    - HRV < baseline - 1 SD: Modify session
    - HRV < baseline - 2 SD: Force rest
    """
    
    def __init__(self):
        self.hrv_log = []  # (date, rmssd_value)
        self.baseline_days = 7
    
    def add_hrv_measurement(self, date, rmssd):
        """
        Add morning HRV measurement (rMSSD in ms)
        
        rMSSD = Root Mean Square of Successive Differences
        Standard HRV metric for training readiness
        """
        self.hrv_log.append((date, rmssd))
    
    def calculate_baseline(self, days=7):
        """
        Calculate rolling baseline (mean  SD)
        """
        if len(self.hrv_log) < days:
            return None, None
        
        recent = [hrv for _, hrv in self.hrv_log[-days:]]
        baseline = sum(recent) / len(recent)
        
        # Standard deviation
        variance = sum((x - baseline)** 2 for x in recent) / len(recent)
        std_dev = variance** 0.5
        
        return baseline, std_dev
    
    def get_training_recommendation(self, today_hrv, planned_session):
        """
        Apply HRV-guided decision rules
        
        Returns: (recommended_session, explanation, confidence)
        """
        baseline_result = self.calculate_baseline(self.baseline_days)
        
        if baseline_result[0] is None:
            return planned_session, "Insufficient HRV data - proceed with plan", "LOW"
        
        baseline, std_dev = baseline_result
        
        # Plews thresholds (elite athletes)
        threshold_critical = baseline - (2 * std_dev)
        threshold_caution = baseline - std_dev
        threshold_optimal = baseline
        
        if today_hrv < threshold_critical:
            # Severely suppressed
            return "REST", f" HRV CRITICAL: {today_hrv:.1f} < {threshold_critical:.1f} (baseline - 2SD)", "HIGH"
        
        elif today_hrv < threshold_caution:
            # Moderately suppressed
            if planned_session in ["INTERVALS", "TEMPO", "PROGRESSIVE", "HAMMER"]:
                return "EASY", f" HRV LOW: {today_hrv:.1f} < {threshold_caution:.1f} (baseline - 1SD)  Downgrade", "HIGH"
            else:
                return planned_session, f"HRV slightly low but easy session OK: {today_hrv:.1f}", "MEDIUM"
        
        elif today_hrv >= threshold_optimal:
            # Normal or elevated
            return planned_session, f" HRV NORMAL: {today_hrv:.1f}  {threshold_optimal:.1f}  Proceed", "HIGH"
        
        else:
            # Between caution and optimal
            return planned_session, f"HRV acceptable: {today_hrv:.1f}", "MEDIUM"
    
    @staticmethod
    def calculate_rmssd_from_rr_intervals(rr_intervals_ms):
        """
        Calculate rMSSD from RR intervals (for those with HRV monitors)
        
        rMSSD = sqrt(mean(successive_differences))
        """
        if len(rr_intervals_ms) < 2:
            return None
        
        diffs_squared = []
        for i in range(len(rr_intervals_ms) - 1):
            diff = rr_intervals_ms[i+1] - rr_intervals_ms[i]
            diffs_squared.append(diff** 2)
        
        mean_squared = sum(diffs_squared) / len(diffs_squared)
        rmssd = mean_squared** 0.5
        
        return round(rmssd, 1)
    
    def get_trend_analysis(self):
        """
        Analyze HRV trend over time
        """
        if len(self.hrv_log) < 14:
            return "Need 14+ days for trend analysis"
        
        recent_week = [hrv for _, hrv in self.hrv_log[-7:]]
        previous_week = [hrv for _, hrv in self.hrv_log[-14:-7]]
        
        recent_avg = sum(recent_week) / len(recent_week)
        previous_avg = sum(previous_week) / len(previous_week)
        
        change_pct = ((recent_avg - previous_avg) / previous_avg) * 100
        
        if change_pct > 5:
            return f" IMPROVING: HRV up {change_pct:.1f}% (recovery/adaptation)"
        elif change_pct < -5:
            return f" DECLINING: HRV down {change_pct:.1f}% (fatigue accumulating)"
        else:
            return f" STABLE: HRV change {change_pct:.1f}%"


# ==============================================================================
# TIER 2: PERFORMANCE TRACKING
# ==============================================================================

# ------------------------------------------------------------------------------
# DURABILITY INDEX (Maunder et al. 2021 - The New Frontier)
# ------------------------------------------------------------------------------
class DurabilityEngine:
    """
    Durability = How well you maintain performance when fatigued
    
    Scientific Basis:
    - Maunder, E. et al. (2021). Sports Med, 51, 1619-1628.
    - Spragg, J. et al. (2023). Med Sci Sports Exerc, 55(12), 2241-2250.
    - Clark et al. (2019). "Durability: A new dimension of fitness"
    
    Key Insight:
    Traditional metrics (VO2max, FTP, LT) are measured FRESH.
    But races are won by those who maintain performance when FATIGUED.
    
    Example:
    Athlete A: VO2max 70  drops to 60 after 2h (-14%)
    Athlete B: VO2max 65  drops to 62 after 2h (-5%)
     Athlete B wins the marathon despite lower "peak"
    """
    
    @staticmethod
    def assess_pace_durability(km_splits, target_pace_sec):
        """
        Analyze pace decay across a long run
        
        Args:
            km_splits: List of km split times (seconds)
            target_pace_sec: Target pace per km
        
        Returns:
            (decay_percentage, status, recommendation)
        """
        if len(km_splits) < 10:
            return None, "Need 10+ km run for durability assessment", None
        
        # Compare first third vs last third
        third = len(km_splits) // 3
        first_third = km_splits[:third]
        last_third = km_splits[-third:]
        
        avg_first = sum(first_third) / len(first_third)
        avg_last = sum(last_third) / len(last_third)
        
        pace_decay_pct = ((avg_last - avg_first) / avg_first) * 100
        
        # Status interpretation
        if pace_decay_pct < 0:
            status = " NEGATIVE SPLIT (exceptional durability)"
            recommendation = "Elite-level durability - maintain training"
        elif pace_decay_pct < 2:
            status = " EXCELLENT durability (<2% fade)"
            recommendation = "Strong durability - ready for long races"
        elif pace_decay_pct < 5:
            status = " GOOD durability (<5% fade)"
            recommendation = "Solid - acceptable for most races"
        elif pace_decay_pct < 8:
            status = " MODERATE fade (<8%)"
            recommendation = "Work on aerobic base & long runs"
        else:
            status = " POOR durability (>8% fade)"
            recommendation = "Priority: Build aerobic base, add volume"
        
        return round(pace_decay_pct, 1), status, recommendation
    
    @staticmethod
    def calculate_durability_index(fresh_performance, fatigued_performance):
        """
        Durability Index = (Fresh Performance / Fatigued Performance)  100
        
        Higher = better durability
        
        Example:
        - Fresh 5K: 19:00 (3:48/km = 228 sec)
        - After 25K: 5K @ 20:00 (4:00/km = 240 sec)
        - DI = (228 / 240)  100 = 95%
        
        Args:
            fresh_performance: Time in seconds (shorter = better)
            fatigued_performance: Time in seconds (shorter = better)
        """
        if fresh_performance == 0 or fatigued_performance == 0:
            return None, "Invalid performance data"
        
        di = (fresh_performance / fatigued_performance) * 100
        
        if di >= 98:
            status = " ELITE durability (98%+)"
            tier = "WORLD CLASS"
        elif di >= 95:
            status = " EXCELLENT durability (95-98%)"
            tier = "ELITE"
        elif di >= 90:
            status = " GOOD durability (90-95%)"
            tier = "COMPETITIVE"
        elif di >= 85:
            status = " MODERATE durability (85-90%)"
            tier = "DEVELOPING"
        else:
            status = " NEEDS IMPROVEMENT (<85%)"
            tier = "NOVICE"
        
        return round(di, 1), status, tier
    
    @staticmethod
    def durability_training_protocol(current_di):
        """
        Training recommendations based on Maunder et al. (2021)
        """
        protocols = []
        
        if current_di < 88:
            protocols = [
                " PRIORITY 1: Build aerobic base (80% of runs easy)",
                "Add weekly long run (90-120 min minimum)",
                "Include 'depleted state' runs (morning fasted, 60-90 min)",
                "Progressive long runs: Start easy, finish at tempo",
                "Back-to-back quality: Saturday tempo + Sunday long",
                "Reduce intervals temporarily - focus on volume"
            ]
        elif current_di < 93:
            protocols = [
                "Maintain weekly long run (2h+)",
                "Add 'fatigued intervals': Easy run  then intervals",
                "Monthly: Tempo after easy mileage (durability stimulus)",
                "One long run per month: Progressive with Hammer finish"
            ]
        elif current_di < 96:
            protocols = [
                " Durability strong - maintain current approach",
                "Occasional durability check: Long run with fast finish",
                "Focus can shift to speed/power work"
            ]
        else:
            protocols = [
                " ELITE durability maintained",
                "No specific durability work needed",
                "Use this as competitive advantage in long races"
            ]
        
        return protocols


# ------------------------------------------------------------------------------
# EFFICIENCY FACTOR ENGINE (Friel 2009, Esteve-Lanao 2005)
# ------------------------------------------------------------------------------
class EfficiencyEngine:
    """
    Efficiency Factor = Aerobic fitness proxy
    
    Scientific Basis:
    - Friel, J. (2009). The Triathlete's Training Bible
    - Esteve-Lanao et al. (2005). Med Sci Sports Exerc (cardiac drift)
    - Lamberts, R.P. et al. (2011). Int J Sports Physiol Perform, 6(4), 461-473
    
    Concept:
    EF = Speed / Heart Rate
    Higher EF = more aerobically efficient
    
    Decoupling:
    First half EF vs Second half EF
    <5% = excellent aerobic fitness
    >10% = poor aerobic base or glycogen depleted
    """
    
    def __init__(self):
        self.ef_history = []
    
    @staticmethod
    def calculate_efficiency_factor(avg_pace_sec_per_km, avg_hr):
        """
        EF = speed (m/s) / HR
        
        Example:
        5:00/km = 3.33 m/s @ 150 HR
        EF = 3.33 / 150 = 0.0222
        
        Higher = more efficient
        """
        if avg_hr == 0:
            return None
        
        speed_m_per_s = 1000.0 / avg_pace_sec_per_km
        ef = speed_m_per_s / avg_hr
        
        return round(ef, 5)
    
    @staticmethod
    def calculate_decoupling(first_half_pace, first_half_hr, 
                            second_half_pace, second_half_hr):
        """
        Decoupling = (EF_second - EF_first) / EF_first  100
        
        Negative = worsening efficiency (normal for long runs)
        
        Interpretation (Friel 2009):
        <5%: Excellent aerobic fitness
        5-10%: Moderate drift (acceptable)
        >10%: Poor aerobic base or nutritional issue
        """
        ef_first = EfficiencyEngine.calculate_efficiency_factor(first_half_pace, first_half_hr)
        ef_second = EfficiencyEngine.calculate_efficiency_factor(second_half_pace, second_half_hr)
        
        if ef_first is None or ef_second is None or ef_first == 0:
            return None, "Invalid data"
        
        decoupling_pct = ((ef_second - ef_first) / ef_first) * 100
        
        if abs(decoupling_pct) < 3:
            status = " ELITE aerobic fitness (<3% decoupling)"
        elif abs(decoupling_pct) < 5:
            status = " EXCELLENT aerobic fitness (<5%)"
        elif abs(decoupling_pct) < 10:
            status = " MODERATE drift (<10% - acceptable for long runs)"
        else:
            status = " HIGH decoupling (>10% - improve base or refuel)"
        
        return round(decoupling_pct, 1), status
    
    def add_ef_measurement(self, date, ef_value):
        """Log EF for trend tracking"""
        self.ef_history.append((date, ef_value))
    
    def analyze_ef_trend(self, weeks=3):
        """
        Track EF improvement over time
        Rising EF = improving aerobic fitness at same HR
        """
        if len(self.ef_history) < weeks * 2:
            return "Need more data for trend analysis"
        
        days_per_week = 7
        recent_period = weeks * days_per_week
        
        recent = [ef for _, ef in self.ef_history[-recent_period:]]
        previous = [ef for _, ef in self.ef_history[-(recent_period*2):-recent_period]]
        
        if not previous:
            return "Need historical data"
        
        recent_avg = sum(recent) / len(recent)
        previous_avg = sum(previous) / len(previous)
        
        improvement_pct = ((recent_avg - previous_avg) / previous_avg) * 100
        
        if improvement_pct > 3:
            return f" IMPROVING: EF up {improvement_pct:.1f}% (aerobic gains)"
        elif improvement_pct < -3:
            return f" DECLINING: EF down {improvement_pct:.1f}% (check fatigue/volume)"
        else:
            return f" STABLE: EF change {improvement_pct:.1f}%"


# ==============================================================================
# TIER 3: ADVANCED METRICS
# ==============================================================================

# ------------------------------------------------------------------------------
# TRIMP ENGINE (Banister 1975, Edwards 1993)
# ------------------------------------------------------------------------------
class TRIMPEngine:
    """
    Training Impulse - HR-weighted load quantification
    
    Scientific Basis:
    - Banister, E.W. (1975). Aust J Sports Med, 7(3), 57-61
    - Edwards, S. (1993). The Heart Rate Monitor Book
    - Manzi, V. et al. (2009). Int J Sports Physiol Perform, 4(3), 347-357
    - Lucia, A. et al. (2003). Med Sci Sports Exerc (validation in cyclists)
    
    Why better than volume alone:
    10km @ 140 HR  10km @ 165 HR
    TRIMP captures this difference
    """
    
    @staticmethod
    def calculate_edwards_trimp(duration_min, avg_hr, max_hr):
        """
        Edwards (1993) TRIMP - Zone-based method
        
        Zones:
        1 (50-60% HRmax): 1
      ** 2 (60-70% HRmax): 2
        3 (70-80% HRmax): 3
        4 (80-90% HRmax): 4
        5 (90-100% HRmax): 5
        
        TRIMP = duration  zone_multiplier
        """
        if max_hr == 0:
            return None
        
        hr_percent = (avg_hr / max_hr) * 100
        
        # Determine zone multiplier
        if hr_percent < 60:
            multiplier = 1
        elif hr_percent < 70:
            multiplier = 2
        elif hr_percent < 80:
            multiplier = 3
        elif hr_percent < 90:
            multiplier = 4
        else:  # >= 90%
            multiplier = 5
        
        trimp = duration_min * multiplier
        return trimp, multiplier
    
    @staticmethod
    def calculate_banister_trimp(duration_min, avg_hr, resting_hr, max_hr, gender='male'):
        """
        Banister (1975) TRIMP - Original exponential method
        
        More complex but more accurate
        Uses exponential weighting for intensity
        """
        if max_hr == resting_hr:
            return None
        
        hr_reserve = (avg_hr - resting_hr) / (max_hr - resting_hr)
        
        # Gender-specific exponent (Banister)
        if gender.lower() == 'male':
            y = 1.92
        else:  # female
            y = 1.67
        
        trimp = duration_min * hr_reserve * 0.64 * math.exp(y * hr_reserve)
        
        return round(trimp, 1)
    
    @staticmethod
    def weekly_trimp_analysis(weekly_trimp, baseline_trimp):
        """
        Compare weekly TRIMP to athlete's baseline
        Based on Manzi et al. (2009)
        """
        if baseline_trimp == 0:
            return "Need baseline TRIMP value"
        
        percent_change = ((weekly_trimp - baseline_trimp) / baseline_trimp) * 100
        
        if percent_change > 50:
            return " DANGEROUS SPIKE: Reduce >30%", "CRITICAL"
        elif percent_change > 30:
            return " SPIKE: High injury/illness risk", "HIGH_RISK"
        elif percent_change > 15:
            return " HIGH: Monitor fatigue closely", "ELEVATED"
        elif -10 <= percent_change <= 15:
            return " OPTIMAL PROGRESSION", "SAFE"
        elif -25 <= percent_change < -10:
            return " DELOAD WEEK (planned recovery)", "RECOVERY"
        else:
            return " SEVERE DELOAD (risk detraining)", "LOW"


# ------------------------------------------------------------------------------
# SESSION RPE (sRPE) ENGINE (Foster 2001)
# ------------------------------------------------------------------------------
class SessionRPEEngine:
    """
    Session RPE - Simple but effective load metric
    
    Scientific Basis:
    - Foster, C. et al. (2001). J Strength Cond Res, 15(1), 109-115
    - Correlation with TRIMP: r = 0.85
    - Validation: 1000+ athletes across sports
    
    Formula:
    sRPE = Duration (minutes)  RPE (1-10 scale)
    
    Advantages:
    - No HR monitor needed
    - Captures all stress (heat, altitude, illness)
    - Works for all sports
    
    30 min session notes taken 30 min post-session
    """
    
    @staticmethod
    def calculate_srpe(duration_min, session_rpe_1_10):
        """
        sRPE = Duration  RPE
        
        Example:
        60 min run @ RPE 7 = 420 sRPE
        """
        srpe = duration_min * session_rpe_1_10
        return srpe
    
    @staticmethod
    def interpret_srpe(srpe_value):
        """
        Rough interpretation (Foster guidelines)
        """
        if srpe_value < 200:
            return "EASY session"
        elif srpe_value < 400:
            return "MODERATE session"
        elif srpe_value < 600:
            return "HARD session"
        else:
            return "VERY HARD session"
    
    @staticmethod
    def weekly_srpe_analysis(weekly_srpe, previous_week_srpe):
        """
        Week-to-week change analysis
        """
        if previous_week_srpe == 0:
            return "Need previous week data"
        
        change_pct = ((weekly_srpe - previous_week_srpe) / previous_week_srpe) * 100
        
        if change_pct > 30:
            return f" SPIKE: +{change_pct:.0f}% vs last week (reduce load)"
        elif change_pct > 15:
            return f" HIGH: +{change_pct:.0f}% vs last week (monitor fatigue)"
        elif -10 <= change_pct <= 15:
            return f" SAFE: {change_pct:+.0f}% vs last week"
        else:
            return f" DELOAD: {change_pct:.0f}% vs last week"


# ------------------------------------------------------------------------------
# GLYCOGEN DEPLETION MODEL (Impellizzeri & Marcora 2007)
# ------------------------------------------------------------------------------
class GlycogenModel:
    """
    Estimate glycogen cost and refueling needs
    
    Scientific Basis:
    - Impellizzeri, F.M. & Marcora, S.M. (2007)
    - Bergstrm, J. & Hultman, E. (1967). Classic muscle biopsy studies
    - Burke, L.M. et al. (2011). Carbohydrate periodization
    
    Normal glycogen stores: ~400-500g (muscle + liver)
    Depletion rate depends on intensity
    """
    
    @staticmethod
    def estimate_glycogen_depletion(duration_min, intensity_pct_vo2max):
        """
        Estimate glycogen cost of session
        
        Depletion rates (approximate):
        <70% VO2max: ~1.0 g/min (mostly fat burning)
        70-85% VO2max: ~1.8 g/min (mixed fuel)
        >85% VO2max: ~2.5 g/min (glycogen-dependent)
        
        Args:
            duration_min: Session duration
            intensity_pct_vo2max: Average intensity (% VO2max)
        """
        if intensity_pct_vo2max > 85:
            rate_g_per_min = 2.5
            intensity_desc = "HIGH (intervals/race)"
        elif intensity_pct_vo2max > 75:
            rate_g_per_min = 1.8
            intensity_desc = "MODERATE-HIGH (tempo)"
        elif intensity_pct_vo2max > 65:
            rate_g_per_min = 1.2
            intensity_desc = "MODERATE (steady)"
        else:
            rate_g_per_min = 0.8
            intensity_desc = "EASY (fat burning)"
        
        total_depleted = duration_min * rate_g_per_min
        
        # Refueling recommendation (Burke et al.)
        # Optimal: 1.2-1.5 g carbs/kg bodyweight within 2h post
        
        return {
            "glycogen_depleted_g": round(total_depleted, 0),
            "intensity_classification": intensity_desc,
            "depletion_rate": rate_g_per_min,
            "refuel_recommendation": "1.2-1.5 g carbs/kg within 2h post-session"
        }
    
    @staticmethod
    def daily_carb_recommendation(weight_kg, training_load_category):
        """
        Daily carb needs based on training load
        Burke et al. (2011) guidelines
        
        Args:
            weight_kg: Body weight
            training_load_category: "LIGHT", "MODERATE", "HIGH", "VERY_HIGH"
        """
        recommendations = {
            "LIGHT": (3, 5, "Easy recovery days"),
            "MODERATE": (5, 7, "Base training"),
            "HIGH": (6, 10, "Normal training load"),
            "VERY_HIGH": (8, 12, "Heavy training blocks / race prep")
        }
        
        if training_load_category not in recommendations:
            training_load_category = "MODERATE"
        
        low, high, context = recommendations[training_load_category]
        
        return {
            "carbs_g_per_kg_low": low,
            "carbs_g_per_kg_high": high,
            "total_carbs_range": f"{int(low * weight_kg)}-{int(high * weight_kg)}g",
            "context": context
        }


# ------------------------------------------------------------------------------
# RCP DETECTION ENGINE (Meyer 2005 - Respiratory Compensation Point)
# ------------------------------------------------------------------------------
class ReadinessEngine:
    @staticmethod
    def analyze_readiness(today_hrv, baseline_hrv, today_rhr, baseline_rhr, sleep_score, soreness_1_10):
        score = 100
        hrv_diff = today_hrv - baseline_hrv
        if hrv_diff < -10:
            score -= 20
        elif hrv_diff < -5:
            score -= 10
        elif hrv_diff > 15:
            score -= 5
        rhr_diff = today_rhr - baseline_rhr
        if rhr_diff > 5:
            score -= 15
        if sleep_score < 70:
            score -= 15
        elif sleep_score < 85:
            score -= 5
        if soreness_1_10 >= 7:
            score -= 20
        elif soreness_1_10 >= 5:
            score -= 10
        if score >= 80:
            return score, " GREEN LIGHT"
        if score >= 50:
            return score, " ORANGE LIGHT"
        return score, " RED LIGHT"


# ------------------------------------------------------------------------------
# HEAT / WEATHER ENGINE
# ------------------------------------------------------------------------------
class HeatEngine:
    @staticmethod
    def dew_point(temp_c, humidity):
        return temp_c - ((100 - humidity) / 5.0)

    @staticmethod
    def heat_status(temp_c, humidity):
        dew = HeatEngine.dew_point(temp_c, humidity)
        msg = " CONDITIONS STABLE"
        is_high_heat = False
        penalty_msg = "NONE"
        if dew >= 24:
            msg = " EXTREME DANGER (ABORT HARD SESSION)"
            is_high_heat = True
            penalty_msg = "SPLIT / DOWNGRADE"
        elif dew >= 20:
            msg = " HIGH STRESS (HEART RATE DRIFT LIKELY)"
            is_high_heat = True
            penalty_msg = "MANDATORY SPLIT (e.g. 2x3.5km)"
        elif dew >= 16:
            msg = " MODERATE HEAT (PERFORMANCE IMPACT)"
            is_high_heat = True
            penalty_msg = "SPLIT TEMPO RECOMMENDED"
        return dew, msg, is_high_heat, penalty_msg


# ------------------------------------------------------------------------------
# SESSION BUILDER (FULL TEXT)
# ------------------------------------------------------------------------------
class SessionBuilder:
    def __init__(self, profile: TitanProfile, memory: AdaptiveMemory):
        self.profile = profile
        self.memory = memory

    def get_paces(self):
        f = self.memory.adaptive_pace_factor
        p5k = self.profile.base_5k_sec * f
        def s(sec): return self.profile.sec_to_str(sec)
        return {
            "EASY": f"{s(p5k * 1.32)} - {s(p5k * 1.45)}",
            "TEMPO": s(p5k * 1.08),
            "VO2MAX": s(p5k * 0.98),
            "SPEED": s(p5k * 0.90),
            "LONG": s(p5k * 1.35)
        }

    def build(self, session_type, is_high_heat=False):
        z = self.get_paces()
        st = session_type.upper()

        if st == "TEMPO":
            if is_high_heat:
                return {
                    "TITLE": "THRESHOLD RUN (HEAT PROTOCOL)",
                    "WARMUP": "15' Easy + 4x Strides.",
                    "MAIN": [
                        " HEAT DETECTED: Use SPLIT TEMPO.",
                        f"SET 1: 3.5km @ {z['TEMPO']}/km",
                        "RECOVERY: 2-3' walk/jog.",
                        f"SET 2: 3.5km @ {z['TEMPO']}/km",
                        "Goal: Maintain pace without HR drift."
                    ],
                    "COOLDOWN": "10-15' very easy."
                }
            return {
                "TITLE": "THRESHOLD RUN (Lactate Tolerance)",
                "WARMUP": "15' Easy + 4x Strides.",
                "MAIN": [
                    f"6-7km continuous @ {z['TEMPO']}/km",
                    "Goal: 'Comfortably hard', stable HR.",
                    "Target HR: 165-168 bpm."
                ],
                "COOLDOWN": "10-15' very easy."
            }

        if st == "INTERVALS":
            rest_time = "3:00" if is_high_heat else "2:00"
            return {
                "TITLE": "VO2 MAX BUILDER",
                "WARMUP": "20' Easy + 4x Strides + Dynamic drills.",
                "MAIN": [
                    f"6 x 1000m @ {z['VO2MAX']}/km",
                    f"Recovery: {rest_time} jog/walk.",
                    "Goal: Same time on all reps.",
                    "If pace drops >5s, stop."
                ],
                "COOLDOWN": "15' very easy."
            }

        if st == "PROGRESSIVE":
            return {
                "TITLE": "PROGRESSIVE RUN (Kenyan Style)",
                "WARMUP": "5' Walk/Jog.",
                "MAIN": [
                    "Total: 8km continuous.",
                    f"KM 1-5: Easy Zone ({z['EASY']}/km).",
                    "KM 6: Moderate.",
                    "KM 7: Hard.",
                    f"KM 8: Tempo ({z['TEMPO']}/km).",
                    "Goal: Negative split. Do NOT start fast."
                ],
                "COOLDOWN": "10' easy."
            }

        if st == "LONG_RUN":
            msg = "Hydrate every 20' (heat)." if is_high_heat else "Fast finish last 2km if feeling good."
            return {
                "TITLE": "AEROBIC CAPACITY (Sunday Long Run)",
                "WARMUP": "Start very slow for first 2km.",
                "MAIN": [
                    f"14-16km @ {z['LONG']}/km.",
                    f"Instruction: {msg}",
                    "Fuel: Gel/Honey every 40'."
                ],
                "COOLDOWN": "Stretch + Foam Roller."
            }

        if st in ["EASY", "RECOVERY_EASY"]:
            return {
                "TITLE": "RECOVERY / EASY RUN",
                "WARMUP": "-",
                "MAIN": [
                    "6-8km very easy.",
                    "HR < 145 bpm.",
                    "Focus: Relaxed form, breathing, mental reset."
                ],
                "COOLDOWN": "Light stretching."
            }

        if "RACE" in st:
            return {
                "TITLE": f"RACE EXECUTION ({st})",
                "WARMUP": "10-15' Easy + 4x Strides.",
                "MAIN": [
                    "Start controlled, no sprint at gun.",
                    "Lock into target pace by 1km.",
                    "Middle: Hold, don't panic.",
                    "Last 1km: Empty the tank."
                ],
                "COOLDOWN": "Walk + light jog + carbs within 30'."
            }

        return {
            "TITLE": "UNDEFINED SESSION",
            "WARMUP": "-",
            "MAIN": ["No session defined."],
            "COOLDOWN": "-"
        }


# ------------------------------------------------------------------------------
# PHASE & SCHEDULER
# ------------------------------------------------------------------------------
class PhaseEngine:
    @staticmethod
    def get_phase(current_date, race_day):
        if current_date > race_day:
            return "POST"
        delta = (race_day - current_date).days
        if delta > 60:
            return "BASE"
        if 21 < delta <= 60:
            return "BUILD"
        if 7 < delta <= 21:
            return "PEAK"
        if 0 <= delta <= 7:
            return "TAPER"
        return "UNKNOWN"

    @staticmethod
    def post_race_menu():
        print("\nPOST-RACE PATHS:")
        print("1. OFF (2 weeks total rest)")
        print("2. MAINT (3 easy runs/week)")
        print("3. 1K PROJECT")
        print("4. 5K PROJECT")
        print("5. 10K PROJECT")
        print("6. 21K PROJECT")
        print("7. 42K PROJECT")
        choice = input("Select Path (1-7): ")
        mapping = {
            "1": "OFF",
            "2": "MAINT",
            "3": "1K",
            "4": "5K",
            "5": "10K",
            "6": "21K",
            "7": "42K"
        }
        return mapping.get(choice, "MAINT")


class Scheduler:
    @staticmethod
    def get_planned_session(date_obj, race_day):
        wd = date_obj.weekday()
        if date_obj > race_day:
            return "EASY"
        if wd == 5:
            return "PROGRESSIVE"
        if wd == 6:
            return "LONG_RUN"
        if wd == 1:
            return "INTERVALS"
        if wd == 3:
            return "TEMPO"
        return "REST"


# ------------------------------------------------------------------------------
# MAIN SYSTEM CORE
# ------------------------------------------------------------------------------
class EquipmentManager:
    """
    Διαχείριση Παπουτσιών & Εδάφους
    Training Intent Awareness
    """
    def __init__(self):
        # Demo database - Στην πράξη θα σώζονται στο JSON
        self.shoes = {
            "1": {"name": "Daily Trainers (Pegasus)", "km": 450, "max_km": 800, "type": "DAILY"},
            "2": {"name": "Super Shoes (Vaporfly)", "km": 120, "max_km": 400, "type": "RACE"},
            "3": {"name": "Old Beaters", "km": 950, "max_km": 800, "type": "RECOVERY"}
        }

    def check_gear(self, session_type, shoe_id, surface):
        """
        Ελέγχει αν ο εξοπλισμός ταιριάζει με την προπόνηση
        """
        shoe = self.shoes.get(shoe_id)
        if not shoe:
            return False, "Unknown Shoe"

        risk_flags = []
        
        # 1. Mileage Check
        if shoe["km"] > shoe["max_km"]:
            risk_flags.append(f"SHOE EXPIRED ({shoe['km']}km). Risk of injury.")

        # 2. Type Mismatch (Intent Awareness)
        if session_type in ["INTERVALS", "TEMPO", "HAMMER"] and shoe["type"] == "RECOVERY":
            return False, "BLOCK: Cannot run Fast in Recovery shoes."
        
        if session_type == "EASY" and shoe["type"] == "RACE":
            risk_flags.append("WASTE: Using Super Shoes for easy run.")

        # 3. Surface Logic
        if session_type == "INTERVALS" and surface == "CONCRETE":
            risk_flags.append("SURFACE RISK: High impact intervals on concrete.")

        if risk_flags:
            return True, " | ".join(risk_flags)
        
        return True, "GEAR OK"


class EliteCoachingStrategy:
    """
    The Brain: Risk Score, Confidence & Block States
    """
    
    @staticmethod
    def calculate_risk_profile(acwr, tsb, hrv_status, sleep_score, soreness, shoe_risk_msg):
        """
        Υπολογίζει το συνολικό ρίσκο (0-100%)
        """
        risk_score = 0
        factors = []

        # 1. Load Risk (ACWR)
        if acwr > 1.5: 
            risk_score += 40
            factors.append("ACWR Spike (>1.5)")
        elif acwr > 1.3:
            risk_score += 20

        # 2. Fatigue State (TSB)
        if tsb and tsb < -30:
            risk_score += 20
            factors.append("Deep Fatigue (TSB <-30)")

        # 3. Recovery (HRV/Sleep)
        if hrv_status == "LOW":
            risk_score += 25
            factors.append("CNS Stress (Low HRV)")
        if sleep_score < 60:
            risk_score += 15
            factors.append("Poor Sleep")

        # 4. Mechanical (Soreness/Shoes)
        if soreness >= 7:
            risk_score += 30
            factors.append("High Soreness")
        if "EXPIRED" in shoe_risk_msg or "SURFACE" in shoe_risk_msg:
            risk_score += 15
            factors.append("Equipment Risk")

        risk_score = min(100, risk_score)
        return risk_score, factors

    @staticmethod
    def get_session_permission(session_type, risk_score, factors):
        """
        Αποφασίζει αν ΕΠΙΤΡΕΠΕΤΑΙ η προπόνηση (Binary Decision)
        Override Hierarchy: Safety > Plan
        """
        # Traffic Light System
        if risk_score >= 75:
            traffic_light = "RED"
        elif risk_score >= 40:
            traffic_light = "ORANGE"
        else:
            traffic_light = "GREEN"

        # BLOCK LOGIC (The "No" state)
        if traffic_light == "RED":
            if session_type in ["INTERVALS", "TEMPO", "LONG_RUN", "HAMMER", "PROGRESSIVE"]:
                return {
                    "allowed": False,
                    "action": "BLOCKED",
                    "reason": f"HIGH RISK ({risk_score}%). Factors: {', '.join(factors)}",
                    "override_session": "RECOVERY_EASY" # Forced downgrade
                }
        
        if traffic_light == "ORANGE":
            if session_type in ["INTERVALS", "HAMMER"]:
                return {
                    "allowed": True, # Allowed but warned
                    "action": "CAUTION",
                    "reason": f"MODERATE RISK ({risk_score}%). Consider downgrading intensity.",
                    "override_session": None
                }

        return {
            "allowed": True,
            "action": "GO",
            "reason": "System Confidence High.",
            "override_session": None
        }

# ==============================================================================
# v48 ULTIMATE PLUS - PROFESSIONAL FEATURES
# ==============================================================================

class RacePacingStrategy:
    '''Race pacing strategy calculator'''
    
    @staticmethod
    def calculate_optimal_splits(goal_time_sec, distance_km, elevation_profile, durability_index):
        base_pace = goal_time_sec / distance_km
        
        if durability_index < 90:
            early_adj = 0.95
            late_adj = 1.05
            strategy = "CONSERVATIVE_START"
        elif durability_index >= 95:
            early_adj = 1.02
            late_adj = 0.98
            strategy = "NEGATIVE_SPLIT"
        else:
            early_adj = 1.0
            late_adj = 1.0
            strategy = "EVEN_PACE"
        
        splits = []
        cumulative = 0
        
        for km in range(int(distance_km)):
            if km < len(elevation_profile):
                elev = elevation_profile[km]
                if elev > 10:
                    pace_adj = 1 + (elev / 100) * 0.10
                elif elev < -10:
                    pace_adj = 1 - (abs(elev) / 100) * 0.05
                else:
                    pace_adj = 1.0
            else:
                pace_adj = 1.0
            
            if km < distance_km / 3:
                timing_adj = early_adj
            elif km > 2 * distance_km / 3:
                timing_adj = late_adj
            else:
                timing_adj = 1.0
            
            split_pace = base_pace * pace_adj * timing_adj
            cumulative += split_pace
            
            splits.append({
                "km": km + 1,
                "pace_sec": round(split_pace, 1),
                "cumulative_sec": round(cumulative, 1),
                "elevation": elevation_profile[km] if km < len(elevation_profile) else 0
            })
        
        return {
            "splits": splits,
            "strategy": strategy,
            "confidence": "HIGH" if durability_index >= 90 else "MODERATE"
        }
    
    @staticmethod
    def weather_adjustment(base_pace_sec, temp_c, humidity_pct):
        if temp_c <= 15:
            temp_factor = 1.0
        elif temp_c <= 20:
            temp_factor = 1.01
        elif temp_c <= 25:
            temp_factor = 1.03
        else:
            temp_factor = 1.05 + ((temp_c - 25) / 5) * 0.02
        
        humidity_factor = 1.02 if humidity_pct > 70 else 1.0
        
        return round(base_pace_sec * temp_factor * humidity_factor, 1)
    
    @staticmethod
    def course_difficulty_score(elevation_profile):
        total_gain = sum(max(0, e) for e in elevation_profile)
        total_loss = sum(abs(min(0, e)) for e in elevation_profile)
        
        distance_km = len(elevation_profile)
        avg_gain_per_km = total_gain / distance_km if distance_km > 0 else 0
        
        if avg_gain_per_km < 5:
            difficulty = 10
            category = "FLAT"
        elif avg_gain_per_km < 15:
            difficulty = 30
            category = "ROLLING"
        elif avg_gain_per_km < 30:
            difficulty = 55
            category = "HILLY"
        else:
            difficulty = 85
            category = "MOUNTAINOUS"
        
        return {
            "difficulty": difficulty,
            "category": category,
            "total_gain": total_gain,
            "total_loss": total_loss,
            "avg_gain_per_km": round(avg_gain_per_km, 1)
        }


class RecoveryScoreEngine:
    '''Multi-factor recovery assessment'''
    
    def __init__(self):
        self.recovery_log = []
        self.baseline_hrv = None
    
    def set_baseline_hrv(self, hrv_value):
        self.baseline_hrv = hrv_value
    
    def calculate_recovery_score(self, hrv_value, sleep_hours, sleep_quality_1_10, 
                                 soreness_1_10, mood_1_10):
        
        if self.baseline_hrv:
            hrv_percent = (hrv_value / self.baseline_hrv) * 100
        else:
            hrv_percent = min(100, (hrv_value / 50) * 100)
        
        if hrv_percent >= 100:
            hrv_score = 100
        elif hrv_percent >= 95:
            hrv_score = 90
        elif hrv_percent >= 90:
            hrv_score = 75
        elif hrv_percent >= 85:
            hrv_score = 60
        else:
            hrv_score = max(20, hrv_percent - 25)
        
        sleep_duration_score = min(100, (sleep_hours / 8) * 100)
        sleep_quality_score = sleep_quality_1_10 * 10
        sleep_score = (sleep_duration_score + sleep_quality_score) / 2
        
        soreness_score = (10 - soreness_1_10) * 10
        mood_score = mood_1_10 * 10
        
        total_score = (
            hrv_score * 0.40 +
            sleep_score * 0.30 +
            soreness_score * 0.20 +
            mood_score * 0.10
        )
        
        entry = {
            "date": datetime.now(),
            "score": round(total_score, 1),
            "hrv": hrv_value,
            "sleep_hours": sleep_hours
        }
        self.recovery_log.append(entry)
        
        if total_score >= 85:
            status = "[OK] FULLY RECOVERED"
            rec = "Ready for hard training"
        elif total_score >= 70:
            status = "[OK] WELL RECOVERED"
            rec = "Normal training OK"
        elif total_score >= 55:
            status = "[WARN] MODERATE"
            rec = "Easy session or reduce intensity 20%"
        elif total_score >= 40:
            status = "[!] POOR RECOVERY"
            rec = "Rest day or very easy only"
        else:
            status = "[!!] SEVERELY FATIGUED"
            rec = "MANDATORY REST"
        
        return round(total_score, 1), status, rec
    
    def predict_recovery_timeline(self, current_score):
        if current_score >= 85:
            return "Already fully recovered"
        
        points_needed = 85 - current_score
        days_needed = points_needed / 10
        
        if days_needed < 1:
            return f"{int(days_needed * 24)} hours with rest"
        else:
            return f"{days_needed:.1f} days with rest"
    
    def weekly_recovery_trend(self, days=7):
        if len(self.recovery_log) < days:
            return None
        
        recent = self.recovery_log[-days:]
        scores = [e["score"] for e in recent]
        
        avg_score = sum(scores) / len(scores)
        
        if len(scores) >= 3:
            early_avg = sum(scores[:3]) / 3
            late_avg = sum(scores[-3:]) / 3
            
            if late_avg > early_avg + 5:
                trend = "IMPROVING"
            elif late_avg < early_avg - 5:
                trend = "DECLINING"
            else:
                trend = "STABLE"
        else:
            trend = "INSUFFICIENT_DATA"
        
        return {
            "avg_score": round(avg_score, 1),
            "trend": trend,
            "lowest_score": min(scores),
            "highest_score": max(scores)
        }


class WearableSync:
    '''Wearable data sync'''
    
    def __init__(self):
        self.last_sync = None
        self.sync_history = []
    
    def import_garmin_csv(self, filepath):
        if not PANDAS_AVAILABLE:
            return None, "pandas required"
        
        try:
            import pandas as pd
            df = pd.read_csv(filepath)
            
            sessions = []
            
            for _, row in df.iterrows():
                try:
                    date = pd.to_datetime(row.get("Date"))
                except:
                    date = datetime.now()
                
                session = {
                    "date": date,
                    "type": row.get("Activity Type", "Run"),
                    "distance_km": float(row.get("Distance", 0)),
                    "duration_sec": self._parse_time_str(str(row.get("Time", "0:00:00"))),
                    "avg_hr": float(row.get("Avg HR", 0)) if pd.notna(row.get("Avg HR")) else None,
                    "max_hr": float(row.get("Max HR", 0)) if pd.notna(row.get("Max HR")) else None
                }
                
                if session["distance_km"] > 0 and session["duration_sec"] > 0:
                    session["pace_sec_per_km"] = session["duration_sec"] / session["distance_km"]
                else:
                    session["pace_sec_per_km"] = 0
                
                sessions.append(session)
            
            self.last_sync = datetime.now()
            self.sync_history.append({
                "date": self.last_sync,
                "source": "Garmin CSV",
                "sessions_imported": len(sessions)
            })
            
            return sessions, f"[OK] Imported {len(sessions)} sessions"
        
        except Exception as e:
            return None, f"[ERROR] {str(e)}"
    
    def import_stryd_csv(self, filepath):
        if not PANDAS_AVAILABLE:
            return None, "pandas required"
        
        try:
            import pandas as pd
            df = pd.read_csv(filepath)
            
            sessions = []
            
            for _, row in df.iterrows():
                session = {
                    "date": pd.to_datetime(row.get("Date")),
                    "distance_km": float(row.get("Distance", 0)),
                    "duration_sec": float(row.get("Duration", 0)),
                    "avg_power": float(row.get("Power", 0)) if pd.notna(row.get("Power")) else None,
                    "cadence": float(row.get("Cadence", 0)) if pd.notna(row.get("Cadence")) else None,
                    "gct_ms": float(row.get("Ground Contact Time", 0)) if pd.notna(row.get("Ground Contact Time")) else None,
                    "vert_osc_cm": float(row.get("Vertical Oscillation", 0)) if pd.notna(row.get("Vertical Oscillation")) else None
                }
                
                sessions.append(session)
            
            self.last_sync = datetime.now()
            self.sync_history.append({
                "date": self.last_sync,
                "source": "Stryd CSV",
                "sessions_imported": len(sessions)
            })
            
            return sessions, f"[OK] Imported {len(sessions)} Stryd sessions"
        
        except Exception as e:
            return None, f"[ERROR] {str(e)}"
    
    @staticmethod
    def _parse_time_str(time_str):
        try:
            parts = time_str.strip().split(':')
            
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            elif len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            else:
                return 0
        except:
            return 0
    
    def get_sync_summary(self):
        if not self.sync_history:
            return "No syncs performed"
        
        total_sessions = sum(s["sessions_imported"] for s in self.sync_history)
        
        return {
            "total_syncs": len(self.sync_history),
            "total_sessions_imported": total_sessions,
            "last_sync": self.last_sync,
            "sources_used": list(set(s["source"] for s in self.sync_history))
        }

# ==============================================================================
# TITAN v48 ULTIMATE - ADDITIONAL FEATURES
# ==============================================================================

class GradeAdjustedPace:
    """Grade Adjusted Pace"""
    
    @staticmethod
    def calculate_gap(pace_sec_per_km, elevation_gain_m, distance_km):
        if distance_km == 0:
            return pace_sec_per_km
        avg_gradient = (elevation_gain_m / (distance_km * 1000)) * 100
        if avg_gradient > 0:
            adjustment = 1 + (avg_gradient * 0.10)
        else:
            adjustment = 1 + (avg_gradient * 0.05)
        return round(pace_sec_per_km / adjustment, 1)
    
    @staticmethod
    def calculate_elevation_cost(elevation_gain_m, weight_kg):
        return round(elevation_gain_m * weight_kg * 0.5, 0)


class RunningPower:
    """Running Power"""
    
    @staticmethod
    def estimate_power(speed_m_per_s, weight_kg, gradient=0):
        import math
        g = 9.81
        k = 0.5
        angle_rad = math.atan(gradient / 100)
        p_gravity = weight_kg * g * speed_m_per_s * math.sin(angle_rad) if gradient != 0 else 0
        p_air = k * (speed_m_per_s** 3)
        p_base = weight_kg * 1.0
        return round(p_gravity + p_air + p_base, 0)
    
    @staticmethod
    def power_zones(ftp):
        return {
            "Z1": f"< {int(ftp * 0.55)} W",
            "Z2": f"{int(ftp * 0.55)}-{int(ftp * 0.75)} W",
            "Z3": f"{int(ftp * 0.75)}-{int(ftp * 0.90)} W",
            "Z4": f"{int(ftp * 0.90)}-{int(ftp * 1.05)} W",
            "Z5": f"> {int(ftp * 1.05)} W"
        }


class BiomechanicsAnalysis:
    """Biomechanics"""
    
    @staticmethod
    def optimal_cadence(height_cm):
        if height_cm >= 185:
            return (165, 175)
        elif height_cm >= 175:
            return (170, 180)
        else:
            return (175, 185)
    
    @staticmethod
    def stride_length(speed_m_s, cadence_spm):
        if cadence_spm == 0:
            return 0
        return round((speed_m_s * 60) / cadence_spm, 2)
    
    @staticmethod
    def analyze_form(cadence, vert_osc, gct):
        score = 100
        issues = []
        if cadence < 160:
            score -= 15
            issues.append("Low cadence")
        if vert_osc > 12:
            score -= 15
            issues.append("High bounce")
        if gct > 280:
            score -= 10
            issues.append("Long contact")
        status = "[OK] GOOD" if score >= 70 else "[WARN] NEEDS WORK"
        return score, status, issues


class MenstrualCycleTracking:
    """Cycle tracking"""
    
    def __init__(self):
        self.cycle_length = 28
    
    def get_phase(self, day):
        if day <= 5:
            return "MENSTRUATION"
        elif day <= 14:
            return "FOLLICULAR"
        elif day <= 16:
            return "OVULATION"
        elif day <= 21:
            return "EARLY_LUTEAL"
        else:
            return "LATE_LUTEAL"
    
    def get_rec(self, day):
        phase = self.get_phase(day)
        recs = {
            "MENSTRUATION": "Easy-moderate",
            "FOLLICULAR": "OPTIMAL - push hard",
            "OVULATION": "Good but careful",
            "EARLY_LUTEAL": "Moderate",
            "LATE_LUTEAL": "Easier sessions"
        }
        return recs.get(phase, "Normal")


class AltitudeTracker:
    """Altitude"""
    
    def __init__(self):
        self.home_alt = 0
        self.accl_days = 0
    
    def set_home(self, alt):
        self.home_alt = alt
    
    @staticmethod
    def pace_adj(home, training):
        if training <= 1500:
            return 1.0
        diff = training - max(home, 1500)
        return round(1 + (diff / 300) * 0.015, 3)
    
    def status(self):
        if self.accl_days <= 3:
            return "ACUTE", "Easy only"
        elif self.accl_days <= 14:
            return "ADAPTING", "Moderate OK"
        else:
            return "ACCLIMATIZED", "Full capacity"


class ScheduleManager:
    """Schedule"""
    
    def __init__(self):
        self.avail_days = []
    
    def set_days(self, days):
        self.avail_days = sorted(days)
    
    def generate(self, priorities):
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        sched = {}
        for i, day_num in enumerate(self.avail_days):
            if i < len(priorities):
                sched[day_names[day_num]] = priorities[i]
            else:
                sched[day_names[day_num]] = "EASY"
        for i in range(7):
            if i not in self.avail_days:
                sched[day_names[i]] = "REST"
        return sched


class ProgressAnalyzer:
    """Progress"""
    
    def __init__(self, goal_sec, dist_km, race_date):
        self.goal_sec = goal_sec
        self.dist_km = dist_km
        self.race_date = race_date
        self.sessions = []
    
    def add(self, date, distance, time_sec):
        pace = time_sec / distance if distance > 0 else 0
        self.sessions.append({"date": date, "pace": pace})
    
    def probability(self):
        if not self.sessions:
            return 0, "No data"
        target = self.goal_sec / self.dist_km
        recent = self.sessions[-20:]
        avg = sum(s["pace"] for s in recent) / len(recent)
        diff = ((avg - target) / target) * 100
        if diff <= -5:
            return 85, "VERY LIKELY"
        elif diff <= 0:
            return 70, "LIKELY"
        elif diff <= 5:
            return 50, "POSSIBLE"
        else:
            return 30, "UNLIKELY"
    
    def interventions(self):
        prob, _ = self.probability()
        if prob < 50:
            return ["ADD intervals", "INCREASE volume 10%", "ADD tempo"]
        elif prob < 70:
            return ["MAINTAIN volume", "ADD goal pace work"]
        else:
            return ["MAINTAIN training", "PREPARE taper"]




class RCPEngine:
    """
    Respiratory Compensation Point - More precise than LTHR
    
    Scientific Basis:
    - Meyer, T. et al. (2005). Int J Sports Med, 26(S1), S38-S48
    - Luca, A. et al. (2000). Med Sci Sports Exerc, 32(10), 1777-1782
    - Wasserman, K. et al. (1986). Original RCP concept
    
    RCP = Point where lactate "explodes"
    More reliable than LT2/LTHR for threshold work
    
    Field Test Protocol:
    - 5 min @ easy
    - 5 min @ moderate
    - 5 min @ tempo
    - 5 min @ threshold
    - Look for HR:Pace ratio inflection
    """
    
    @staticmethod
    def estimate_rcp_from_progressive_test(pace_segments_sec, hr_segments, rpe_segments):
        """
        Detect RCP from progressive field test
        
        Args:
            pace_segments_sec: List of avg pace/km for each segment (seconds)
            hr_segments: List of avg HR for each segment
            rpe_segments: List of RPE for each segment
        
        Returns:
            (rcp_hr, rcp_pace, rcp_rpe, explanation)
        """
        if len(pace_segments_sec) < 4 or len(hr_segments) < 4:
            return None, None, None, "Need 4+ segments for RCP detection"
        
        # Calculate HR:Pace efficiency for each segment
        hr_pace_ratios = []
        for hr, pace in zip(hr_segments, pace_segments_sec):
            speed = 1000.0 / pace  # m/s
            ratio = hr / speed  # HR per m/s (higher = less efficient)
            hr_pace_ratios.append(ratio)
        
        # Find sharp inflection point (2nd derivative)
        for i in range(1, len(hr_pace_ratios) - 1):
            delta_before = hr_pace_ratios[i] - hr_pace_ratios[i-1]
            delta_after = hr_pace_ratios[i+1] - hr_pace_ratios[i]
            
            # RCP = where increase accelerates sharply
            if delta_after > delta_before * 1.5:
                rcp_hr = hr_segments[i]
                rcp_pace = pace_segments_sec[i]
                rcp_rpe = rpe_segments[i] if i < len(rpe_segments) else None
                
                explanation = f"RCP detected at segment {i+1}: Sharp efficiency drop"
                return rcp_hr, rcp_pace, rcp_rpe, explanation
        
        # If no clear inflection, estimate from highest sustainable
        rcp_hr = hr_segments[-2]  # Second-to-last segment
        rcp_pace = pace_segments_sec[-2]
        rcp_rpe = rpe_segments[-2] if len(rpe_segments) >= 2 else None
        
        return rcp_hr, rcp_pace, rcp_rpe, "RCP estimated (no clear inflection)"
    
    @staticmethod
    def rcp_training_zones(rcp_hr, max_hr):
        """
        Training zones based on RCP (Luca et al. 2000)
        
        Zone 1: Below VT1 (easy aerobic)
        Zone 2: VT1 to RCP (tempo/threshold)
        Zone 3: Above RCP (VO2max/anaerobic)
        """
        vt1_hr = rcp_hr * 0.85  # Approximate VT1
        
        zones = {
            "Zone 1 (Easy)": f"< {int(vt1_hr)} HR (< 85% RCP)",
            "Zone 2 (Threshold)": f"{int(vt1_hr)}-{int(rcp_hr)} HR (85-100% RCP)",
            "Zone 3 (VO2max)": f"> {int(rcp_hr)} HR (> RCP)",
            "RCP_HR": rcp_hr,
            "VT1_HR": int(vt1_hr)
        }
        
        return zones


# ------------------------------------------------------------------------------
# READINESS ENGINE
# ------------------------------------------------------------------------------


# ==============================================================================
# TITAN v48 UNIVERSAL ADDITIONS - ALL FEATURES
# ==============================================================================
class MLPerformancePredictor:
    """
    Machine Learning Performance Predictor
    
    IMPORTANT: Provides predictions, NOT decisions
    Decision layer remains rule-based
    
    Scientific Basis:
    - Mujika et al. (2014). ML in endurance prediction
    - Borresen & Lambert (2008). Training load models
    """
    
    def __init__(self):
        # ML Enhancements: Scaling and validation
        self.scaler = StandardScaler()
        self.is_trained = False
        logger.info("ML Predictor initialized with StandardScaler")
        
        self.model = None
        self.training_data = []
        self.feature_names = ['ctl', 'atl', 'hrv_avg', 'sleep_avg', 'recent_pace']
    
    def add_training_sample(self, ctl, atl, hrv_avg, sleep_avg, recent_pace, actual_time):
        """Add historical race data for model training"""
        self.training_data.append({
            'features': [ctl, atl, hrv_avg, sleep_avg, recent_pace],
            'result': actual_time
        })
    
    def train_model(self):
        """Train prediction model on historical data"""
        if not SKLEARN_AVAILABLE:
            return False, "scikit-learn not installed"
        
        if len(self.training_data) < 5:
            return False, "Need at least 5 race results for training"
        
        import numpy as np
        from sklearn.ensemble import RandomForestRegressor
        
        X = np.array([d['features'] for d in self.training_data])
        y = np.array([d['result'] for d in self.training_data])
        
        self.model = RandomForestRegressor(n_estimators=100, random_state=42)
        self.model.fit(X, y)
        
        return True, "Model trained successfully"
    
    def predict_performance(self, ctl, atl, hrv_avg, sleep_avg, recent_pace):
        """
        Predict race performance
        
        Returns:
            (predicted_time_sec, lower_bound, upper_bound, confidence)
        """
        if not self.model:
            return None, None, None, "Model not trained"
        
        import numpy as np
        features = np.array([[ctl, atl, hrv_avg, sleep_avg, recent_pace]])
        
        # Get prediction
        predicted_time = self.model.predict(features)[0]
        
        # Calculate confidence interval (±3% for moderate confidence)
        uncertainty = predicted_time * 0.03  # 3% margin
        
        lower_bound = predicted_time - uncertainty
        upper_bound = predicted_time + uncertainty
        
        # Determine confidence
        if len(self.training_data) >= 10:
            confidence = "HIGH"
        elif len(self.training_data) >= 5:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        
        return int(predicted_time), int(lower_bound), int(upper_bound), confidence

# Usage example:
predictor = MLPerformancePredictor()
# Add past races
predictor.add_training_sample(ctl=85, atl=75, hrv_avg=55, sleep_avg=7.5, recent_pace=240, actual_time=2400)
predictor.train_model()
# Predict
pred, low, high, conf = predictor.predict_performance(90, 80, 58, 8, 235)
if pred is not None and high is not None:
    margin = high - pred
    print(f"Predicted: {pred}s ± {margin}s (Confidence: {conf})")
else:
    print(f"Prediction unavailable. (Values: pred={pred}, high={high}, Confidence={conf})")

import random

class GeneticOptimization:
    """
    Genetic Algorithm for Training Parameters Optimization.
    Designed to work with TITAN v50 architecture.
    """
    def __init__(self, profile_type="BALANCED", population_size=50, mutation_rate=0.1):
        self.profile_type = profile_type
        self.pop_size = population_size
        self.mutation_rate = mutation_rate
        self.generations = 20
        # Ορισμός ορίων παραμέτρων (CTL, ATL, HRV, Sleep, Pace)
        # Προσαρμοσμένα για λογικές τιμές τρεξίματος
        self.bounds = [
            (40, 120),   # CTL (Chronic Load)
            (30, 130),   # ATL (Acute Load)
            (30, 100),   # HRV (ms)
            (5, 10),     # Sleep (hours)
            (180, 360)   # Pace (sec/km) - 3:00 to 6:00
        ]

    def create_individual(self):
        """Δημιουργία τυχαίου ατόμου εντός ορίων."""
        return [random.uniform(low, high) for low, high in self.bounds]

    def fitness(self, individual, predictor_model):
        """
        Υπολογίζει πόσο 'καλή' είναι μια λύση.
        Στόχος: Ελαχιστοποίηση χρόνου αγώνα (Predicted Time).
        """
        ctl, atl, hrv, sleep, pace = individual
        
        # Περιορισμοί ασφαλείας (Soft Constraints)
        # Αν το ATL είναι πολύ ψηλότερο από το CTL (Risk Injury), ποινή στο fitness
        penalty = 0
        if atl > ctl * 1.3:
            penalty += 1000 # Μεγάλη ποινή σε χρόνο
        
        try:
            # Καλούμε το μοντέλο ML για πρόβλεψη
            pred, _, _, _ = predictor_model.predict_performance(ctl, atl, hrv, sleep, pace)
            
            if pred is None:
                return float('inf')
            
            return pred + penalty
        except:
            return float('inf')

    def crossover(self, parent1, parent2):
        """Μονοσημειακή διασταύρωση."""
        point = random.randint(1, len(self.bounds) - 1)
        child1 = parent1[:point] + parent2[point:]
        child2 = parent2[:point] + parent1[point:]
        return child1, child2

    def mutate(self, individual):
        """Τυχαία μετάλλαξη."""
        for i in range(len(individual)):
            if random.random() < self.mutation_rate:
                low, high = self.bounds[i]
                individual[i] = random.uniform(low, high)
        return individual

    def select(self, population, fitnesses):
        """Επιλογή Tournament."""
        selected = []
        for _ in range(self.pop_size):
            # Επιλογή 3 τυχαίων και κράτημα του καλύτερου
            candidates = random.sample(list(zip(population, fitnesses)), 3)
            winner = min(candidates, key=lambda x: x[1])[0]
            selected.append(winner)
        return selected

    def optimize(self, predictor_model):
        """Κύρια εκτέλεση του αλγορίθμου."""
        if not predictor_model or not predictor_model.model:
            return None, "Model not trained yet."

        print(f"--- Genetic Optimization ({self.profile_type}) ---")
        population = [self.create_individual() for _ in range(self.pop_size)]
        
        best_sol = None
        best_fit = float('inf')

        for gen in range(self.generations):
            fitnesses = [self.fitness(ind, predictor_model) for ind in population]
            
            # Εύρεση καλύτερου γενιάς
            min_f = min(fitnesses)
            if min_f < best_fit:
                best_fit = min_f
                best_sol = population[fitnesses.index(min_f)]
            
            # Επιλογή - Διασταύρωση - Μετάλλαξη
            parents = self.select(population, fitnesses)
            next_pop = []
            
            for i in range(0, self.pop_size, 2):
                p1, p2 = parents[i], parents[i+1]
                c1, c2 = self.crossover(p1, p2)
                next_pop.append(self.mutate(c1))
                next_pop.append(self.mutate(c2))
            
            population = next_pop

        # Μορφοποίηση αποτελέσματος
        ctl, atl, hrv, sleep, pace = best_sol
        result_str = (
            f"Optimal Parameters found:\n"
            f" CTL: {ctl:.1f}, ATL: {atl:.1f}\n"
            f" HRV: {hrv:.1f}, Sleep: {sleep:.1f}h\n"
            f" Recent Pace: {int(pace)}s/km\n"
            f" Predicted Race Time: {int(best_fit)}s"
        )
        return best_sol, result_str




# ============================================================================
# v50 ULTRA CLASSES - MISSING FEATURES
# ============================================================================

class TaperOptimizer:
    def __init__(self):
        self.taper_models = {
            "MODERATE": {"days": 14, "volume_reduction": 0.40},
            "AGGRESSIVE": {"days": 21, "volume_reduction": 0.50},
            "CONSERVATIVE": {"days": 10, "volume_reduction": 0.30}
        }
    
    def generate_taper_plan(self, race_date, current_volume, race_importance="MODERATE"):
        model = self.taper_models.get(race_importance, self.taper_models["MODERATE"])
        days = model["days"]
        reduction = model["volume_reduction"]
        
        plan = []
        for day in range(days):
            factor = 1.0 - (reduction * (day / days))
            volume = current_volume * factor
            plan.append({
                "day": day + 1,
                "volume": round(volume, 1),
                "intensity": "MAINTAIN" if day < days * 0.7 else "REDUCE"
            })
        
        return plan


class ASCIIDataVisualization:
    def __init__(self):
        self.width = 60
        self.height = 15
    
    def plot_tsb_chart(self, tsb_history):
        if not tsb_history:
            return "No data to plot"
        
        max_val = max(tsb_history)
        min_val = min(tsb_history)
        range_val = max_val - min_val if max_val != min_val else 1
        
        chart = []
        chart.append("TSB Chart (Last 30 days)")
        chart.append("=" * self.width)
        
        for i in range(self.height):
            threshold = max_val - (i * range_val / self.height)
            line = f"{threshold:+5.0f} |"
            
            for val in tsb_history[-30:]:
                if abs(val - threshold) < (range_val / self.height):
                    line += "*"
                else:
                    line += " "
            
            chart.append(line)
        
        chart.append("      +" + "-" * min(len(tsb_history), 30))
        return "\n".join(chart)


class SimulationMode:
    def __init__(self):
        self.scenarios = []
    
    def simulate_training_block(self, weeks, weekly_volume, intensity_distribution):
        # SAFETY: Use deepcopy for real data
        results = []
        cumulative_load = 0
        
        for week in range(weeks):
            week_load = weekly_volume * (1 + intensity_distribution.get("hard", 0.2))
            cumulative_load += week_load
            
            fatigue = cumulative_load * 0.05
            fitness = cumulative_load * 0.03
            form = fitness - fatigue
            
            results.append({
                "week": week + 1,
                "load": week_load,
                "fitness": round(fitness, 1),
                "fatigue": round(fatigue, 1),
                "form": round(form, 1)
            })
        
        return results


class WeeklyCommanderReport:
    def __init__(self):
        self.report_template = "WEEKLY COMMANDER REPORT"
    
    def generate_report(self, athlete_name, week_data):
        report = []
        report.append(f"=== {self.report_template} ===")
        report.append(f"Athlete: {athlete_name}")
        report.append(f"Week: {week_data.get('week_number', 'N/A')}")
        report.append("")
        report.append(f"Total Volume: {week_data.get('total_volume', 0)} km")
        report.append(f"Total Sessions: {week_data.get('sessions', 0)}")
        report.append(f"Avg HR: {week_data.get('avg_hr', 0)} bpm")
        report.append("")
        report.append("Status: " + week_data.get('status', 'NORMAL'))
        
        return "\n".join(report)


class WeatherAPI:
    def __init__(self, api_key=None, city="Athens"):
        self.api_key = api_key
        self.city = city
        self.cache = {}
    
    def get_current_weather(self):
        # Simulated weather data
        return {
            "temp": 20,
            "humidity": 60,
            "wind": 5,
            "conditions": "Clear"
        }
    
    def get_training_conditions(self):
        weather = self.get_current_weather()
        
        if weather["temp"] > 25:
            return "HOT - Reduce intensity, hydrate more"
        elif weather["temp"] < 10:
            return "COLD - Warm up longer"
        else:
            return "OPTIMAL - Normal training OK"


class InjuryEarlyWarningEngine:
    def __init__(self):
        self.risk_factors = {
            "sudden_load_increase": 0.3,
            "insufficient_recovery": 0.25,
            "high_soreness": 0.2,
            "low_hrv": 0.15,
            "poor_sleep": 0.1
        }
    
    def assess_injury_risk(self, athlete_data):
        risk_score = 0
        factors_triggered = []
        
        # Check load increase
        if athlete_data.get("load_increase", 0) > 0.15:
            risk_score += self.risk_factors["sudden_load_increase"]
            factors_triggered.append("Sudden load increase")
        
        # Check recovery
        if athlete_data.get("recovery_score", 100) < 60:
            risk_score += self.risk_factors["insufficient_recovery"]
            factors_triggered.append("Poor recovery")
        
        # Check soreness
        if athlete_data.get("soreness", 0) >= 7:
            risk_score += self.risk_factors["high_soreness"]
            factors_triggered.append("High soreness")
        
        risk_level = "LOW"
        if risk_score > 0.5:
            risk_level = "HIGH"
        elif risk_score > 0.3:
            risk_level = "MODERATE"
        
        return {
            "risk_level": risk_level,
            "risk_score": round(risk_score, 2),
            "factors": factors_triggered,
            "recommendation": self._get_recommendation(risk_level)
        }
    
    def _get_recommendation(self, risk_level):
        if risk_level == "HIGH":
            return "TAKE REST DAY. High injury risk detected."
        elif risk_level == "MODERATE":
            return "REDUCE INTENSITY. Monitor closely."
        else:
            return "NORMAL training OK. Stay vigilant."


class CognitiveLoadMonitor:
    def __init__(self):
        self.history = []
    
    def log_cognitive_state(self, date, mental_fatigue, work_stress, life_stress):
        total = (mental_fatigue + work_stress + life_stress) / 3
        entry = {
            "date": date,
            "mental": mental_fatigue,
            "work": work_stress,
            "life": life_stress,
            "total": round(total, 1)
        }
        self.history.append(entry)
        return entry
    
    def recovery_recommendations(self, cognitive_load):
        if cognitive_load >= 8:
            return ["Full rest day", "Meditation", "Early sleep"]
        elif cognitive_load >= 6:
            return ["Light activity only", "Reduce intensity"]
        else:
            return ["Normal training OK"]
    
    def assess_cognitive_impact(self, cognitive_load, planned_rpe):
        if cognitive_load >= 8:
            adjustment = +2
            rec = "HIGH stress. RPE +2 points."
        elif cognitive_load >= 6:
            adjustment = +1
            rec = "MODERATE stress. RPE +1 point."
        else:
            adjustment = 0
            rec = "LOW stress. Normal RPE."
        return min(10, planned_rpe + adjustment), rec


class PhaseAwareLogic:
    def __init__(self):
        self.phases = {
            "BASE": {"intensity": "low", "volume": "high"},
            "BUILD": {"intensity": "medium", "volume": "medium"},
            "PEAK": {"intensity": "high", "volume": "low"},
            "TAPER": {"intensity": "medium", "volume": "very_low"},
            "RACE": {"intensity": "max", "volume": "minimal"}
        }
    
    def get_phase_guidelines(self, current_phase):
        return self.phases.get(current_phase, self.phases["BASE"])
    
    def adjust_session_for_phase(self, session, phase):
        guidelines = self.get_phase_guidelines(phase)
        
        # Adjust session based on phase
        if phase == "TAPER":
            session["volume"] *= 0.6
            session["intensity"] = "MODERATE"
        elif phase == "PEAK":
            session["intensity"] = "HIGH"
            session["volume"] *= 0.8
        
        return session


class KnowledgeTraceability:
    def __init__(self):
        self.decisions = []
    
    def log_decision(self, decision_type, reasoning, outcome=None):
        entry = {
            "type": decision_type,
            "reasoning": reasoning,
            "outcome": outcome,
            "timestamp": "now"
        }
        self.decisions.append(entry)
        return entry
    
    def explain_taper_plan(self, plan, race_importance):
        explanation = "TAPER PLAN REASONING:\n"
        explanation += f"Race Importance: {race_importance}\n"
        explanation += f"Days in taper: {len(plan)}\n"
        explanation += "Strategy: Progressive volume reduction with intensity maintenance\n"
        return explanation
    
    def get_decision_history(self):
        return self.decisions


class TeamDashboard:
    def __init__(self):
        self.athletes = {}
    
    def add_athlete(self, athlete_id, athlete_data):
        self.athletes[athlete_id] = athlete_data
    
    def get_team_summary(self):
        if not self.athletes:
            return "No athletes in team"
        
        total = len(self.athletes)
        avg_load = sum(a.get("weekly_load", 0) for a in self.athletes.values()) / total
        
        summary = f"TEAM SUMMARY ({total} athletes)\n"
        summary += f"Average weekly load: {avg_load:.1f}\n"
        
        return summary


class TitanSystem:
    def __init__(self):
        # v48: Multi-athlete support
        self.athlete_db = AthleteDatabase()
        
        # Load existing athlete or create default
        self.profile = self.athlete_db.get_current()
        
        if not self.profile:
            # Create default athlete on first run
            self.profile = self.athlete_db.create_athlete(
                name="Zafiris",
                gender="M",
                age=43,
                height_cm=180,
                weight_kg=75
            )
            self.profile.set_hr_data(resting_hr=44, max_hr=191)
            self.profile.race_day = datetime(2026, 4, 26)
            self.athlete_db.save_athlete(self.profile)
        
        self.memory = AdaptiveMemory()
        self.today = datetime.now().strftime("%Y-%m-%d")
        self.phase = PhaseEngine.get_phase(datetime.now(), self.profile.race_day)
        self.current_dew = 12.0
        self.current_is_hot = False
        
        # v46 Engines
        self.nm_load = NeuromuscularLoadEngine()
        self.daily_monitor = DailyMonitoring()
        
        # v47 TIER 1: Injury Prevention & Load Management
        self.tsb_engine = TSBEngine()
        self.hrv_guided = HRVGuidedEngine()
        
        # v47 TIER 2: Performance Tracking
        self.efficiency_tracker = EfficiencyEngine()

        # v48 engines
        self.periodization = PeriodizationManager(self.profile)
        self.sleep_tracker = SleepArchitecture()
        self.cns_tracker = CNSReadinessTest()
        self.data_importer = DataImporter()
        # --- v48 ULTIMATE ENGINES ---
        self.gap_engine = GradeAdjustedPace()
        self.power_engine = RunningPower()
        self.bio_engine = BiomechanicsAnalysis()
        self.cycle_tracker = MenstrualCycleTracking()
        self.altitude_tracker = AltitudeTracker()
        self.schedule_mgr = ScheduleManager()
        # Ο ProgressAnalyzer δημιουργείται δυναμικά στο μενού του
        # Baselines for ACWR & TRIMP (will be set after initial logging)
        self.chronic_load_baseline = None
        self.trimp_baseline = None
	# --- v48 PROFESSIONAL ENGINES ---
        self.pacing_engine = RacePacingStrategy()
        self.recovery_engine = RecoveryScoreEngine()
        self.sync_engine = WearableSync()
	# --- v49 ELITE ENGINES ---
        self.gear_mgr = EquipmentManager()
        self.coach_brain = EliteCoachingStrategy()
        # --- v50 ULTRA FEATURES (ADDONS) ---
        self.ml_brain = MLPerformancePredictor()
        self.genetics = GeneticOptimization(profile_type="BALANCED") # Μπορείς να το αλλάξεις
        self.team_dash = TeamDashboard()
        self.taper_engine = TaperOptimizer()
        self.ascii_viz = ASCIIDataVisualization()
        self.sim_engine = SimulationMode()
        self.weekly_report = WeeklyCommanderReport()
        # Βάλε το API Key σου εδώ ή άστο κενό για DEMO mode
        self.weather_api = WeatherAPI(api_key=None, city="Thessaloniki") 
        self.injury_warning = InjuryEarlyWarningEngine()
        self.cognitive_monitor = CognitiveLoadMonitor()
        self.phase_logic = PhaseAwareLogic()
        self.traceability = KnowledgeTraceability()

    def run(self):
        while True:
            print("\n==== TITAN OS v48 UNIVERSAL ====")
            print(f"Athlete: {self.profile.name} | Age: {self.profile.age} | Phase: {self.phase}")
            print(f"Race: {self.profile.race_day.date()} | Goal: {self.profile.current_goal or 'Not set'}")
            print("-" * 60)
            print("0. [v48] ATHLETE MANAGEMENT (Switch/Create/View)")
            print("-" * 60)
            print("="*60)
            print(" CORE FUNCTIONS")
            print("="*60)
            print("1.  FULL READINESS & MEDICAL SCAN")
            print("2.  WEATHER & HEAT SHIELD")
            print("3.  TODAY'S MISSION (AUTO + OVERRIDES)")
            print("4.  NUTRITION PLAN (with Glycogen Awareness)")
            print("5.  PERFORMANCE / DRIFT / LACTATE / FATIGUE LOGGING")
            print("")
            print("="*60)
            print(" v46 ELITE COACHING SCIENCE")
            print("="*60)
            print("6.  NEUROMUSCULAR LOAD STATUS")
            print("7.  DAILY MONITORING (Morning Metrics)")
            print("8.  RACE WEEK ENTROPY CHECK")
            print("9.   FUEL TIMING MATRIX")
            print("")
            print("="*60)
            print(" v47 ADVANCED PERFORMANCE SCIENCE")
            print("="*60)
            print("10.  ACWR & TSB (Load Management)")
            print("11.  HRV-GUIDED TRAINING")
            print("12.  DURABILITY ASSESSMENT")
            print("13.  EFFICIENCY FACTOR")
            print("14.  ADVANCED METRICS (TRIMP/sRPE/Glycogen)")
            print("")
            print("="*60)
            print("  SYSTEM")
            print("="*60)
            print("15.  SETTINGS (Weight / 5K / CS / D)")
            print("16. POST-RACE EVOLUTION")
            print("")
            print("-" * 60)
            print("[v48 UNIVERSAL FEATURES]")
            print("-" * 60)
            print("17. ATHLETE PROFILE (Demographics/BMR/TDEE/EA)")
            print("18. GOALS & PERIODIZATION (Set/Complete/Track)")
            print("19. SLEEP ARCHITECTURE (Deep/REM Tracking)")
            print("20. CNS READINESS (Tap/Grip/Jump Tests)")
            print("21. DATA IMPORT (CSV Files)")
            print("-" * 60)
            print("-" * 60)
            print("[v48 ULTIMATE FEATURES]")
            print("23. GRADE ADJUSTED PACE (GAP)")
            print("24. RUNNING POWER")
            print("25. BIOMECHANICS SCAN")
            print("26. MENSTRUAL CYCLE (Ref)")
            print("27. ALTITUDE ADJUSTMENT")
            print("28. SMART SCHEDULE")
            print("29. PROGRESS ANALYZER")
            print("-" * 60)
            print("[v49 PROFESSIONAL FEATURES]")
            print("31. RACE PACING STRATEGY")
            print("32. RECOVERY SCORE (HRV+Sleep)")
            print("33. WEARABLE SYNC (Garmin/Stryd)")
            print("-" * 60)
            print("30. EXIT")
            print("-" * 60)
            print("[v50 ULTRA FEATURES]")
            print("40. ML PREDICTOR (Race Time)")
            print("41. TAPER OPTIMIZER")
            print("42. ASCII VISUALIZATION (Form Graph)")
            print("43. SIMULATION MODE (What-If)")
            print("44. WEATHER CHECK (Live API)")
            print("45. COGNITIVE LOAD MONITOR")
            print("46. WEEKLY COMMANDER REPORT")
            print("-" * 60)

            cmd = input("\nCOMMAND > ").strip()
            if cmd == "0":
                self.menu_athlete_management()
            elif cmd == "1":
                self.menu_readiness()
            elif cmd == "2":
                self.menu_weather()
            elif cmd == "3":
                self.menu_session()
            elif cmd == "4":
                self.menu_nutrition()
            elif cmd == "5":
                self.menu_logging()
            elif cmd == "6":
                self.menu_nm_load()
            elif cmd == "7":
                self.menu_daily_monitoring()
            elif cmd == "8":
                self.menu_race_week_entropy()
            elif cmd == "9":
                self.menu_fuel_timing()
            elif cmd == "10":
                self.menu_load_management()
            elif cmd == "11":
                self.menu_hrv_guided()
            elif cmd == "12":
                self.menu_durability()
            elif cmd == "13":
                self.menu_efficiency()
            elif cmd == "14":
                self.menu_advanced_metrics()
            elif cmd == "15":
                self.menu_settings()
            elif cmd == "16":
                self.menu_post_race()
            elif cmd == "17":
                self.menu_athlete_profile()
            elif cmd == "18":
                self.menu_periodization()
            elif cmd == "19":
                self.menu_sleep_architecture()
            elif cmd == "20":
                self.menu_cns_readiness()
            elif cmd == "21":
                self.menu_data_import()
            elif cmd == "22": 
                print("Old Exit removed. Use 30.")
            elif cmd == "23": 
                self.menu_gap()
            elif cmd == "24": 
                self.menu_power()
            elif cmd == "25": 
                self.menu_biomech()
            elif cmd == "26": 
                self.menu_cycle()
            elif cmd == "27": 
                self.menu_altitude()
            elif cmd == "28": 
                self.menu_schedule()
            elif cmd == "29": 
                self.menu_progress()
            elif cmd == "30": 
                print("Stay Hard.")
                break
            elif cmd == "31": self.menu_race_strategy()
            elif cmd == "32": self.menu_recovery_score()
            elif cmd == "33": self.menu_wearable_sync()
            elif cmd == "40": self.menu_ml_predict()
            elif cmd == "41": self.menu_taper()
            elif cmd == "42": self.menu_ascii_viz()
            elif cmd == "43": self.menu_simulation()
            elif cmd == "44": self.menu_weather_live()
            elif cmd == "45": self.menu_cognitive()
            elif cmd == "46": self.menu_weekly_report()
            input("\n(Press Enter...)")

    # ---------------- READINESS & MEDICAL ----------------
    def menu_readiness(self):
        print("\n>>> FULL READINESS & MEDICAL SCAN")
        try:
            hrv = float(input("HRV Today: "))
            rhr = float(input(f"RHR Today (Baseline {self.profile.resting_hr_baseline}): "))
            sleep = float(input("Sleep Score (0-100): "))
            soreness = float(input("Soreness (1-10): "))
            symptoms = input("Symptoms (None/Head/Chest/Fever): ").upper()
        except:
            hrv, rhr, sleep, soreness, symptoms = 60.0, 46.0, 85.0, 2.0, "NONE"

        score, status = ReadinessEngine.analyze_readiness(
            today_hrv=hrv,
            baseline_hrv=55,
            today_rhr=rhr,
            baseline_rhr=self.profile.resting_hr_baseline,
            sleep_score=sleep,
            soreness_1_10=soreness
        )
        crisis = MedicalEngine.crisis_protocol(symptoms)

        print(f"\n READINESS SCORE: {score}/100")
        print(f" STATUS: {status}")
        print(f" CRISIS CHECK: {crisis}")

    # ---------------- WEATHER ----------------
    def menu_weather(self):
        print("\n>>> WEATHER & HEAT SHIELD")
        try:
            t = float(input("Temp (C): "))
            h = float(input("Humidity (%): "))
        except:
            t, h = 15.0, 60.0
        dew, msg, is_hot, pen_msg = HeatEngine.heat_status(t, h)
        self.current_dew = dew
        self.current_is_hot = is_hot
        print(f"\nDew Point: {dew:.1f}C")
        print(f"Status: {msg}")
        print(f"Action: {pen_msg}")

    # ---------------- SESSION ----------------
    def menu_session(self):
        print("\n>>> TODAY'S MISSION (ELITE COACHING MODE)")
        
        # 1. Βασικά Δεδομένα
        try:
            planned = Scheduler.get_planned_session(datetime.now(), self.profile.race_day)
            print(f"📅 SCHEDULED: {planned}")
            
            # Ερώτηση για override
            user_ov = input("Manual override? (Enter for Auto): ").upper()
            target_session = user_ov if user_ov else planned
            
            # 2. Context Awareness (Shoes & Surface)
            print("\n👟 EQUIPMENT CHECK:")
            for k, v in self.gear_mgr.shoes.items():
                print(f"  {k}. {v['name']} ({v['type']} - {v['km']}km)")
            shoe_choice = input("Select Shoe (1-3): ")
            surface = input("Surface (ROAD/TRACK/TRAIL/CONCRETE): ").upper()
            
            # Έλεγχος Εξοπλισμού
            gear_ok, gear_msg = self.gear_mgr.check_gear(target_session, shoe_choice, surface)
            if not gear_ok:
                print(f"\n🚫 GEAR BLOCK: {gear_msg}")
                print("SESSION ABORTED. Change shoes or session.")
                return 

            # 3. Risk Calculation (Simulated inputs for now - normally from logs)
            # Εδώ κανονικά θα τραβούσε από self.daily_monitor κλπ.
            # Για το demo ζητάμε τα κρίσιμα αν δεν υπάρχουν
            try:
                acwr_in = 1.1 # Placeholder ή τραβήξτε από self.acwr_engine
                hrv_stat = "NORMAL" # Placeholder
                sleep = float(input("Last Night Sleep Score (0-100): "))
                soreness = float(input("Leg Soreness (1-10): "))
            except:
                sleep, soreness = 80, 2
                acwr_in, hrv_stat = 1.1, "NORMAL"

            risk_score, risk_factors = self.coach_brain.calculate_risk_profile(
                acwr=acwr_in, tsb=-10, hrv_status=hrv_stat, 
                sleep_score=sleep, soreness=soreness, shoe_risk_msg=gear_msg
            )

            # 4. Coaching Decision (The BLOCK Logic)
            decision = self.coach_brain.get_session_permission(target_session, risk_score, risk_factors)

            print("\n" + "="*50)
            print(f"🛡️  TITAN RISK ANALYSIS: {risk_score}%")
            print("="*50)
            
            if decision['action'] == "BLOCKED":
                print(f"❌ STATUS: {decision['action']}")
                print(f"🛑 REASON: {decision['reason']}")
                print(f"🔄 FORCED SWITCH TO: {decision['override_session']}")
                final_session = decision['override_session']
            
            elif decision['action'] == "CAUTION":
                print(f"⚠️ STATUS: {decision['action']}")
                print(f"ℹ️ NOTE: {decision['reason']}")
                confirm = input("Proceed anyway? (y/n): ").lower()
                final_session = target_session if confirm == 'y' else "EASY"
            
            else:
                print(f" STATUS: {decision['action']}")
                final_session = target_session

            # 5. Build Final Session
            print(f"\n🚀 GENERATING: {final_session}")
            if "RISK" in gear_msg: 
                print(f"⚠️ GEAR WARNING: {gear_msg}")
            
            is_hot = self.current_is_hot
            builder = SessionBuilder(self.profile, self.memory)
            breakdown = builder.build(final_session, is_high_heat=is_hot)

            print("-" * 50)
            print(f" MISSION: {breakdown['TITLE']}")
            print(f" WARMUP: {breakdown['WARMUP']}")
            print(" MAIN SET:")
            for line in breakdown["MAIN"]:
                print(f"   {line}")
            print(f" COOLDOWN: {breakdown['COOLDOWN']}")

        except Exception as e:
            print(f"Error in session builder: {e}")
    # ---------------- NUTRITION ----------------
    def menu_nutrition(self):
        print("\n>>> NUTRITION PLAN (with Glycogen Awareness)")
        try:
            w = float(input("Current Weight (kg): "))
            gut = int(input("Gut Health (0-10): "))
            low_carb_day = input("Is today LOW CARB day? (y/n): ").lower() == "y"
            back_to_back = input("Back-to-back quality days? (y/n): ").lower() == "y"
        except:
            w, gut, low_carb_day, back_to_back = 75.0, 8, False, False
        dew = self.current_dew
        today_obj = datetime.now()
        sess = Scheduler.get_planned_session(today_obj, self.profile.race_day)
        plan = NutritionEngine.calculate_plan(
            w, sess, gut, dew, self.phase,
            low_carb_day=low_carb_day,
            back_to_back_quality=back_to_back
        )
        print(f"\n=== {plan['Diet_Type']} ===")
        print(f"Phase: {plan['Phase']}")
        print(f"Protein Target: {plan['Protein_Target']}")
        print(f"Carb Target: {plan['Carb_Target']}")
        print(f"Foods: {plan['Foods']}")
        if "Forbidden" in plan:
            print(f"Forbidden: {plan['Forbidden']}")
        print(f"Hydration: {plan['Hydration_Strategy']}")
        print(f"Hammer Allowed: {plan['Hammer_Allowed']}")
        print("Glycogen Flags:")
        for f in plan["Glycogen_Flags"]:
            print(f"  - {f}")

    # ---------------- LOGGING ----------------
    def menu_logging(self):
        print("\n>>> PERFORMANCE / DRIFT / LACTATE / FATIGUE / DECISION RULES")
        try:
            session_type = input("Session type (TEMPO/INTERVALS/LONG/EASY): ").upper()
            dist = float(input("Distance (km): "))
            time_str = input("Time (MM:SS or HH:MM:SS): ")
            avg_hr = float(input("Avg HR: "))
            hr_first = float(input("HR first half: "))
            hr_second = float(input("HR second half: "))
            rpe = float(input("RPE (1-10): "))
            soreness = float(input("Soreness (1-10): "))
            easy_baseline_str = input("Baseline EASY pace (MM:SS) [for mech load]: ")
        except:
            session_type = "TEMPO"
            dist, time_str, avg_hr, hr_first, hr_second, rpe, soreness = 10.0, "45:00", 155, 150, 160, 7, 3
            easy_baseline_str = "5:30"

        total_sec = self.profile.str_to_sec(time_str)
        pace_sec = total_sec / dist if dist > 0 else 0
        drift = DriftEngine.compute_drift(hr_first, hr_second)
        drift_msg = DriftEngine.drift_rule(drift)

        hr_pct_max = avg_hr / self.profile.max_hr * 100.0 if self.profile.max_hr > 0 else 0.0
        lt1_msg = LactateLogic.estimate_lt1(hr_pct_max, drift)
        hr_stable = abs(hr_second - hr_first) <= 3
        lt2_msg = LactateLogic.estimate_lt2(hr_stable, rpe)
        tempo_decision = LactateLogic.tempo_volume_decision("TRUE" in lt2_msg)

        hr_suppression = avg_hr < (self.profile.threshold_hr - 10) and rpe >= 8
        rpe_mismatch = rpe >= 8 and avg_hr < self.profile.threshold_hr
        pace_hr_div = drift > 5.0
        fatigue_level, fatigue_types = FatigueEngine.classify_fatigue(
            hr_suppression, rpe_mismatch, pace_hr_div, soreness
        )

        easy_today_sec = pace_sec
        easy_baseline_sec = self.profile.str_to_sec(easy_baseline_str)
        mech_msg = self.memory.mechanical_load_risk(easy_today_sec, easy_baseline_sec)
        
        # === DECISION RULES APPLICATION ===
        print("\n" + "="*60)
        print("DECISION RULES ANALYSIS (Seiler / Mujika)")
        print("="*60)
        
        # 1. HR Drift  Pace Adjustment
        should_adjust, new_pace, pace_msg = DecisionRulesEngine.check_hr_drift_pace_adjustment(
            drift, session_type, pace_sec
        )
        print(f"\n1  {pace_msg}")
        if should_adjust:
            print(f"   Suggested new pace: {self.profile.sec_to_str(new_pace)}/km")
        
        # 2. Neuromuscular Fatigue Detection
        is_nm_fatigued, nm_msg = DecisionRulesEngine.check_neuromuscular_fatigue(
            rpe, avg_hr, self.profile.threshold_hr
        )
        print(f"\n2  {nm_msg}")
        if is_nm_fatigued:
            print("    Schedule easy day or rest")

        print("\n" + "="*60)
        print("STANDARD METRICS")
        print("="*60)
        print(f"\nPace: {self.profile.sec_to_str(pace_sec)}/km")
        print(f"Drift: {drift:.1f}% -> {drift_msg}")
        print(f"HR% max: {hr_pct_max:.1f}%")
        print(f"LT1 Logic: {lt1_msg}")
        print(f"LT2 Logic: {lt2_msg}")
        print(f"Tempo Volume Decision: {tempo_decision}")
        print(f"Fatigue Level: {fatigue_level}")
        print(f"Fatigue Types: {', '.join(fatigue_types)}")
        print(f"Mechanical Load: {mech_msg}")

        self.memory.log_session(
            date=datetime.now(),
            session_type="UNKNOWN",
            load=dist * rpe,
            rpe=rpe,
            drift=drift,
            success_flag=True,
            soreness=soreness
        )

# ---------------- SETTINGS ----------------
    def menu_settings(self):
        print("\n>>> SETTINGS")
        try:
            nw = input("New Weight (kg) [Enter to skip]: ").strip()
            if nw:
                w = float(nw)
                self.profile.weight_kg = w  # <--- ΑΥΤΟ ΕΛΕΙΠΕ
                self.profile.weight_floor = w - 0.5
                self.profile.weight_ceiling = w + 1.2
                self.athlete_db.save_athlete(self.profile) # Σώσιμο αλλαγών
                
            nt = input(f"New 5K Time (MM:SS) [Current {self.profile.base_5k_time_str}]: ").strip()
            if nt:
                self.profile.base_5k_time_str = nt
                self.profile.base_5k_sec = self.profile.str_to_sec(nt) / 5.0
                
            print("You can also update CS/D from recent performances.")
            upd = input("Update CS/D? (y/n): ").lower()
            if upd == "y":
                perfs = []
                while True:
                    line = input("Enter perf (dist_m,time_s) or Enter to stop: ").strip()
                    if not line: break
                    try:
                        d_s = line.split(',')
                        perfs.append((float(d_s[0]), float(d_s[1])))
                    except: print("Invalid format.")
                cs, dp = CriticalSpeedEngine.estimate_cs_and_dprime(perfs)
                if cs and dp:
                    self.profile.critical_speed_m_per_s = cs
                    self.profile.d_prime_m = dp
                    print(f"Updated CS: {cs:.3f} m/s, D: {dp:.1f} m")
                    self.athlete_db.save_athlete(self.profile)
                else: print("Could not estimate CS/D.")
            print(" Settings updated.")
        except: print("Error in settings.")

    # ---------------- POST-RACE EVOLUTION ----------------
    def menu_post_race(self):
        print("\n>>> POST-RACE EVOLUTION ENGINE")
        today_obj = datetime.now()
        if today_obj <= self.profile.race_day:
            print("Race day not passed yet. Evolution will unlock after race.")
            return
        path = PhaseEngine.post_race_menu()
        print(f"Selected Path: {path}")
        if path == "OFF":
            self.phase = "OFF"
        elif path == "MAINT":
            self.phase = "MAINT"
        elif path in ["1K", "5K", "10K", "21K", "42K"]:
            self.phase = f"PROJECT_{path}"
        else:
            self.phase = "MAINT"
        print(f"Phase updated to: {self.phase}")

    # ---------------- NEUROMUSCULAR LOAD STATUS ----------------
    def menu_nm_load(self):
        print("\n>>> NEUROMUSCULAR LOAD MANAGEMENT")
        print("Log today's session to track CNS load.")
        try:
            date_str = input("Date (YYYY-MM-DD) [Enter for today]: ").strip()
            if not date_str:
                date_obj = datetime.now()
            else:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            
            session_type = input("Session type (TEMPO/INTERVALS/LONG/EASY): ").upper()
            has_strides = input("Did session include strides? (y/n): ").lower() == 'y'
            has_intervals = input("Did session include short intervals (<1k)? (y/n): ").lower() == 'y'
            has_hammer = input("Did session include Hammer segment? (y/n): ").lower() == 'y'
        except:
            date_obj = datetime.now()
            session_type = "EASY"
            has_strides, has_intervals, has_hammer = False, False, False
        
        nli_points, details = self.nm_load.add_session(
            date_obj, session_type, has_strides, has_intervals, has_hammer
        )
        
        print(f"\n Session NLI: {nli_points} points")
        for detail in details:
            print(f"   {detail}")
        
        status = self.nm_load.get_status(datetime.now())
        print(f"\n{status['message']}")
        
        if status['needs_deload']:
            print("  RECOMMENDATION: Schedule easy week or add extra recovery day")

    # ---------------- DAILY MONITORING ----------------
    def menu_daily_monitoring(self):
        print("\n>>> DAILY MONITORING - Morning Metrics")
        choice = input("1. Add today's entry  2. View history: ").strip()
        
        if choice == "1":
            try:
                date_obj = datetime.now()
                weight = float(input(f"Morning weight (kg) [Baseline: {self.profile.weight_floor}]: "))
                rhr = float(input(f"Resting HR [Baseline: {self.profile.resting_hr_baseline}]: "))
                stiffness = int(input("Stiffness (0-5, 0=none, 5=severe): "))
                sleep_quality = int(input("Sleep quality (0-5, 0=terrible, 5=perfect): "))
            except:
                print("Invalid input. Using defaults.")
                return
            
            self.daily_monitor.add_entry(date_obj, weight, rhr, stiffness, sleep_quality)
            
            weight_change = self.daily_monitor.get_weight_change_pct(self.profile.weight_floor)
            status = self.daily_monitor.get_status(
                self.profile.weight_floor, 
                self.profile.resting_hr_baseline
            )
            
            print(f"\n STATUS: {status}")
            print(f"Weight change from baseline: {weight_change:.1f}%")
            
            # Apply Decision Rules
            hrv_status = "LOW" if rhr > self.profile.resting_hr_baseline + 5 else "NORMAL"
            should_abort, msg = DecisionRulesEngine.check_morning_abort_hammer(
                weight_change, hrv_status
            )
            print(f"\n DECISION RULE: {msg}")
        
        elif choice == "2":
            self.daily_monitor.display_metrics()

    # ---------------- RACE WEEK ENTROPY ----------------
    def menu_race_week_entropy(self):
        print("\n>>> RACE WEEK ENTROPY CHECK")
        print("Goal: Peak PREDICTABILITY, not peak fitness")
        
        days_to_race = (self.profile.race_day - datetime.now()).days
        print(f"Days to race: {days_to_race}")
        
        if days_to_race > 7:
            print("Not in race week yet. Continue normal training.")
            return
        
        # Get race week protocol
        protocol = RaceWeekEngine.race_week_protocol(days_to_race)
        print(f"\n TODAY'S PROTOCOL: {protocol}")
        
        # Calculate entropy
        try:
            training_ok = input("Did you follow the plan this week? (y/n): ").lower() == 'y'
            gut_health = int(input("Gut health (0-10): "))
            sleep_avg = int(input("Average sleep quality this week (0-5): "))
            weight_stable = input("Has weight been stable? (y/n): ").lower() == 'y'
        except:
            training_ok, gut_health, sleep_avg, weight_stable = True, 8, 4, True
        
        entropy, status = RaceWeekEngine.calculate_entropy_score(
            days_to_race, training_ok, gut_health, sleep_avg, weight_stable
        )
        
        print(f"\n ENTROPY SCORE: {entropy}/100")
        print(f" {status}")
        
        if entropy > 30:
            print("\n  ACTIONS TO REDUCE ENTROPY:")
            if not training_ok:
                print("   Stick to planned sessions (no experiments)")
            if gut_health < 7:
                print("   Switch to white diet immediately")
            if sleep_avg < 3:
                print("   Prioritize 8+ hours sleep")
            if not weight_stable:
                print("   Lock in daily nutrition routine")

    # ---------------- FUEL TIMING MATRIX ----------------
    def menu_fuel_timing(self):
        print("\n>>> FUEL TIMING MATRIX")
        print("Based on Jeukendrup / Burke protocols")
        
        try:
            today_obj = datetime.now()
            session_type = Scheduler.get_planned_session(today_obj, self.profile.race_day)
            override = input(f"Planned: {session_type}. Override? (TEMPO/INTERVALS/LONG/EASY) or Enter: ").upper()
            if override:
                session_type = override
            
            has_hammer = False
            if session_type in ["LONG_RUN", "PROGRESSIVE"]:
                has_hammer = input("Will this session include Hammer segment? (y/n): ").lower() == 'y'
        except:
            session_type = "EASY"
            has_hammer = False
        
        FuelTimingEngine.display_fuel_plan(session_type, has_hammer)




    # ============================================================================
    # v47 ADVANCED MENU METHODS
    # ============================================================================
    
    # ---------------- ACWR & TSB STATUS ----------------
    def menu_load_management(self):
        print("\n>>> LOAD MANAGEMENT: ACWR & TSB")
        print("="*60)
        
        # Get load data
        try:
            loads_7d = []
            print("Enter daily load for last 7 days (km  RPE or TRIMP):")
            for i in range(7):
                load = float(input(f"Day {i+1}: "))
                loads_7d.append(load)
            
            loads_28d = []
            print("\nEnter average daily load for last 28 days:")
            avg_28d = float(input("Average daily load (28d): "))
        except:
            print("Using demo data...")
            loads_7d = [45, 50, 38, 55, 42, 60, 48]
            avg_28d = 42
        
        # ACWR Calculation
        acute_load = sum(loads_7d)
        acwr, status, recommendation = ACWREngine.calculate_acwr(acute_load, avg_28d)
        
        print("\n ACUTE:CHRONIC WORKLOAD RATIO (Gabbett 2016)")
        print("="*60)
        print(f"Acute Load (7d): {acute_load:.0f}")
        print(f"Chronic Load (28d avg): {avg_28d:.0f}")
        print(f"ACWR: {acwr}")
        print(f"Status: {status}")
        print(f"Recommendation: {recommendation}")
        
        # TSB Calculation
        print("\n TRAINING STRESS BALANCE (Banister/Coggan)")
        print("="*60)
        
        # Add loads to TSB engine
        today = datetime.now()
        for i, load in enumerate(loads_7d):
            date = today - timedelta(days=7-i)
            self.tsb_engine.add_daily_load(date, load)
        
        ctl = self.tsb_engine.calculate_ctl()
        atl = self.tsb_engine.calculate_atl()
        tsb, tsb_status = self.tsb_engine.calculate_tsb()
        
        if tsb is not None:
            print(f"CTL (Fitness): {ctl}")
            print(f"ATL (Fatigue): {atl}")
            print(f"TSB (Form): {tsb}")
            print(f"Status: {tsb_status}")
        else:
            print("Need more training days for TSB calculation")
    
    # ---------------- HRV-GUIDED DECISION ----------------
    def menu_hrv_guided(self):
        print("\n>>> HRV-GUIDED TRAINING (Kiviniemi 2007)")
        print("="*60)
        
        try:
            today_hrv = float(input("Morning HRV (rMSSD in ms): "))
            
            # Add to log
            self.hrv_guided.add_hrv_measurement(datetime.now(), today_hrv)
            
            # Get planned session
            planned = input("Planned session (TEMPO/INTERVALS/LONG/EASY): ").upper()
            
        except:
            print("Using demo data...")
            today_hrv = 55
            planned = "TEMPO"
            # Add some historical data
            for i in range(7):
                self.hrv_guided.add_hrv_measurement(
                    datetime.now() - timedelta(days=7-i),
                    58 + (i % 3) - 1
                )
        
        # Get recommendation
        recommended, explanation, confidence = self.hrv_guided.get_training_recommendation(
            today_hrv, planned
        )
        
        print("\n HRV-GUIDED DECISION:")
        print("="*60)
        print(f"Planned Session: {planned}")
        print(f"Recommended Session: {recommended}")
        print(f"Explanation: {explanation}")
        print(f"Confidence: {confidence}")
        
        # Trend analysis
        trend = self.hrv_guided.get_trend_analysis()
        print(f"\nTrend (7d): {trend}")
        
        if recommended != planned and recommended in ["REST", "EASY"]:
            print("\n  RECOMMENDATION: Follow HRV guidance to avoid overtraining")
            print("Research shows 8.3% vs 5.6% VO2max improvement with HRV-guided training")
    
    # ---------------- DURABILITY ASSESSMENT ----------------  
    def menu_durability(self):
        print("\n>>> DURABILITY ASSESSMENT (Maunder et al. 2021)")
        print("="*60)
        
        choice = input("1. Pace Decay Analysis  2. Durability Index: ").strip()
        
        if choice == "1":
            try:
                n_km = int(input("How many km in your run? "))
                splits = []
                print("Enter split times (MM:SS or seconds):")
                for i in range(n_km):
                    split_str = input(f"KM {i+1}: ")
                    if ':' in split_str:
                        parts = split_str.split(':')
                        seconds = int(parts[0]) * 60 + int(parts[1])
                    else:
                        seconds = float(split_str)
                    splits.append(seconds)
                target = float(input("Target pace (sec/km): "))
            except:
                print("Using demo data...")
                splits = [270, 272, 275, 278, 280, 282, 285, 288, 290, 292, 
                         295, 298, 300, 302, 305]
                target = 280
                n_km = len(splits)
            
            decay, status, recommendation = DurabilityEngine.assess_pace_durability(
                splits, target
            )
            
            print("\n PACE DURABILITY:")
            print("="*60)
            print(f"Distance: {n_km} km")
            print(f"Pace Decay: {decay}%")
            print(f"Status: {status}")
            print(f"Recommendation: {recommendation}")
            
        elif choice == "2":
            try:
                print("\nFresh performance (e.g., fresh 5K time):")
                fresh = self.profile.str_to_sec(input("Time (MM:SS): "))
                print("\nFatigued performance (e.g., 5K after 25K):")
                fatigued = self.profile.str_to_sec(input("Time (MM:SS): "))
            except:
                fresh = 1140  # 19:00
                fatigued = 1200  # 20:00
            
            di, status, tier = DurabilityEngine.calculate_durability_index(
                fresh, fatigued
            )
            
            print("\n DURABILITY INDEX:")
            print("="*60)
            print(f"DI Score: {di}%")
            print(f"Status: {status}")
            print(f"Tier: {tier}")
            
            # Training protocol
            protocols = DurabilityEngine.durability_training_protocol(di)
            print("\n TRAINING RECOMMENDATIONS:")
            for p in protocols:
                print(f"  {p}")
    
    # ---------------- EFFICIENCY FACTOR TRACKING ----------------
    def menu_efficiency(self):
        print("\n>>> EFFICIENCY FACTOR (Friel 2009)")
        print("="*60)
        
        choice = input("1. Calculate EF  2. Decoupling Analysis  3. View Trend: ").strip()
        
        if choice == "1":
            try:
                pace = self.profile.str_to_sec(input("Average pace (MM:SS/km): "))
                hr = float(input("Average HR: "))
            except:
                pace = 300
                hr = 155
            
            ef = EfficiencyEngine.calculate_efficiency_factor(pace, hr)
            
            print(f"\n EFFICIENCY FACTOR: {ef:.5f}")
            print("Higher EF = more aerobically efficient")
            
            # Log it
            self.efficiency_tracker.add_ef_measurement(datetime.now(), ef)
            
        elif choice == "2":
            try:
                print("First half:")
                pace1 = self.profile.str_to_sec(input("  Pace (MM:SS/km): "))
                hr1 = float(input("  Avg HR: "))
                print("Second half:")
                pace2 = self.profile.str_to_sec(input("  Pace (MM:SS/km): "))
                hr2 = float(input("  Avg HR: "))
            except:
                pace1, hr1 = 300, 150
                pace2, hr2 = 310, 160
            
            decoupling, status = EfficiencyEngine.calculate_decoupling(
                pace1, hr1, pace2, hr2
            )
            
            print("\n DECOUPLING ANALYSIS:")
            print("="*60)
            print(f"Decoupling: {decoupling}%")
            print(f"Status: {status}")
            
        elif choice == "3":
            trend = self.efficiency_tracker.analyze_ef_trend()
            print(f"\n EF TREND: {trend}")
    
    # ---------------- ADVANCED METRICS ----------------
    def menu_advanced_metrics(self):
        print("\n>>> ADVANCED METRICS (TRIMP / sRPE / Glycogen)")
        print("="*60)
        print("1. Calculate TRIMP (Training Impulse)")
        print("2. Session RPE (Foster 2001)")
        print("3. Glycogen Depletion Estimate")
        print("4. Back to Main Menu")
        
        choice = input("\nSelect: ").strip()
        
        if choice == "1":
            try:
                duration = float(input("Duration (minutes): "))
                avg_hr = float(input("Average HR: "))
                method = input("Method (E)dwards or (B)anister: ").upper()
            except:
                duration, avg_hr, method = 60, 155, "E"
            
            if method == "E" or method == "EDWARDS":
                trimp, zone = TRIMPEngine.calculate_edwards_trimp(
                    duration, avg_hr, self.profile.max_hr
                )
                print(f"\nEdwards TRIMP: {trimp}")
                print(f"HR Zone: {zone}")
            else:
                trimp = TRIMPEngine.calculate_banister_trimp(
                    duration, avg_hr, self.profile.resting_hr_baseline, 
                    self.profile.max_hr, 'male'
                )
                print(f"\nBanister TRIMP: {trimp}")
                
        elif choice == "2":
            try:
                duration = float(input("Duration (minutes): "))
                rpe = float(input("Session RPE (1-10): "))
            except:
                duration, rpe = 60, 7
            
            srpe = SessionRPEEngine.calculate_srpe(duration, rpe)
            interpretation = SessionRPEEngine.interpret_srpe(srpe)
            
            print(f"\nsRPE Score: {srpe}")
            print(f"Interpretation: {interpretation}")
            
        elif choice == "3":
            try:
                duration = float(input("Duration (minutes): "))
                intensity = float(input("Intensity (% VO2max, e.g., 75): "))
                weight = float(input("Body weight (kg): "))
            except:
                duration, intensity, weight = 90, 75, 75
            
            result = GlycogenModel.estimate_glycogen_depletion(duration, intensity)
            carb_rec = GlycogenModel.daily_carb_recommendation(weight, "HIGH")
            
            print("\n GLYCOGEN DEPLETION:")
            print("="*60)
            print(f"Glycogen Depleted: {result['glycogen_depleted_g']}g")
            print(f"Intensity: {result['intensity_classification']}")
            print(f"Depletion Rate: {result['depletion_rate']} g/min")
            print(f"\n{result['refuel_recommendation']}")
            print(f"\nDaily carbs needed: {carb_rec['total_carbs_range']}")

# ---------------- v48 ATHLETE MANAGEMENT ----------------
    def menu_athlete_management(self):
        """Manage athletes"""
        print("\n[v48 ATHLETE MANAGEMENT]")
        athletes = self.athlete_db.list_all()
        
        if athletes:
            print("\nAthletes:")
            for i, ath in enumerate(athletes, 1):
                current = " <- CURRENT" if ath["id"] == self.athlete_db.current_athlete_id else ""
                print(f"  {i}. {ath['name']} ({ath['gender']}, Age {ath['age']}){current}")
        
        print("\n1. Switch athlete")
        print("2. Create new athlete")
        print("3. View current athlete details")
        
        choice = input("Select: ").strip()
        
        if choice == "1" and athletes:
            try:
                num = int(input("Athlete number: ")) - 1
                if 0 <= num < len(athletes):
                    self.profile = self.athlete_db.switch_athlete(athletes[num]["id"])
                    self.periodization = PeriodizationManager(self.profile)
                    print(f"[OK] Switched to {self.profile.name}")
            except: print("Invalid selection.")
        
        elif choice == "2":
            try:
                name = input("Athlete name: ")
                gender = input("Gender (M/F): ").upper()
                age = int(input("Age: "))
                height = float(input("Height (cm): "))
                weight = float(input("Weight (kg): "))
                
                self.profile = self.athlete_db.create_athlete(name, gender, age, height, weight)
                
                # Auto HR setup
                rhr = int(input("Resting HR: "))
                self.profile.set_hr_data(rhr, None) # Auto max HR
                self.athlete_db.save_athlete(self.profile)
                
                print(f"\n[OK] Created: {self.profile.name}")
                self.periodization = PeriodizationManager(self.profile)
            except: print("Error creating athlete.")
        
        elif choice == "3":
            print(f"\n[{self.profile.name}]")
            print(f"Gender: {self.profile.gender}")
            print(f"Age: {self.profile.age}")
            print(f"Height: {self.profile.height_cm} cm")
            print(f"Weight: {self.profile.weight_kg} kg")
            # Υπολογισμός BMR/TDEE με τις νέες σταθερές (2020/2800)
            bmr = self.profile.calculate_bmr()
            tdee = self.profile.calculate_tdee()
            print(f"\nBMR: {bmr} kcal/day (Fixed)")
            print(f"TDEE: {tdee} kcal/day (Max)")

    # ========================================================================
    # v48 UNIVERSAL MENU METHODS
    # ========================================================================
    
    def menu_athlete_profile(self):
        """Profile and nutrition"""
        print(f"\n[PROFILE: {self.profile.name}]")
        print("1. View profile")
        print("2. Update weight")
        print("3. Update HR data")
        print("4. Energy Availability")
        
        choice = input("Select: ").strip()
        
        if choice == "1":
            print(f"\nGender: {self.profile.gender}")
            print(f"Age: {self.profile.age}")
            print(f"Height: {self.profile.height_cm} cm")
            print(f"Weight: {self.profile.weight_kg} kg")
            print(f"Resting HR: {self.profile.resting_hr}")
            print(f"Max HR: {self.profile.max_hr}")
            print(f"Threshold HR: {self.profile.threshold_hr}")
            
            bmr = self.profile.calculate_bmr()
            tdee = self.profile.calculate_tdee()
            if bmr:
                print(f"\nBMR: {bmr} kcal/day")
                print(f"TDEE: {tdee} kcal/day")

        elif choice == "2":
            try:
                print(f"Current Weight: {self.profile.weight_kg} kg")
                nw = float(input("New Weight (kg): "))
                self.profile.weight_kg = nw
                # Ενημέρωση και των ορίων ασφαλείας
                self.profile.weight_floor = nw - 0.5
                self.profile.weight_ceiling = nw + 1.2
                self.profile.weight_panic = nw - 1.5
                self.athlete_db.save_athlete(self.profile)
                print("[OK] Weight Updated.")
            except:
                print("Invalid input.")

        elif choice == "3":
            try:
                print(f"Current Resting HR: {self.profile.resting_hr}")
                print(f"Current Max HR: {self.profile.max_hr}")
                
                nrhr = input("New Resting HR (Enter to keep current): ").strip()
                if nrhr:
                    self.profile.resting_hr = int(nrhr)
                
                nmhr = input("New Max HR (Enter to keep current): ").strip()
                if nmhr:
                    self.profile.max_hr = int(nmhr)
                    # Αυτόματη ενημέρωση Threshold αν αλλάξει το Max
                    self.profile.threshold_hr = int(self.profile.max_hr * 0.88)
                
                self.athlete_db.save_athlete(self.profile)
                print("[OK] HR Data Updated.")
            except:
                print("Invalid input.")
        
        elif choice == "4":
            ei = float(input("Energy intake (kcal): "))
            duration = float(input("Training duration (min): "))
            avg_hr = float(input("Avg HR: "))
            
            eee = NutritionScience.calculate_exercise_ee(
                duration, avg_hr, self.profile.resting_hr,
                self.profile.weight_kg, self.profile.age, self.profile.gender
            )
            
            ffm = NutritionScience.calculate_ffm(self.profile.weight_kg)
            ea, status, rec = NutritionScience.calculate_energy_availability(ei, eee, ffm)
            
            print(f"\nEnergy Intake: {ei} kcal")
            print(f"Exercise EE: {eee} kcal")
            print(f"FFM: {ffm} kg")
            print(f"\nEA: {ea} kcal/kg FFM/day")
            print(f"Status: {status}")
            print(f"Action: {rec}")
    
    def menu_periodization(self):
        """Goals and phases"""
        print("\n[GOALS & PERIODIZATION]")
        
        if self.periodization.current_goal:
            goal = self.periodization.current_goal
            print("\nCurrent Goal:")
            print(f"  Distance: {goal['distance_km']}K")
            print(f"  Target: {goal['target_time']}")
            print(f"  Race: {goal['race_date'].strftime('%Y-%m-%d')}")
            
            phase = self.periodization.calculate_phase(goal['race_date'])
            print(f"\nPhase: {phase}")
        
        print("\n1. Set goal")
        print("2. Complete goal")
        
        choice = input("Select: ").strip()
        
        if choice == "1":
            dist = float(input("Distance (5/10/21/42): "))
            target = input("Target (MM:SS): ")
            date = input("Date (YYYY-MM-DD): ")
            
            goal = self.periodization.add_goal(dist, target, date)
            self.athlete_db.save_athlete(self.profile)
            print(f"[OK] Goal: {dist}K in {target}")
        
        elif choice == "2" and self.periodization.current_goal:
            actual = input("Actual time: ")
            result = self.periodization.complete_goal(
                self.periodization.current_goal['goal_id'], actual
            )
            
            print("\n[OK] COMPLETED!")
            print("\nNext goals:")
            for sug in result['suggestions']:
                print(f"  - {sug['description']}")
    
    def menu_sleep_architecture(self):
        """Sleep tracking"""
        print("\n[SLEEP ARCHITECTURE]")
        print("1. Log sleep")
        print("2. View summary")
        
        choice = input("Select: ").strip()
        
        if choice == "1":
            total_h = float(input("Total (hours): "))
            deep = float(input("Deep (min): "))
            rem = float(input("REM (min): "))
            quality = int(input("Quality (1-10): "))
            
            session = self.sleep_tracker.add_sleep_session(
                datetime.now(), total_h * 60, deep, rem, quality
            )
            
            score, status, issues = self.sleep_tracker.analyze_quality(session)
            
            print(f"\nTotal: {total_h}h")
            print(f"Deep: {deep}min ({session['deep_pct']}%)")
            print(f"REM: {rem}min ({session['rem_pct']}%)")
            print(f"\nScore: {score}/100")
            print(f"Status: {status}")
            
            if issues:
                for issue in issues:
                    print(f"  - {issue}")
    
    def menu_cns_readiness(self):
        """CNS tests"""
        print("\n[CNS READINESS]")
        print("1. Tap Test")
        print("2. Grip Strength")
        print("3. Vertical Jump")
        
        choice = input("Test: ").strip()
        
        if choice == "1":
            taps = int(input("Taps in 10sec: "))
            result = self.cns_tracker.add_tap_test(datetime.now(), taps)
            
            if 'baseline' in result:
                print(f"\nBaseline: {result['baseline']:.0f}")
                print(f"Today: {taps} ({result['percent']:.0f}%)")
                print(f"{result['status']}")
            else:
                print(result['message'])
        
        elif choice == "2":
            force = float(input("Grip (kg): "))
            result = self.cns_tracker.add_grip_strength(datetime.now(), force)
            
            if 'baseline' in result:
                print(f"\nBaseline: {result['baseline']:.0f}")
                print(f"Today: {force} ({result['percent']:.0f}%)")
                print(f"{result['status']}")
            else:
                print(result['message'])
        
        elif choice == "3":
            height = float(input("Jump (cm): "))
            result = self.cns_tracker.add_vertical_jump(datetime.now(), height)
            
            if 'baseline' in result:
                print(f"\nBaseline: {result['baseline']:.0f}")
                print(f"Today: {height} ({result['percent']:.0f}%)")
                print(f"{result['status']}")
            else:
                print(result['message'])
    
    def menu_data_import(self):
        """CSV import"""
        print("\n[DATA IMPORT]")
        
        if not PANDAS_AVAILABLE:
            print("[!] pandas not installed")
            print("Install: pip install pandas")
            return
        
        filepath = input("CSV path: ").strip()
        sessions, msg = self.data_importer.import_csv(filepath)
        print(msg)
        
        if sessions:
            print(f"\n{len(sessions)} sessions")
            for s in sessions[:3]:
                print(f"  {s['date']}: {s['distance_km']}km")

        # ---------------- v48 ULTIMATE MENUS ----------------
    
    def menu_gap(self):
        print("\n>>> GRADE ADJUSTED PACE (GAP)")
        try:
            pace_str = input("Actual pace (MM:SS/km): ")
            pace_sec = self.profile.str_to_sec(pace_str)
            elev = float(input("Elevation Gain (m): "))
            dist = float(input("Distance (km): "))
            gap = self.gap_engine.calculate_gap(pace_sec, elev, dist)
            cost = self.gap_engine.calculate_elevation_cost(elev, self.profile.weight_kg)
            print(f"\nACTUAL PACE: {pace_str}/km")
            print(f"GAP (Effort): {self.profile.sec_to_str(gap)}/km")
            print(f"Energy Cost of Vert: {cost} kcal")
        except: print("Invalid input.")

    def menu_power(self):
        print("\n>>> RUNNING POWER ESTIMATION")
        try:
            pace_str = input("Pace (MM:SS/km): ")
            pace_sec = self.profile.str_to_sec(pace_str)
            speed_ms = 1000.0 / pace_sec
            grad = float(input("Gradient % (0=Flat): "))
            power = self.power_engine.estimate_power(speed_ms, self.profile.weight_kg, grad)
            w_kg = power / self.profile.weight_kg
            print(f"\nESTIMATED POWER: {power:.0f} Watts")
            print(f"RATIO: {w_kg:.1f} W/kg")
        except: print("Invalid input.")

    def menu_biomech(self):
        print("\n>>> BIOMECHANICS SCAN")
        try:
            h = self.profile.height_cm
            opt = self.bio_engine.optimal_cadence(h)
            print(f"Optimal Cadence for {h}cm: {opt[0]}-{opt[1]} spm")
            cad = int(input("Your Cadence (spm): "))
            vo = float(input("Vert Oscillation (cm) [e.g. 8-12]: "))
            gct = float(input("Ground Contact Time (ms) [e.g. 200-300]: "))
            s, st, issues = self.bio_engine.analyze_form(cad, vo, gct)
            print(f"\nFORM SCORE: {s}/100 ({st})")
            for i in issues: print(f" - {i}")
        except: print("Invalid input.")

    def menu_cycle(self):
        print("\n>>> MENSTRUAL CYCLE OPTIMIZATION")
        try:
            day = int(input("Current Day of Cycle (1-28): "))
            phase = self.cycle_tracker.get_phase(day)
            rec = self.cycle_tracker.get_rec(day)
            print(f"\nPHASE: {phase}")
            print(f"RECOMMENDATION: {rec}")
        except: print("Invalid input.")

    def menu_altitude(self):
        print("\n>>> ALTITUDE ADJUSTMENT")
        try:
            alt = float(input("Current Training Altitude (m): "))
            adj = self.altitude_tracker.pace_adj(0, alt)
            print(f"Pace Penalty: {adj:.3f}x")
            ex_pace = 300 * adj # 5:00/km
            print(f"5:00/km feels like: {self.profile.sec_to_str(ex_pace)}/km")
            s, adv = self.altitude_tracker.status()
            print(f"STATUS: {s} ({adv})")
        except: print("Invalid input.")

    def menu_schedule(self):
        print("\n>>> SMART SCHEDULE GENERATOR")
        try:
            days_in = input("Available Days (0=Mon, 6=Sun) e.g., 0,2,4,6: ")
            days = [int(x) for x in days_in.split(",")]
            self.schedule_mgr.set_days(days)
            sched = self.schedule_mgr.generate(["INTERVALS", "TEMPO", "LONG_RUN", "EASY", "EASY"])
            print("\nSUGGESTED WEEK:")
            for d, s in sched.items():
                print(f" {d}: {s}")
        except: print("Invalid input.")

    def menu_progress(self):
        print("\n>>> PROGRESS ANALYZER")
        # Initialize dynamically with demo goal if not set
        if not hasattr(self, 'progress_engine'):
            goal_sec = self.profile.str_to_sec(self.profile.target_time) if self.profile.target_time else 2400
            self.progress_analyzer = ProgressAnalyzer(goal_sec=0, dist_km=0, race_date=datetime.now())
        
        print("1. Add Result  2. Check Probability")
        c = input("Select: ")
        if c == "1":
            d = float(input("Dist (km): "))
            t = input("Time (MM:SS): ")
            self.progress_engine.add(datetime.now(), d, self.profile.str_to_sec(t))
            print("Logged.")
        elif c == "2":
            prob, txt = self.progress_engine.probability()
            print(f"\nSUCCESS PROBABILITY: {prob}% ({txt})")
            print("INTERVENTIONS:")
            for i in self.progress_engine.interventions():
                print(f" - {i}")
# ---------------- v49 PROFESSIONAL MENUS ----------------
    def menu_race_strategy(self):
        print("\n>>> RACE PACING STRATEGY")
        try:
            time_str = input("Goal Time (HH:MM:SS): ")
            goal = self.profile.str_to_sec(time_str)
            dist = float(input("Distance (km): "))
            
            # Δημιουργία Demo Υψομετρικών (αφού δεν έχουμε χάρτη ακόμα)
            print("Generating demo elevation profile...")
            elev_profile = [0, 5, 10, 5, 0, -5, -10, -5, 0, 5] * (int(dist)//10 + 1)
            elev_profile = elev_profile[:int(dist)]
            
            # Υπολογισμός με βάση την αντοχή (Durability)
            # Αν δεν έχεις κάνει τεστ durability, βάζουμε default 92
            durability = 92 
            
            res = self.pacing_engine.calculate_optimal_splits(goal, dist, elev_profile, durability)
            
            print(f"\nSTRATEGY: {res['strategy']}")
            print(f"Confidence: {res['confidence']}")
            print("\nSPLITS (First 5km & Last 5km):")
            for s in res['splits'][:5]:
                print(f" KM {s['km']}: {self.profile.sec_to_str(s['pace_sec'])} (Elev: {s['elevation']}m)")
            print(" ...")
            for s in res['splits'][-5:]:
                print(f" KM {s['km']}: {self.profile.sec_to_str(s['pace_sec'])} (Elev: {s['elevation']}m)")
                
        except Exception as e: 
            print(f"Error in pacing strategy: {e}")

    def menu_recovery_score(self):
        print("\n>>> RECOVERY SCORE ENGINE")
        try:
            hrv = float(input("HRV (ms): "))
            sleep = float(input("Sleep (hours): "))
            qual = int(input("Sleep Quality (1-10): "))
            sore = int(input("Soreness (1-10): "))
            mood = int(input("Mood (1-10): "))
            
            # Πρέπει να ορίσουμε baseline αν δεν υπάρχει
            self.recovery_engine.set_baseline_hrv(self.profile.resting_hr_baseline + 20) # Rough estimate relative to RHR
            
            score, status, rec = self.recovery_engine.calculate_recovery_score(
                hrv, sleep, qual, sore, mood
            )
            print(f"\nRECOVERY SCORE: {score}/100")
            print(f"STATUS: {status}")
            print(f"ADVICE: {rec}")
        except Exception as e: 
            print(f"Invalid input: {e}")

    def menu_wearable_sync(self):
        print("\n>>> WEARABLE SYNC")
        print("Supported: Garmin Connect CSV, Stryd PowerCenter CSV")
        path = input("Path to CSV file: ").strip()
        if not path: return
        
        # Δοκιμή Garmin
        sessions, msg = self.sync_engine.import_garmin_csv(path)
        if sessions:
            print(f"Garmin: {msg}")
        else:
            # Δοκιμή Stryd αν αποτύχει το Garmin
            sessions, msg = self.sync_engine.import_stryd_csv(path)
            print(f"Stryd: {msg}")


# ---------------- v50 ULTRA MENUS ----------------

    def menu_ml_predict(self):
        print("\n>>> MACHINE LEARNING RACE PREDICTOR")
        if not SKLEARN_AVAILABLE:
            print("[!] Scikit-learn not installed. Cannot run prediction.")
            return

        print("1. Train Model (needs history)  2. Predict Performance")
        choice = input("Select: ")
        
        if choice == "1":
            # Εδώ κανονικά θα τραβούσε δεδομένα από τη βάση (self.db)
            # Για το demo, προσθέτουμε μερικά fake data
            print("Training model with demo data...")
            self.ml_brain.add_training_sample(85, 75, 55, 7.5, 240, 2400) # Demo 1
            self.ml_brain.add_training_sample(90, 80, 50, 7.0, 235, 2350) # Demo 2
            self.ml_brain.add_training_sample(80, 60, 60, 8.0, 245, 2450) # Demo 3
            self.ml_brain.add_training_sample(95, 90, 45, 6.5, 230, 2300) # Demo 4
            self.ml_brain.add_training_sample(88, 70, 58, 7.8, 238, 2380) # Demo 5
            
            success, msg = self.ml_brain.train_model()
            print(f"Result: {msg}")
            
        elif choice == "2":
            try:
                ctl = float(input("Current CTL: "))
                atl = float(input("Current ATL: "))
                hrv = float(input("Avg HRV (7d): "))
                sleep = float(input("Avg Sleep (h): "))
                pace = float(input("Recent 10K Pace (sec/km): "))
                
                pred, low, high, conf = self.ml_brain.predict_performance(ctl, atl, hrv, sleep, pace)
                
                if pred:
                    print(f"\n🔮 PREDICTED TIME: {self.profile.sec_to_str(pred)}")
                    print(f"   Range: {self.profile.sec_to_str(low)} - {self.profile.sec_to_str(high)}")
                    print(f"   Confidence: {conf}")
                else:
                    print("Model not trained yet.")
            except Exception as e:
                print(f"Error: {e}")

    def menu_taper(self):
        print("\n>>> TAPER OPTIMIZER (ML-Based)")
        try:
            days = int(input("Days to race: "))
            ctl = float(input("Current CTL: "))
            imp = input("Race Importance (A/B/C): ").upper()
            fresh = int(input("Psychological Freshness (1-10): "))
            
            # Δημιουργία ημερομηνίας αγώνα
            race_date = datetime.now() + timedelta(days=days)
            
            plan = self.taper_engine.calculate_taper_plan(ctl, race_date, imp, fresh)
            
            print(f"\n=== TAPER PLAN ({len(plan)} Days) ===")
            print(f"{'Day':<5} {'Vol%':<6} {'Intensity':<12} {'Notes'}")
            print("-" * 40)
            for day in plan:
                print(f"{day['day']:<5} {day['volume_pct']:<6} {day['intensity']:<12} {day['neuromuscular']}")
                
            # Εξήγηση από το σύστημα γνώσης
            trace = self.traceability.explain_taper_plan(ctl, days, plan[0]['volume_pct'], 40)
            print(trace)
            
        except Exception as e:
            print(f"Error: {e}")

    def menu_ascii_viz(self):
        print("\n>>> ASCII FORM VISUALIZATION")
        # Εδώ θα έπρεπε να παίρνει το πραγματικό ιστορικό TSB
        # Φτιάχνουμε demo δεδομένα για να δεις το γράφημα
        demo_history = []
        for i in range(14):
            date = datetime.now() - timedelta(days=14-i)
            val = -15 + (i * 2) # Demo ανοδική πορεία
            demo_history.append((date, val))
            
        print(self.ascii_viz.plot_tsb_trend(demo_history))
        print("\n")
        print(self.ascii_viz.plot_intensity_distribution(78, 22))

    def menu_simulation(self):
        print("\n>>> SIMULATION MODE (What-If)")
        try:
            curr_ctl = float(input("Current CTL: "))
            curr_atl = float(input("Current ATL: "))
            load = float(input("Planned Session Load (TSS): "))
            
            n_ctl, n_atl, n_tsb, risk, rec = self.sim_engine.simulate_session_impact(
                curr_ctl, curr_atl, load
            )
            
            print("\n🧪 SIMULATION RESULTS:")
            print(f"New CTL: {n_ctl} (+{n_ctl - curr_ctl:.1f})")
            print(f"New ATL: {n_atl} (+{n_atl - curr_atl:.1f})")
            print(f"New TSB: {n_tsb}")
            print(f"RISK LEVEL: {risk}")
            print(f"ADVICE: {rec}")
            
        except Exception as e:
            print(f"Input error: {e}")

    def menu_weather_live(self):
        print("\n>>> LIVE WEATHER INTELLIGENCE")
        if not REQUESTS_AVAILABLE:
            print("[!] Requests library not installed.")
            return

        # Κλήση API (Demo Mode αν δεν έβαλες κλειδί)
        temp, hum, cond, feels = self.weather_api.get_current_weather()
        
        if temp is not None:
            print(f"\n🌤️  CURRENT WEATHER ({self.weather_api.city})")
            print(f"Temp: {temp}°C (Feels like {feels}°C)")
            print(f"Humidity: {hum}%")
            print(f"Conditions: {cond}")
            
            # Έλεγχος για προσαρμογή προπόνησης
            planned = {'distance_km': 12, 'intensity': 'TEMPO', 'warmup_min': 15}
            print("\nAnalyzing planned TEMPO session...")
            mod, status = self.weather_api.adjust_session_for_weather(planned, temp, hum)
            
            if status == "MODIFIED":
                print(f"⚠️  SUGGESTED MODIFICATION: {mod['note']}")
                print(f"New Volume: {mod['distance_km']:.1f} km")
            else:
                print("✅ Conditions Optimal. Execute as planned.")
        else:
            print("Could not fetch weather data.")

    def menu_cognitive(self):
        print("\n>>> COGNITIVE LOAD MONITOR")
        try:
            mf = int(input("Mental Fatigue (1-10): "))
            ws = int(input("Work Stress (1-10): "))
            ls = int(input("Life Stress (1-10): "))
            
            # Καταγραφή
            entry = self.cognitive_monitor.log_cognitive_state(datetime.now(), mf, ws, ls)
            
            # Ανάλυση επίδρασης
            planned_rpe = 7 # Υποθέτουμε μια μέτρια προπόνηση
            adj_rpe, rec = self.cognitive_monitor.assess_cognitive_impact(entry['total_load'], planned_rpe)
            
            print(f"\n🧠 COGNITIVE LOAD: {entry['total_load']}/10")
            print(f"Expected RPE shift: {planned_rpe} -> {adj_rpe}")
            print("STRATEGY:")
            print(rec)
            
            # Recovery advice
            print("\nRECOVERY CHECKLIST:")
            for item in self.cognitive_monitor.recovery_recommendations(entry['total_load']):
                print(item)
                
        except:
            print("Invalid input.")

    def menu_weekly_report(self):
        print("\n>>> WEEKLY COMMANDER'S REPORT")
        # Εδώ κανονικά τραβάμε από self.db.get_history()
        # Φτιάχνουμε demo sessions
        demo_sessions = [
            {'distance_km': 10, 'duration_sec': 3000, 'intensity': 'EASY'},
            {'distance_km': 12, 'duration_sec': 3600, 'intensity': 'TEMPO'},
            {'distance_km': 8, 'duration_sec': 2400, 'intensity': 'EASY'},
            {'distance_km': 22, 'duration_sec': 7000, 'intensity': 'LONG_RUN'}
        ]
        
        target = float(input("Weekly Target (km): "))
        report = self.weekly_report.generate_report(demo_sessions, target)
        print(report)



# ==============================================================================
# TITAN v49 NEURAL - INTELLIGENT ADAPTIVE SYSTEM
# ==============================================================================

import sqlite3

class DatabaseManager:
    """
    Permanent memory system for TITAN
    Stores all training history, daily metrics, gear usage, and PRs
    
    Tables:
    - daily_metrics: Morning check-in data
    - training_log: Complete training history
    - gear_usage: Shoe tracking with compression recovery
    - personal_bests: PR tracking
    """
    
    def __init__(self, db_name="titan_core.db"):
        # Βρίσκει τον φάκελο που τρέχει το script
        base_dir = Path(__file__).parent.absolute()
        self.db_path = base_dir / db_name
        
        # Σύνδεση με τη βάση
        self.conn = sqlite3.connect(str(self.db_path))
        self.create_tables()
    

    def create_tables(self):
        """Create tables - alias for create_database"""
        return self.create_database()

    def create_database(self):
        """Initialize database with all tables"""
        self.conn = sqlite3.connect(self.db_path)
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
        
        self.conn.commit()
    
    def save_daily_metric(self, date, weight=None, hrv=None, rhr=None, 
                         sleep_hours=None, sleep_quality=None, soreness=None,
                         fatigue=None, mood=None, notes=None):
        """Save morning check-in data"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO daily_metrics 
            (date, weight_kg, hrv_rmssd, resting_hr, sleep_hours, sleep_quality,
             soreness, fatigue_level, mood, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (date, weight, hrv, rhr, sleep_hours, sleep_quality, soreness, fatigue, mood, notes))
        
        self.conn.commit()
    
    def save_session(self, date, session_type, distance_km, duration_sec, 
                    avg_hr=None, max_hr=None, rpe=None, shoe_id=None,
                    surface=None, temperature=None, notes=None):
        """Save training session"""
        cursor = self.conn.cursor()
        
        # Calculate training load (RPE * duration in minutes)
        training_load = (rpe * (duration_sec / 60)) if rpe else 0
        
        cursor.execute("""
            INSERT INTO training_log 
            (date, session_type, distance_km, duration_sec, avg_hr, max_hr, rpe,
             training_load, shoe_id, surface, temperature_c, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (date, session_type, distance_km, duration_sec, avg_hr, max_hr, rpe,
              training_load, shoe_id, surface, temperature, notes))
        
        # Update shoe mileage if shoe_id provided
        if shoe_id and distance_km:
            self.update_shoe_mileage(shoe_id, distance_km, date)
        
        self.conn.commit()
    
    def get_training_load_history(self, days=42):
        """Get training load for last N days (for TSB calculation)"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT date, training_load 
            FROM training_log 
            WHERE date >= date('now', '-' || ? || ' days')
            ORDER BY date DESC
        """, (days,))
        
        return cursor.fetchall()
    
    def get_ctl_atl_tsb(self):
        """
        Calculate real TSB from database history
        CTL (Chronic Training Load): 42-day exponential moving average
        ATL (Acute Training Load): 7-day exponential moving average
        TSB (Training Stress Balance): CTL - ATL
        """
        loads = self.get_training_load_history(42)
        
        if not loads:
            return 0, 0, 0
        
        # Calculate CTL (42-day EMA)
        ctl = 0
        ctl_decay = 2 / (42 + 1)
        
        for date, load in loads:
            ctl = (load * ctl_decay) + (ctl * (1 - ctl_decay))
        
        # Calculate ATL (7-day EMA, last 7 days)
        recent_loads = [l for d, l in loads if d][:7]
        atl = 0
        atl_decay = 2 / (7 + 1)
        
        for load in recent_loads:
            atl = (load * atl_decay) + (atl * (1 - atl_decay))
        
        # Calculate TSB
        tsb = ctl - atl
        
        return round(ctl, 1), round(atl, 1), round(tsb, 1)
    
    def update_shoe_mileage(self, shoe_id, distance_km, date):
        """Update shoe mileage"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            UPDATE gear_usage 
            SET total_km = total_km + ?, last_used = ?
            WHERE id = ?
        """, (distance_km, date, shoe_id))
        
        self.conn.commit()
    
    def add_shoe(self, name, shoe_type="DAILY", max_km=800):
        """Add new shoe to database"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            INSERT INTO gear_usage (shoe_name, shoe_type, max_km_limit)
            VALUES (?, ?, ?)
        """, (name, shoe_type, max_km))
        
        self.conn.commit()
        return cursor.lastrowid
    
    def get_active_shoes(self):
        """Get all active shoes"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT id, shoe_name, total_km, max_km_limit, last_used, shoe_type
            FROM gear_usage
            WHERE status = 'ACTIVE'
            ORDER BY shoe_name
        """)
        
        return cursor.fetchall()
    
    def check_shoe_availability(self, shoe_id):
        """
        Check if shoe is available for use
        Considers compression recovery (24h rest for foam)
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
    
    def save_personal_best(self, distance_km, time_sec, date, race_name=None):
        """Save PR"""
        cursor = self.conn.cursor()
        
        pace_per_km = time_sec / distance_km
        
        cursor.execute("""
            INSERT INTO personal_bests 
            (distance_km, time_sec, pace_sec_per_km, date, race_name)
            VALUES (?, ?, ?, ?, ?)
        """, (distance_km, time_sec, pace_per_km, date, race_name))
        
        self.conn.commit()
    
    def get_pr(self, distance_km):
        """Get PR for distance"""
        cursor = self.conn.cursor()
        
        cursor.execute("""
            SELECT time_sec, date, race_name
            FROM personal_bests
            WHERE distance_km = ?
            ORDER BY time_sec ASC
            LIMIT 1
        """, (distance_km,))
        
        return cursor.fetchone()
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


class PolarizedConstraint:
    """
    Seiler's Polarized Training Constraint
    Enforces 80/20 rule and prevents too many hard days
    """
    
    @staticmethod
    def check_recent_intensity(training_history, days=7):
        """
        Check last 7 days for high-intensity sessions
        
        Returns:
            (is_violation, hard_day_count, recommendation)
        """
        hard_sessions = 0
        
        for session in training_history[-days:]:
            if session.get('intensity') in ['HIGH', 'THRESHOLD', 'VO2MAX']:
                hard_sessions += 1
        
        # Seiler Rule: Max 2-3 hard days per week
        if hard_sessions >= 2:
            return True, hard_sessions, "EASY_ONLY_48H"
        
        return False, hard_sessions, "NORMAL"
    
    @staticmethod
    def calculate_intensity_distribution(training_history, days=7):
        """
        Calculate actual vs ideal intensity distribution
        
        Ideal (Polarized): 80% easy, 20% hard
        """
        total_time = 0
        easy_time = 0
        hard_time = 0
        
        for session in training_history[-days:]:
            duration = session.get('duration_sec', 0)
            intensity = session.get('intensity', 'EASY')
            
            total_time += duration
            
            if intensity in ['EASY', 'RECOVERY']:
                easy_time += duration
            elif intensity in ['HIGH', 'THRESHOLD', 'VO2MAX']:
                hard_time += duration
        
        if total_time == 0:
            return 0, 0
        
        easy_pct = (easy_time / total_time) * 100
        hard_pct = (hard_time / total_time) * 100
        
        return round(easy_pct, 1), round(hard_pct, 1)


class NonLinearLogic:
    """
    Flexible decision making: Green/Yellow/Red
    No more binary Yes/No
    """
    
    @staticmethod
    def evaluate_readiness(readiness_score):
        """
        Evaluate readiness and return action
        
        Returns:
            (color, action, modification)
        """
        if readiness_score >= 85:
            return "GREEN", "EXECUTE", "Full session as planned"
        elif readiness_score >= 70:
            return "YELLOW", "MODIFY", "Reduce volume by 30% or intensity by 10%"
        elif readiness_score >= 55:
            return "ORANGE", "DOWNGRADE", "Convert to easy recovery run"
        else:
            return "RED", "REST", "Mandatory rest day"
    
    @staticmethod
    def modify_session(planned_session, color):
        """
        Modify session based on readiness color
        """
        if color == "GREEN":
            return planned_session
        
        elif color == "YELLOW":
            # Reduce volume by 30%
            modified = planned_session.copy()
            modified['distance_km'] = modified.get('distance_km', 0) * 0.7
            modified['note'] = "Volume reduced 30% due to moderate readiness"
            return modified
        
        elif color == "ORANGE":
            # Downgrade to easy
            return {
                "type": "EASY",
                "distance_km": planned_session.get('distance_km', 0) * 0.5,
                "intensity": "RECOVERY",
                "note": "Downgraded to recovery due to low readiness"
            }
        
        else:  # RED
            return {
                "type": "REST",
                "distance_km": 0,
                "note": "Rest day mandated by system"
            }


class StochasticReadiness:
    """
    Probabilistic readiness with warmup decision
    Readiness is a range, not a point
    """
    
    @staticmethod
    def calculate_readiness_range(hrv_value, baseline_hrv, sleep_hours, soreness):
        """
        Calculate readiness as a range with confidence interval
        
        Returns:
            (low, mid, high, confidence)
        """
        # Base score from HRV
        hrv_pct = (hrv_value / baseline_hrv) * 100 if baseline_hrv else 90
        base_score = min(100, hrv_pct)
        
        # Adjustments
        sleep_adj = (sleep_hours / 8) * 10 if sleep_hours else 0
        soreness_adj = -((soreness - 5) * 2) if soreness else 0
        
        mid_score = base_score + sleep_adj + soreness_adj
        mid_score = max(0, min(100, mid_score))
        
        # Calculate range (±5 points)
        low_score = max(0, mid_score - 5)
        high_score = min(100, mid_score + 5)
        
        # Confidence (higher when measurements are stable)
        confidence = "HIGH" if high_score - low_score < 8 else "MODERATE"
        
        return round(low_score, 1), round(mid_score, 1), round(high_score, 1), confidence
    
    @staticmethod
    def warmup_decision_protocol():
        """
        When readiness is on the edge, use 10-min warmup test
        """
        return {
            "protocol": "10_MINUTE_WARMUP",
            "instructions": [
                "Start easy jog for 10 minutes",
                "Monitor: HR should stabilize, legs should loosen",
                "Decision point at 10:00:",
                "  - Feel better? Continue session",
                "  - Still heavy? Convert to easy day"
            ]
        }


class AdaptivePacing:
    """
    Dynamic pace targets based on readiness
    No more fixed paces
    """
    
    @staticmethod
    def calculate_adapted_pace(base_pace_sec, readiness_score):
        """
        Adjust target pace based on readiness
        
        base_pace_sec: Your normal pace for the session type
        readiness_score: Current readiness (0-100)
        
        Returns:
            adapted_pace_sec
        """
        if readiness_score >= 90:
            factor = 0.98  # 2% faster (feeling great)
        elif readiness_score >= 80:
            factor = 1.0   # Normal pace
        elif readiness_score >= 70:
            factor = 1.03  # 3% slower
        elif readiness_score >= 60:
            factor = 1.06  # 6% slower
        else:
            factor = 1.10  # 10% slower
        
        return round(base_pace_sec * factor, 1)
    
    @staticmethod
    def calculate_threshold_pace_today(lt2_pace_base, readiness_score):
        """
        Calculate today's threshold pace
        Maintains physiological stimulus even when tired
        """
        # LT2 is at a % of max HR, so we adjust to maintain that stimulus
        return AdaptivePacing.calculate_adapted_pace(lt2_pace_base, readiness_score)


class AdvancedHammer:
    """
    Hammer sessions with intensity levels
    Not just on/off switch
    """
    
    LEVELS = {
        1: {
            "name": "CONTROLLED",
            "pace_range": "Marathon to Half Marathon pace",
            "effort": "Can speak short sentences",
            "duration": "Up to 90 min"
        },
        2: {
            "name": "AGGRESSIVE",
            "pace_range": "10K to 5K pace",
            "effort": "Few words only",
            "duration": "30-60 min"
        },
        3: {
            "name": "FULL_SEND",
            "pace_range": "All out",
            "effort": "Cannot speak",
            "duration": "< 30 min"
        }
    }
    
    @staticmethod
    def get_hammer_level(session_type, fatigue_level):
        """
        Determine appropriate hammer level
        """
        if fatigue_level > 7:
            return None  # No hammer if fatigued
        
        if session_type == "TEMPO":
            return 1  # Controlled
        elif session_type == "THRESHOLD":
            return 2  # Aggressive
        elif session_type == "VO2MAX":
            return 3  # Full send
        else:
            return 1  # Default to controlled


class VO2MicroDosing:
    """
    Billat-style micro-dosing
    Keep nervous system alive without metabolic cost
    """
    
    @staticmethod
    def check_if_allowed(ctl, atl, readiness):
        """
        Micro-dosing allowed when:
        - In fatigue (ATL > CTL)
        - But not severely fatigued (readiness > 60)
        """
        if atl > ctl and readiness > 60:
            return True, "Micro-dosing allowed"
        elif readiness <= 60:
            return False, "Too fatigued for any intensity"
        else:
            return False, "Not in fatigue phase"
    
    @staticmethod
    def get_protocol():
        """
        Return micro-dosing protocol
        """
        return {
            "name": "Billat Micro-Dose",
            "structure": "4-6 x (30sec fast / 30sec recovery)",
            "pace": "VO2max pace",
            "total_hard_time": "2-3 minutes only",
            "rationale": "Neurological stimulus without metabolic cost",
            "when": "During recovery weeks or high fatigue"
        }


class TissueLoadProxy:
    """
    Eccentric load calculator
    Predicts injury risk based on impact
    """
    
    SURFACE_HARDNESS = {
        "TRAIL": 0.5,
        "GRASS": 0.6,
        "TRACK": 0.8,
        "ASPHALT": 1.0,
        "CONCRETE": 1.2
    }
    
    @staticmethod
    def calculate_eccentric_load(distance_km, surface, shoe_age_km, shoe_max_km=800):
        """
        Eccentric Load = Distance × Surface Hardness × Shoe Degradation
        """
        surface_factor = TissueLoadProxy.SURFACE_HARDNESS.get(surface, 1.0)
        
        # Shoe degradation increases exponentially after 70% life
        shoe_degradation = 1.0
        if shoe_age_km > (shoe_max_km * 0.7):
            excess = shoe_age_km - (shoe_max_km * 0.7)
            shoe_degradation = 1 + (excess / (shoe_max_km * 0.3)) * 0.5
        
        eccentric_load = distance_km * surface_factor * shoe_degradation
        
        return round(eccentric_load, 2)
    
    @staticmethod
    def assess_injury_risk(eccentric_load, cumulative_week_load):
        """
        Assess injury risk based on eccentric load
        """
        # Weekly threshold
        if cumulative_week_load > 150:
            return "HIGH", "Excessive weekly eccentric load - tendon stress"
        elif cumulative_week_load > 100:
            return "MODERATE", "Elevated load - monitor for pain"
        else:
            return "LOW", "Normal load"


class ExplanationLayer:
    """
    The Coach Speaks - Explain WHY decisions are made
    """
    
    @staticmethod
    def explain_denial(reason_code, details):
        """
        Generate explanation for denied sessions
        """
        explanations = {
            "HIGH_ATL": f"Hammer Denied: Your Acute Fatigue (ATL) is {details.get('atl_pct', 0)}% above normal. Need recovery.",
            
            "SHOE_BLOCKED": f"Shoe Blocked: {details.get('shoe_name', 'Shoe')} needs {details.get('hours_left', 24)}h foam recovery (compression set).",
            
            "POLARIZED_VIOLATION": f"High Intensity Denied: You've done {details.get('hard_days', 0)} hard sessions in 7 days. Seiler's rule: max 2-3.",
            
            "TISSUE_OVERLOAD": f"Session Modified: Eccentric load would be {details.get('eccentric_load', 0)} (threshold: 50). High tendon stress predicted.",
            
            "LOW_READINESS": f"Session Downgraded: Readiness is {details.get('readiness', 0)}/100. Your body needs easier stress today.",
            
            "HRV_SUPPRESSED": f"Rest Recommended: HRV is {details.get('hrv_pct', 0)}% of baseline. Autonomic nervous system needs recovery."
        }
        
        return explanations.get(reason_code, f"Denied: {reason_code}")
    
    @staticmethod
    def explain_modification(modification_type, before, after):
        """
        Explain session modifications
        """
        return {
            "original_plan": before,
            "modified_plan": after,
            "reason": f"Modified due to: {modification_type}",
            "rationale": "Maintaining training stimulus while respecting recovery needs"
        }




if __name__ == "__main__":
    try:
        # Δημιουργία και εκκίνηση της εφαρμογής
        app = TitanSystem()
        app.run()
    except Exception as e:
        # Αν υπάρξει σφάλμα, τύπωσε το και ΠΕΡΙΜΕΝΕ
        print("\n" + "="*60)
        print("CRITICAL ERROR - ΤΟ ΠΡΟΓΡΑΜΜΑ ΤΕΡΜΑΤΙΣΕ")
        print("="*60)
        print(f"Error Details: {e}")
        print("="*60)
        # Αυτή η εντολή κρατάει το παράθυρο ανοιχτό:
        input("\nΠατήστε ENTER για έξοδο...")
    except KeyboardInterrupt:
        print("\nUser Cancelled.")

"""
Nutrition Optimizer
Weight-based nutrition adjustment with scientific backing.
Integrates with Garmin weight data to provide real-time dietary recommendations.
"""

import logging
from dataclasses import dataclass

from titan.config.thresholds import (
    FAT_KCAL_PER_GRAM,
    HYDRATION_BASE_ML_PER_KG,
    HYDRATION_EASY_ML,
    HYDRATION_INTERVALS_ML,
    HYDRATION_LONG_RUN_ML,
    HYDRATION_TEMPO_ML,
    MIN_FAT_G,
)
from titan.core.structured_events import make_event_emitter

_log = logging.getLogger(__name__)
_nutrition_event = make_event_emitter("nutrition", _log)


@dataclass
class NutritionPreferences:
    training_time: str = 'variable'   # 'morning'|'midday'|'evening'|'variable'
    fasted_training: str = 'easy_only'  # 'always'|'never'|'easy_only'
    dietary_style: str = 'standard'    # 'standard'|'mediterranean'|'low_carb'|'vegetarian'
    meal_frequency: int = 3
    biological_sex: str = 'male'       # 'male'|'female'|'prefer_not_to_say'
    menstrual_tracking: str = 'no'     # 'yes'|'no'
    menstrual_phase: str | None = None  # 'follicular'|'luteal'|None


class NutritionOptimizer:
    """
    Scientific nutrition optimizer based on training load and weight trends.

    Based on research from:
    - Burke, L.M. et al. (2011) - Carbohydrate periodization
    - Jeukendrup, A.E. (2014) - Fuel for athletes
    - Mountjoy, M. et al. (2018) - RED-S (Relative Energy Deficiency in Sport)
    """

    def __init__(self, glycogen_model):
        """
        Initialize nutrition optimizer.

        Args:
            glycogen_model: GlycogenModel instance for depletion calculations
        """
        self.glycogen_model = glycogen_model
        self.weight_history = []

    def add_weight_entry(self, date: str, weight_kg: float):
        """Add weight entry from Garmin or manual input."""
        self.weight_history.append((date, weight_kg))
        # Keep last 90 days only
        if len(self.weight_history) > 90:
            self.weight_history = self.weight_history[-90:]

    def analyze_weight_trend(self, days: int = 7) -> dict:
        """
        Analyze weight trend over specified period.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary with trend analysis
        """
        if len(self.weight_history) < days:
            return {
                "status": "INSUFFICIENT_DATA",
                "change_kg": 0,
                "change_pct": 0,
                "velocity": 0,
                "recommendation": "Need more weight data",
            }

        recent = self.weight_history[-days:]
        first_weight = recent[0][1]
        if first_weight <= 0:
            return {
                "status": "INSUFFICIENT_DATA",
                "change_kg": 0,
                "change_pct": 0,
                "velocity": 0,
                "recommendation": "Need valid baseline weight data",
            }

        last_weight = recent[-1][1]

        change_kg = last_weight - first_weight
        change_pct = (change_kg / first_weight) * 100
        velocity = change_kg / (days / 7)  # kg per week

        # Interpret
        if abs(velocity) < 0.2:
            status = "STABLE"
            rec = "Maintain current nutrition"
        elif velocity > 0.5:
            status = "GAINING_FAST"
            rec = "Reduce calories by 200-300 kcal/day"
        elif velocity > 0.2:
            status = "GAINING"
            rec = "Minor calorie reduction if undesired"
        elif velocity < -0.5:
            status = "LOSING_FAST"
            rec = "⚠️ Increase calories - risk of RED-S"
        elif velocity < -0.2:
            status = "LOSING"
            rec = "Monitor energy availability"
        else:
            status = "STABLE"
            rec = "Continue current approach"

        result = {
            "status": status,
            "change_kg": round(change_kg, 2),
            "change_pct": round(change_pct, 2),
            "velocity_kg_per_week": round(velocity, 2),
            "recommendation": rec,
            "first_weight": first_weight,
            "current_weight": last_weight,
        }
        _nutrition_event(
            "weight_trend_analyzed",
            days=days,
            status=result["status"],
            velocity_kg_per_week=result["velocity_kg_per_week"],
            change_pct=result["change_pct"],
        )
        return result

    def calculate_daily_nutrition(
        self,
        weight_kg: float,
        today_session: dict,
        tomorrow_session: dict = None,
        training_phase: str = "BUILD",
        height_cm: int = 180,
        age: int = 35,
        prefs: 'NutritionPreferences | None' = None,
        optimal_time_hour: int = 7,
    ) -> dict:
        """
        Calculate today's nutrition requirements.

        Args:
            weight_kg: Current weight
            today_session: Today's training session dict
            tomorrow_session: Tomorrow's session (for pre-fueling)
            training_phase: Current phase (BASE/BUILD/PEAK/TAPER)

        Returns:
            Comprehensive nutrition plan
        """
        session_type = today_session.get("session_type", "REST")
        duration_min = today_session.get("duration_min", 0)

        # Base metabolic calculations
        # Using simplified Mifflin-St Jeor for male athlete (can be adjusted)
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5  # Mifflin-St Jeor (male)

        # Activity multiplier based on session
        activity_multipliers = {
            "REST": 1.2,
            "EASY": 1.5,
            "TEMPO": 1.7,
            "INTERVALS": 1.8,
            "LONG_RUN": 1.9,
            "HAMMER": 1.8,
            "RACE": 2.0,
        }

        multiplier = activity_multipliers.get(session_type, 1.5)
        tdee = bmr * multiplier

        # Carbohydrate requirements (Burke et al. 2011)
        carb_ranges = {
            "REST": (3, 5),
            "EASY": (5, 7),
            "TEMPO": (6, 8),
            "INTERVALS": (7, 10),
            "LONG_RUN": (8, 10),
            "HAMMER": (7, 10),
            "RACE": (10, 12),
        }

        carb_low, carb_high = carb_ranges.get(session_type, (5, 7))

        # --- A. Sex-based calorie adjustment ---
        if prefs and prefs.biological_sex == 'female':
            tdee *= 0.87  # Arciero et al 1993
            if prefs.menstrual_phase == 'luteal':
                tdee += 200  # Benton & Young 2012

        # --- B. Protein ---
        if prefs and prefs.biological_sex == 'female':
            protein_g = weight_kg * (1.8 if session_type in ('INTERVALS', 'TEMPO') else 1.6)
        else:
            protein_g = weight_kg * 1.8  # Morton et al 2018 conservative

        # --- C. Carb / fat ---
        quality_session = session_type in ('TEMPO', 'INTERVALS', 'HAMMER', 'LONG_RUN', 'RACE')
        low_carb_note: str | None = None
        vegetarian_note: bool = False

        carb_g = weight_kg * ((carb_low + carb_high) / 2)

        dietary_style = prefs.dietary_style if prefs else 'standard'
        if dietary_style == 'mediterranean':
            carb_g = tdee * 0.50 / 4
            fat_g = max(MIN_FAT_G, tdee * 0.30 / FAT_KCAL_PER_GRAM)
        elif dietary_style == 'low_carb' and not quality_session:
            carb_g = tdee * 0.35 / 4
            fat_g = max(MIN_FAT_G, tdee * 0.45 / FAT_KCAL_PER_GRAM)
        elif dietary_style == 'low_carb' and quality_session:
            low_carb_note = "⚠️ Υδατάνθρακες δεν μειώθηκαν — ποιοτική προπόνηση απαιτεί γλυκογόνο"
            carb_kcal = carb_g * 4
            protein_kcal = protein_g * 4
            fat_g = max(MIN_FAT_G, (tdee - carb_kcal - protein_kcal) / FAT_KCAL_PER_GRAM)
        else:
            if dietary_style == 'vegetarian':
                vegetarian_note = True
            carb_kcal = carb_g * 4
            protein_kcal = protein_g * 4
            fat_g = max(MIN_FAT_G, (tdee - carb_kcal - protein_kcal) / FAT_KCAL_PER_GRAM)

        # Session-specific timing
        timing = self._get_meal_timing(session_type, duration_min)

        # Hydration — weight-based daily need + session-type adjustment
        hydration_ml = self._calculate_hydration(weight_kg, session_type)
        if prefs and prefs.biological_sex == 'female':
            hydration_ml = round(hydration_ml * 0.85 / 100) * 100

        # Meal schedule (personalized if prefs given)
        meal_schedule = self._build_meal_schedule(
            prefs, session_type, duration_min, optimal_time_hour,
            today_session.get('distance_km', 0)
        )

        # Special notes
        special_notes = self._get_special_notes(session_type, tomorrow_session)
        if prefs:
            if low_carb_note:
                special_notes.append(low_carb_note)
            if prefs.menstrual_phase == 'luteal':
                special_notes.append("🔴 Ωχρινική φάση: +200 kcal, αυξημένες ανάγκες σε σίδηρο και μαγνήσιο")
            if vegetarian_note:
                special_notes.append("🌱 Στόχος πρωτεΐνης από: φυτικές πηγές όσπρια, τόφου, τέμπε, κινόα, ελληνικό γιαούρτι")
            if prefs.fasted_training in ('always', 'easy_only') and session_type == 'LONG_RUN':
                special_notes.append("⚠️ Μην τρέξεις νηστικός σε μεγάλες αποστάσεις")

        plan = {
            "total_calories": round(tdee, 0),
            "calories": round(tdee, 0),
            "carbs_g": round(carb_g, 0),
            "carbs_range": f"{int(weight_kg * carb_low)}-{int(weight_kg * carb_high)}g",
            "protein_g": round(protein_g, 0),
            "fat_g": round(fat_g, 0),
            "hydration_ml": hydration_ml,
            "pre_session": timing["pre_session"],
            "during_session": timing["during_session"],
            "post_session": timing["post_session"],
            "meal_schedule": meal_schedule,
            "special_notes": special_notes,
            "weight_trend": self.analyze_weight_trend(),
        }

        _nutrition_event(
            "daily_plan_calculated",
            session_type=session_type,
            duration_min=duration_min,
            training_phase=training_phase,
            calories=plan["total_calories"],
            carbs_g=plan["carbs_g"],
            hydration_ml=hydration_ml,
            weight_status=plan["weight_trend"].get("status"),
        )

        return plan

    def _get_meal_timing(self, session_type: str, duration_min: int) -> dict:
        """Get session-specific meal timing recommendations."""
        if session_type in ["INTERVALS", "TEMPO", "HAMMER"]:
            return {
                "pre_session": "60-90g carbs 2-3h before",
                "during_session": "30-60g carbs/hour if >90min"
                if duration_min > 90
                else "Water only",
                "post_session": "1.2g carbs/kg + 20-30g protein within 30min",
            }
        if session_type == "LONG_RUN":
            return {
                "pre_session": "30-60g carbs (can train low if not hammering)",
                "during_session": "60g carbs/hour (gels/sports drink)",
                "post_session": "1.2-1.5g carbs/kg within 2h + 20-30g protein",
            }
        if session_type == "EASY":
            return {
                "pre_session": "Optional - can train fasted",
                "during_session": "Water only",
                "post_session": "Normal breakfast - prioritize protein 20-30g",
            }
        # REST
        return {
            "pre_session": "N/A",
            "during_session": "N/A",
            "post_session": "Regular meals - focus on whole foods",
        }

    def _calculate_hydration(
        self,
        weight_kg: float,
        session_type: str = "EASY",
    ) -> int:
        """
        Calculate daily hydration need: body-weight baseline + session-type adjustment.

        Science:
        - Base: 35 ml/kg/day (Burke et al. 2011; Sawka et al. 2007 ACSM position stand)
        - Session adjustments account for sweat losses by intensity class

        Session adjustments (ml):
          LONG_RUN:             +800
          INTERVALS / HAMMER:   +600
          TEMPO / RACE:         +500
          EASY / PROGRESSIVE:   +300
          REST / other:         +0

        Result is rounded to the nearest 100 ml.
        """
        base_ml = weight_kg * HYDRATION_BASE_ML_PER_KG

        session_adjustments = {
            "LONG_RUN": HYDRATION_LONG_RUN_ML,
            "INTERVALS": HYDRATION_INTERVALS_ML,
            "HAMMER": HYDRATION_INTERVALS_ML,
            "TEMPO": HYDRATION_TEMPO_ML,
            "RACE": HYDRATION_TEMPO_ML,
            "EASY": HYDRATION_EASY_ML,
            "PROGRESSIVE": HYDRATION_EASY_ML,
        }
        adjustment = session_adjustments.get(session_type, 0)

        total_ml = base_ml + adjustment
        return round(total_ml / 100) * 100

    def _get_special_notes(self, session_type: str, tomorrow_session: dict = None) -> list[str]:
        """Get special nutrition notes."""
        notes = []

        if session_type in ["INTERVALS", "TEMPO", "HAMMER"]:
            notes.append("⚡ High glycogen demand - ensure adequate carbs")

        if tomorrow_session and tomorrow_session.get("session_type") in [
            "INTERVALS",
            "TEMPO",
            "HAMMER",
        ]:
            notes.append("🔋 Tomorrow is quality - refuel well tonight")

        if session_type == "LONG_RUN":
            notes.append("🏃 Test race nutrition during this run")

        weight_trend = self.analyze_weight_trend()
        if weight_trend.get("velocity_kg_per_week", 0) < -0.5:
            notes.append("⚠️ Rapid weight loss detected - increase calories to avoid RED-S")

        return notes

    def _build_meal_schedule(
        self,
        prefs: 'NutritionPreferences | None',
        session_type: str,
        duration_min: int,
        optimal_time_hour: int = 7,
        distance_km: float = 0,
    ) -> list[dict]:
        """Build a personalized meal schedule based on preferences."""
        if prefs is None:
            return []

        training_time = prefs.training_time
        if training_time == 'variable':
            h = optimal_time_hour
            if 6 <= h <= 9:
                training_time = 'morning'
            elif 10 <= h <= 14:
                training_time = 'midday'
            elif 15 <= h <= 20:
                training_time = 'evening'
            else:
                training_time = 'morning'

        show_preworkout = (
            prefs.fasted_training == 'never' or
            (prefs.fasted_training == 'easy_only' and session_type not in ('EASY', 'RECOVERY', 'REST'))
        )

        schedule = []
        meal_freq = prefs.meal_frequency

        if training_time == 'morning':
            if show_preworkout:
                schedule.append({'time': '05:00', 'label': 'ΠΡΟ-ΠΡΟΠΟΝΗΤΙΚΟ', 'description': '15-20g carbs + καφές. Μπανάνα ή φρυγανιά με μέλι.'})
            schedule.append({'time': '07:30', 'label': 'ΜΕΤΑ-ΠΡΟΠΟΝΗΤΙΚΟ', 'description': 'Κύριο πρωινό — 20-30g πρωτεΐνη + carbs αναπλήρωσης'})
            schedule.append({'time': '12:30', 'label': 'ΜΕΣΗΜΕΡΙΑΝΟ', 'description': 'Ισορροπημένο — carbs + πρωτεΐνη + λαχανικά'})
            if meal_freq == 5:
                schedule.append({'time': '16:00', 'label': 'ΣΝΑΚ', 'description': 'Φρούτο + χούφτα ξηροί καρποί'})
            schedule.append({'time': '19:30', 'label': 'ΒΡΑΔΙΝΟ', 'description': 'Lean protein + λαχανικά + σύνθετοι carbs'})

        elif training_time == 'midday':
            schedule.append({'time': '07:30', 'label': 'ΠΡΩΙΝΟ', 'description': 'Κανονικό πρωινό 2-3ώρες πριν'})
            if show_preworkout:
                schedule.append({'time': '10:00', 'label': 'ΠΡΟ-ΠΡΟΠΟΝΗΤΙΚΟ', 'description': 'Μικρό σνακ — 20-25g carbs'})
            schedule.append({'time': '13:00', 'label': 'ΜΕΤΑ-ΠΡΟΠΟΝΗΤΙΚΟ / ΜΕΣΗΜΕΡΙΑΝΟ', 'description': 'Κύριο γεύμα — πρωτεΐνη + carbs αναπλήρωσης'})
            if meal_freq == 5:
                schedule.append({'time': '16:00', 'label': 'ΣΝΑΚ', 'description': 'Γιαούρτι / φρούτο'})
            schedule.append({'time': '19:30', 'label': 'ΒΡΑΔΙΝΟ', 'description': 'Ισορροπημένο γεύμα'})

        elif training_time == 'evening':
            schedule.append({'time': '07:30', 'label': 'ΠΡΩΙΝΟ', 'description': 'Πλούσιο πρωινό'})
            schedule.append({'time': '12:30', 'label': 'ΜΕΣΗΜΕΡΙΑΝΟ', 'description': 'Κύριο γεύμα — καλή φόρτωση carbs'})
            if show_preworkout:
                schedule.append({'time': '15:30', 'label': 'ΠΡΟ-ΠΡΟΠΟΝΗΤΙΚΟ', 'description': 'Ελαφρύ σνακ — 20g carbs, χαμηλά λιπαρά'})
            schedule.append({'time': '19:30', 'label': 'ΜΕΤΑ-ΠΡΟΠΟΝΗΤΙΚΟ', 'description': 'Γρήγορη πρωτεΐνη + carbs αναπλήρωσης'})
            if session_type == 'LONG_RUN' or distance_km > 15:
                schedule.append({'time': '21:30', 'label': 'ΑΝΑΚΑΜΨΗ', 'description': 'Κεράκι πρωτεΐνης + σύνθετοι carbs'})

        return schedule

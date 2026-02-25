"""
Nutrition Optimizer

Weight-based nutrition adjustment with scientific backing.
Integrates with Garmin weight data to provide real-time dietary recommendations.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

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
    
    def analyze_weight_trend(self, days: int = 7) -> Dict:
        """
        Analyze weight trend over specified period.
        
        Args:
            days: Number of days to analyze
        
        Returns:
            Dictionary with trend analysis
        """
        if len(self.weight_history) < days:
            return {
                'status': 'INSUFFICIENT_DATA',
                'change_kg': 0,
                'change_pct': 0,
                'velocity': 0,
                'recommendation': 'Need more weight data'
            }
        
        recent = self.weight_history[-days:]
        first_weight = recent[0][1]
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
        
        return {
            'status': status,
            'change_kg': round(change_kg, 2),
            'change_pct': round(change_pct, 2),
            'velocity_kg_per_week': round(velocity, 2),
            'recommendation': rec,
            'first_weight': first_weight,
            'current_weight': last_weight
        }
    
    def calculate_daily_nutrition(
        self,
        weight_kg: float,
        today_session: Dict,
        tomorrow_session: Dict = None,
        training_phase: str = 'BUILD',
        height_cm: int = 180,
        age: int = 35,
    ) -> Dict:
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
        session_type = today_session.get('session_type', 'REST')
        duration_min = today_session.get('duration_min', 0)
        
        # Base metabolic calculations
        # Using simplified Mifflin-St Jeor for male athlete (can be adjusted)
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + 5  # Mifflin-St Jeor (male)
        
        # Activity multiplier based on session
        activity_multipliers = {
            'REST': 1.2,
            'EASY': 1.5,
            'TEMPO': 1.7,
            'INTERVALS': 1.8,
            'LONG_RUN': 1.9,
            'HAMMER': 1.8,
            'RACE': 2.0
        }
        
        multiplier = activity_multipliers.get(session_type, 1.5)
        tdee = bmr * multiplier
        
        # Carbohydrate requirements (Burke et al. 2011)
        carb_ranges = {
            'REST': (3, 5),
            'EASY': (5, 7),
            'TEMPO': (6, 8),
            'INTERVALS': (7, 10),
            'LONG_RUN': (8, 10),
            'HAMMER': (7, 10),
            'RACE': (10, 12)
        }
        
        carb_low, carb_high = carb_ranges.get(session_type, (5, 7))
        
        # Protein requirements (1.6-2.2 g/kg for endurance athletes)
        protein_g = weight_kg * 1.8
        
        # Fat (remaining calories)
        carb_g = weight_kg * ((carb_low + carb_high) / 2)
        carb_kcal = carb_g * 4
        protein_kcal = protein_g * 4
        fat_kcal = tdee - carb_kcal - protein_kcal
        fat_g = max(40, fat_kcal / 9)  # Minimum 40g fat
        
        # Session-specific timing
        timing = self._get_meal_timing(session_type, duration_min)
        
        # Hydration — combine dew_point and session intensity
        hydration_ml = self._calculate_hydration(
            duration_min,
            today_session.get('dew_point', 15),
            session_type,
        )
        
        return {
            'total_calories': round(tdee, 0),
            'carbs_g': round(carb_g, 0),
            'carbs_range': f"{int(weight_kg * carb_low)}-{int(weight_kg * carb_high)}g",
            'protein_g': round(protein_g, 0),
            'fat_g': round(fat_g, 0),
            'hydration_ml': hydration_ml,
            'pre_session': timing['pre_session'],
            'during_session': timing['during_session'],
            'post_session': timing['post_session'],
            'special_notes': self._get_special_notes(session_type, tomorrow_session),
            'weight_trend': self.analyze_weight_trend()
        }
    
    def _get_meal_timing(self, session_type: str, duration_min: int) -> Dict:
        """Get session-specific meal timing recommendations."""
        if session_type in ['INTERVALS', 'TEMPO', 'HAMMER']:
            return {
                'pre_session': "60-90g carbs 2-3h before",
                'during_session': "30-60g carbs/hour if >90min" if duration_min > 90 else "Water only",
                'post_session': "1.2g carbs/kg + 20-30g protein within 30min"
            }
        elif session_type == 'LONG_RUN':
            return {
                'pre_session': "30-60g carbs (can train low if not hammering)",
                'during_session': "60g carbs/hour (gels/sports drink)",
                'post_session': "1.2-1.5g carbs/kg within 2h + 20-30g protein"
            }
        elif session_type == 'EASY':
            return {
                'pre_session': "Optional - can train fasted",
                'during_session': "Water only",
                'post_session': "Normal breakfast - prioritize protein 20-30g"
            }
        else:  # REST
            return {
                'pre_session': "N/A",
                'during_session': "N/A",
                'post_session': "Regular meals - focus on whole foods"
            }
    
    def _calculate_hydration(
        self,
        duration_min: int,
        dew_point: float,
        session_type: str = "EASY",
    ) -> int:
        """
        Calculate hydration needs combining dew-point heat stress and
        session intensity.

        Science:
        - Fluid loss ~10-20% per 5°C rise in perceived heat (Sawka et al. 2007)
        - High-intensity sessions increase sweat rate independent of temperature
        - Base rate: 500 ml/h for mild easy aerobic

        Dew Point thresholds (°C):
          ≥ 22  Oppressive  → 1000 ml/h
          ≥ 18  Uncomfortable → 800 ml/h
          ≥ 15  Sticky      → 650 ml/h
          < 15  Comfortable → 500 ml/h

        Intensity multipliers:
          INTERVALS / HAMMER → ×1.4
          TEMPO / RACE       → ×1.2
          LONG_RUN           → ×1.1  (duration compensates naturally)
          EASY / REST        → ×1.0
        """
        hours = duration_min / 60.0

        # Dew-point base rate
        if dew_point >= 22:
            hourly_rate = 1000
        elif dew_point >= 18:
            hourly_rate = 800
        elif dew_point >= 15:
            hourly_rate = 650
        else:
            hourly_rate = 500

        # Intensity multiplier
        intensity_map = {
            "INTERVALS": 1.4,
            "HAMMER"   : 1.4,
            "TEMPO"    : 1.2,
            "RACE"     : 1.2,
            "LONG_RUN" : 1.1,
        }
        intensity_factor = intensity_map.get(session_type, 1.0)

        total_ml = hours * hourly_rate * intensity_factor
        return int(round(total_ml))
    
    def _get_special_notes(self, session_type: str, tomorrow_session: Dict = None) -> List[str]:
        """Get special nutrition notes."""
        notes = []
        
        if session_type in ['INTERVALS', 'TEMPO', 'HAMMER']:
            notes.append("⚡ High glycogen demand - ensure adequate carbs")
        
        if tomorrow_session and tomorrow_session.get('session_type') in ['INTERVALS', 'TEMPO', 'HAMMER']:
            notes.append("🔋 Tomorrow is quality - refuel well tonight")
        
        if session_type == 'LONG_RUN':
            notes.append("🏃 Test race nutrition during this run")
        
        weight_trend = self.analyze_weight_trend()
        if weight_trend.get('velocity_kg_per_week', 0) < -0.5:
            notes.append("⚠️ Rapid weight loss detected - increase calories to avoid RED-S")
        
        return notes

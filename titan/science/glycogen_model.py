"""Glycogen Depletion and Refueling Model (Burke et al. 2011)"""
from typing import Dict

class GlycogenModel:
    """Estimate glycogen cost and refueling needs"""
    
    @staticmethod
    def estimate_glycogen_depletion(duration_min: float, intensity_pct_vo2max: float) -> Dict:
        """Estimate glycogen cost of session"""
        if intensity_pct_vo2max > 85:
            rate, desc = 2.5, "HIGH (intervals/race)"
        elif intensity_pct_vo2max > 75:
            rate, desc = 1.8, "MODERATE-HIGH (tempo)"
        elif intensity_pct_vo2max > 65:
            rate, desc = 1.2, "MODERATE (steady)"
        else:
            rate, desc = 0.8, "EASY (fat burning)"
        
        return {
            "glycogen_depleted_g": round(duration_min * rate, 0),
            "intensity_classification": desc,
            "depletion_rate": rate,
            "refuel_recommendation": "1.2-1.5 g carbs/kg within 2h"
        }
    
    @staticmethod
    def daily_carb_recommendation(weight_kg: float, training_load: str) -> Dict:
        """Daily carb needs (Burke et al. 2011)"""
        recs = {
            "LIGHT": (3, 5, "Recovery days"),
            "MODERATE": (5, 7, "Base training"),
            "HIGH": (6, 10, "Normal load"),
            "VERY_HIGH": (8, 12, "Heavy blocks")
        }
        low, high, ctx = recs.get(training_load, (5, 7, "Moderate"))
        return {
            "carbs_g_per_kg_low": low,
            "carbs_g_per_kg_high": high,
            "total_carbs_range": f"{int(low * weight_kg)}-{int(high * weight_kg)}g",
            "context": ctx
        }

class GlycogenEngine:
    """Simple glycogen status checker (from original TITAN)"""

    @staticmethod
    def glycogen_flag(low_carb_day: bool, back_to_back_quality: bool, weight: float) -> tuple:
        """
        Glycogen availability check.
        
        Args:
            low_carb_day: Is this a low-carb day?
            back_to_back_quality: Quality sessions on consecutive days?
            weight: Athlete weight in kg
        
        Returns:
            (hammer_allowed, min_carbs, flags)
        """
        flags = []
        hammer_allowed = True
        min_carbs = None

        if low_carb_day:
            hammer_allowed = False
            flags.append("LOW_GLYCOGEN: Hammer forbidden today")

        if back_to_back_quality:
            min_carbs = int(7 * weight)
            flags.append(f"BACK-TO-BACK QUALITY: Carbs ≥ {min_carbs}g required")

        if not flags:
            flags.append("GLYCOGEN OK: Normal fueling rules")

        return hammer_allowed, min_carbs, flags

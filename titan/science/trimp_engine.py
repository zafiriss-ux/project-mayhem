"""TRIMP Engine - Training Impulse Calculation"""
from typing import Tuple, Optional
import math

class TRIMPEngine:
    """
    Training Impulse - HR-weighted load quantification.
    
    Scientific Basis:
    - Banister, E.W. (1975). Aust J Sports Med, 7(3), 57-61
    - Edwards, S. (1993). The Heart Rate Monitor Book
    - Manzi, V. et al. (2009). Int J Sports Physiol Perform, 4(3), 347-357
    
    Why better than volume alone:
    10km @ 140 HR ≠ 10km @ 165 HR
    TRIMP captures this difference
    """
    
    @staticmethod
    def calculate_edwards_trimp(duration_min: float, avg_hr: int, max_hr: int) -> Tuple[Optional[float], int]:
        """
        Edwards (1993) TRIMP - Zone-based method.
        
        Zones:
        1 (50-60% HRmax): 1×
        2 (60-70% HRmax): 2×
        3 (70-80% HRmax): 3×
        4 (80-90% HRmax): 4×
        5 (90-100% HRmax): 5×
        
        TRIMP = duration × zone_multiplier
        
        Args:
            duration_min: Session duration in minutes
            avg_hr: Average heart rate
            max_hr: Maximum heart rate
        
        Returns:
            (trimp_value, zone_multiplier)
        """
        if not max_hr or max_hr < 100:  # Physiologically impossible below 100 bpm
            return None, 0
        
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
    def calculate_banister_trimp(
        duration_min: float,
        avg_hr: int,
        resting_hr: int,
        max_hr: int,
        gender: str = 'male'
    ) -> Optional[float]:
        """
        Banister (1975) TRIMP - Original exponential method.
        
        More complex but more accurate.
        Uses exponential weighting for intensity.
        
        Args:
            duration_min: Session duration
            avg_hr: Average heart rate
            resting_hr: Resting heart rate
            max_hr: Maximum heart rate
            gender: 'male' or 'female' (affects exponent)
        
        Returns:
            TRIMP value
        """
        if not max_hr or max_hr < 100 or max_hr <= resting_hr:
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
    def weekly_trimp_analysis(weekly_trimp: float, baseline_trimp: float) -> Tuple[str, str]:
        """
        Compare weekly TRIMP to athlete's baseline.
        
        Based on Manzi et al. (2009).
        
        Args:
            weekly_trimp: This week's total TRIMP
            baseline_trimp: Athlete's normal weekly TRIMP
        
        Returns:
            (message, risk_level)
        """
        if baseline_trimp == 0:
            return "Need baseline TRIMP value", "UNKNOWN"
        
        percent_change = ((weekly_trimp - baseline_trimp) / baseline_trimp) * 100
        
        if percent_change > 50:
            return "🛑 DANGEROUS SPIKE: Reduce >30%", "CRITICAL"
        elif percent_change > 30:
            return "⚠️ SPIKE: High injury/illness risk", "HIGH_RISK"
        elif percent_change > 15:
            return "⚠️ HIGH: Monitor fatigue closely", "ELEVATED"
        elif -10 <= percent_change <= 15:
            return "✅ OPTIMAL PROGRESSION", "SAFE"
        elif -25 <= percent_change < -10:
            return "➡️ DELOAD WEEK (planned recovery)", "RECOVERY"
        else:
            return "⚠️ SEVERE DELOAD (risk detraining)", "LOW"
    
    @staticmethod
    def calculate_zone_time_trimp(zone_times: list, zone_multipliers: list = [1, 2, 3, 4, 5]) -> float:
        """
        Calculate TRIMP from time in each zone.
        
        Args:
            zone_times: List of minutes in each zone [z1, z2, z3, z4, z5]
            zone_multipliers: Multipliers for each zone (default Edwards)
        
        Returns:
            Total TRIMP
        """
        if len(zone_times) != len(zone_multipliers):
            return 0.0
        
        trimp = sum(time * mult for time, mult in zip(zone_times, zone_multipliers))
        return round(trimp, 1)

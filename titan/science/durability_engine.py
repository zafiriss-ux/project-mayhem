"""
Durability Engine - Performance Maintenance Under Fatigue

Scientific Basis:
- Maunder, E. et al. (2021). Sports Med, 51, 1619-1628.
- Spragg, J. et al. (2023). Med Sci Sports Exerc, 55(12), 2241-2250.
- Clark et al. (2019). "Durability: A new dimension of fitness"

Key Insight:
Traditional metrics (VO2max, FTP, LT) are measured FRESH.
But races are won by those who maintain performance when FATIGUED.
"""

from typing import List, Tuple, Optional


class DurabilityEngine:
    """
    Durability = How well you maintain performance when fatigued.
    
    The "new frontier" in endurance science - measuring performance
    degradation over long efforts.
    """

    @staticmethod
    def assess_pace_durability(
        km_splits: List[float],
        target_pace_sec: float
    ) -> Tuple[Optional[float], str, Optional[str]]:
        """
        Analyze pace decay across a long run.
        
        Args:
            km_splits: List of km split times (seconds)
            target_pace_sec: Target pace per km
        
        Returns:
            Tuple of (decay_percentage, status, recommendation)
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
            status = "✓ NEGATIVE SPLIT (exceptional durability)"
            recommendation = "Elite-level durability - maintain training"
        elif pace_decay_pct < 2:
            status = "✓ EXCELLENT durability (<2% fade)"
            recommendation = "Strong durability - ready for long races"
        elif pace_decay_pct < 5:
            status = "✓ GOOD durability (<5% fade)"
            recommendation = "Solid - acceptable for most races"
        elif pace_decay_pct < 8:
            status = "→ MODERATE fade (<8%)"
            recommendation = "Work on aerobic base & long runs"
        else:
            status = "⚠️ POOR durability (>8% fade)"
            recommendation = "Priority: Build aerobic base, add volume"

        return round(pace_decay_pct, 1), status, recommendation

    @staticmethod
    def calculate_durability_index(
        fresh_performance: float,
        fatigued_performance: float
    ) -> Tuple[Optional[float], str, str]:
        """
        Durability Index = (Fresh Performance / Fatigued Performance) × 100.
        
        Higher = better durability
        
        Example:
        - Fresh 5K: 19:00 (3:48/km = 228 sec)
        - After 25K: 5K @ 20:00 (4:00/km = 240 sec)
        - DI = (228 / 240) × 100 = 95%
        
        Args:
            fresh_performance: Time in seconds (shorter = better)
            fatigued_performance: Time in seconds (shorter = better)
            
        Returns:
            Tuple of (durability_index, status, tier)
        """
        if fresh_performance == 0 or fatigued_performance == 0:
            return None, "Invalid performance data", "UNKNOWN"

        di = (fresh_performance / fatigued_performance) * 100

        if di >= 98:
            status = "✓ ELITE durability (98%+)"
            tier = "WORLD CLASS"
        elif di >= 95:
            status = "✓ EXCELLENT durability (95-98%)"
            tier = "ELITE"
        elif di >= 90:
            status = "✓ GOOD durability (90-95%)"
            tier = "COMPETITIVE"
        elif di >= 85:
            status = "→ MODERATE durability (85-90%)"
            tier = "DEVELOPING"
        else:
            status = "⚠️ NEEDS IMPROVEMENT (<85%)"
            tier = "NOVICE"

        return round(di, 1), status, tier

    @staticmethod
    def durability_training_protocol(current_di: float) -> List[str]:
        """
        Training recommendations based on Maunder et al. (2021).
        
        Args:
            current_di: Current durability index (%)
            
        Returns:
            List of training recommendations
        """
        protocols = []

        if current_di < 88:
            protocols = [
                "⚠️ PRIORITY 1: Build aerobic base (80% of runs easy)",
                "Add weekly long run (90-120 min minimum)",
                "Include 'depleted state' runs (morning fasted, 60-90 min)",
                "Progressive long runs: Start easy, finish at tempo",
                "Back-to-back quality: Saturday tempo + Sunday long",
                "Reduce intervals temporarily - focus on volume"
            ]
        elif current_di < 93:
            protocols = [
                "Maintain weekly long run (2h+)",
                "Add 'fatigued intervals': Easy run → then intervals",
                "Monthly: Tempo after easy mileage (durability stimulus)",
                "One long run per month: Progressive with Hammer finish"
            ]
        elif current_di < 96:
            protocols = [
                "✓ Durability strong - maintain current approach",
                "Occasional durability check: Long run with fast finish",
                "Focus can shift to speed/power work"
            ]
        else:
            protocols = [
                "✓ ELITE durability maintained",
                "No specific durability work needed",
                "Use this as competitive advantage in long races"
            ]

        return protocols

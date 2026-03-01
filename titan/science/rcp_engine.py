"""RCP Engine - Respiratory Compensation Point Analysis"""
from typing import List, Tuple, Optional, Dict

class RCPEngine:
    """
    Respiratory Compensation Point - More precise than LTHR.
    
    Scientific Basis:
    - Meyer, T. et al. (2005). Int J Sports Med, 26(S1), S38-S48
    - Luca, A. et al. (2000). Med Sci Sports Exerc, 32(10), 1777-1782
    - Wasserman, K. et al. (1986). Original RCP concept
    
    RCP = Point where lactate "explodes"
    More reliable than LT2/LTHR for threshold work
    """

    @staticmethod
    def estimate_rcp_from_progressive_test(
        pace_segments_sec: List[float],
        hr_segments: List[int],
        rpe_segments: List[float]
    ) -> Tuple[Optional[int], Optional[float], Optional[float], str]:
        """
        Detect RCP from progressive field test.
        
        Field Test Protocol:
        - 5 min @ easy
        - 5 min @ moderate
        - 5 min @ tempo
        - 5 min @ threshold
        - Look for HR:Pace ratio inflection
        
        Args:
            pace_segments_sec: Avg pace/km for each segment (seconds)
            hr_segments: Avg HR for each segment
            rpe_segments: RPE for each segment
        
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
    def rcp_training_zones(rcp_hr: int, max_hr: int) -> Dict[str, any]:
        """
        Training zones based on RCP (Luca et al. 2000).
        
        Zone 1: Below VT1 (easy aerobic)
        Zone 2: VT1 to RCP (tempo/threshold)
        Zone 3: Above RCP (VO2max/anaerobic)
        
        Args:
            rcp_hr: Respiratory Compensation Point HR
            max_hr: Maximum heart rate
        
        Returns:
            Dictionary with zone definitions
        """
        vt1_hr = rcp_hr * 0.85  # Approximate VT1

        zones = {
            "Zone 1 (Easy)": f"< {int(vt1_hr)} HR (< 85% RCP)",
            "Zone 2 (Threshold)": f"{int(vt1_hr)}-{int(rcp_hr)} HR (85-100% RCP)",
            "Zone 3 (VO2max)": f"> {int(rcp_hr)} HR (> RCP)",
            "RCP_HR": rcp_hr,
            "VT1_HR": int(vt1_hr),
            "Max_HR": max_hr
        }

        return zones

    @staticmethod
    def calculate_rcp_training_zones(rcp_hr: int, max_hr: int) -> Dict[str, Tuple[int, int]]:
        """
        Calculate precise HR zones based on RCP.
        
        Returns dict with (low, high) HR for each zone.
        """
        vt1_hr = int(rcp_hr * 0.85)

        return {
            "zone_1_easy": (0, vt1_hr),
            "zone_2_threshold": (vt1_hr, rcp_hr),
            "zone_3_vo2max": (rcp_hr, max_hr),
            "rcp_hr": rcp_hr,
            "vt1_hr": vt1_hr
        }

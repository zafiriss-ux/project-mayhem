"""
Critical Speed & D' Engine

Models endurance capacity and time to exhaustion.
"""

from typing import List, Tuple, Optional


class CriticalSpeedEngine:
    """
    Critical Speed (CS) and D' (D-prime) modeling.
    
    CS = Maximum sustainable speed indefinitely
    D' = Finite work capacity above CS
    
    Used to predict time to exhaustion at any pace.
    """
    
    @staticmethod
    def estimate_cs_and_dprime(
        perfs: List[Tuple[float, float]]
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Estimate CS and D' from multiple performances.
        
        Uses linear regression on distance-time data.
        
        Args:
            perfs: List of (distance_meters, time_seconds) tuples
                   Example: [(3000, 720), (5000, 1260), (10000, 2700)]
        
        Returns:
            Tuple of (critical_speed_m_per_s, d_prime_meters) or (None, None)
            
        Example:
            >>> perfs = [(3000, 720), (5000, 1260), (10000, 2700)]
            >>> cs, dprime = CriticalSpeedEngine.estimate_cs_and_dprime(perfs)
            >>> print(f"CS: {cs:.2f} m/s, D': {dprime:.0f} m")
        """
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
        
        cs = a  # Critical Speed (m/s)
        d_prime = b  # D' (meters)
        
        return cs, d_prime
    
    @staticmethod
    def time_to_exhaustion_at_pace(
        cs_m_per_s: Optional[float],
        d_prime_m: Optional[float],
        pace_sec_per_km: float
    ) -> Optional[float]:
        """
        Predict time to exhaustion at a given pace.
        
        Formula: t = D' / (v - CS)
        where v = pace in m/s
        
        Args:
            cs_m_per_s: Critical speed in m/s
            d_prime_m: D' in meters
            pace_sec_per_km: Target pace in seconds per km
            
        Returns:
            Time to exhaustion in seconds, or None if pace is sustainable
        """
        if cs_m_per_s is None or d_prime_m is None:
            return None
        if pace_sec_per_km <= 0:
            return None
        
        v = 1000.0 / pace_sec_per_km  # Convert to m/s
        
        if v <= cs_m_per_s:
            return None  # Pace is at or below CS (sustainable)
        
        t = d_prime_m / (v - cs_m_per_s)
        return t

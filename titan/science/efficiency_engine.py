"""
Efficiency Factor Engine - Aerobic Fitness Proxy

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



MODULE_VERSION = "1.0.0"

class EfficiencyEngine:
    """
    Efficiency Factor = Aerobic fitness proxy.

    Tracks the relationship between speed and heart rate to monitor
    aerobic development over time.
    """

    def __init__(self):
        """Initialize efficiency tracking."""
        self.ef_history: list[tuple[str, float]] = []

    @staticmethod
    def calculate_efficiency_factor(avg_pace_sec_per_km: float, avg_hr: float) -> float | None:
        """
        EF = speed (m/s) / HR.

        Example:
        5:00/km = 3.33 m/s @ 150 HR
        EF = 3.33 / 150 = 0.0222

        Higher = more efficient

        Args:
            avg_pace_sec_per_km: Average pace in seconds per kilometer
            avg_hr: Average heart rate

        Returns:
            Efficiency factor value
        """
        if avg_hr == 0:
            return None

        speed_m_per_s = 1000.0 / avg_pace_sec_per_km
        ef = speed_m_per_s / avg_hr

        return round(ef, 5)

    @staticmethod
    def calculate_decoupling(
        first_half_pace: float, first_half_hr: float, second_half_pace: float, second_half_hr: float
    ) -> tuple[float | None, str]:
        """
        Decoupling = (EF_second - EF_first) / EF_first × 100.

        Negative = worsening efficiency (normal for long runs)

        Interpretation (Friel 2009):
        <5%: Excellent aerobic fitness
        5-10%: Moderate drift (acceptable)
        >10%: Poor aerobic base or nutritional issue

        Args:
            first_half_pace: First half average pace (sec/km)
            first_half_hr: First half average HR
            second_half_pace: Second half average pace (sec/km)
            second_half_hr: Second half average HR

        Returns:
            Tuple of (decoupling_percentage, status_interpretation)
        """
        ef_first = EfficiencyEngine.calculate_efficiency_factor(first_half_pace, first_half_hr)
        ef_second = EfficiencyEngine.calculate_efficiency_factor(second_half_pace, second_half_hr)

        if ef_first is None or ef_second is None or ef_first == 0:
            return None, "Invalid data"

        decoupling_pct = ((ef_second - ef_first) / ef_first) * 100

        if abs(decoupling_pct) < 3:
            status = "✓ ELITE aerobic fitness (<3% decoupling)"
        elif abs(decoupling_pct) < 5:
            status = "✓ EXCELLENT aerobic fitness (<5%)"
        elif abs(decoupling_pct) < 10:
            status = "→ MODERATE drift (<10% - acceptable for long runs)"
        else:
            status = "⚠️ HIGH decoupling (>10% - improve base or refuel)"

        return round(decoupling_pct, 1), status

    def add_ef_measurement(self, date: str, ef_value: float) -> None:
        """
        Log EF for trend tracking.

        Args:
            date: Measurement date
            ef_value: Efficiency factor value
        """
        self.ef_history.append((date, ef_value))

    def analyze_ef_trend(self, weeks: int = 3) -> str:
        """
        Track EF improvement over time.

        Rising EF = improving aerobic fitness at same HR

        Args:
            weeks: Number of weeks to analyze

        Returns:
            Trend analysis string
        """
        if len(self.ef_history) < weeks * 2:
            return "Need more data for trend analysis"

        days_per_week = 7
        recent_period = weeks * days_per_week

        recent = [ef for _, ef in self.ef_history[-recent_period:]]
        previous = [ef for _, ef in self.ef_history[-(recent_period * 2) : -recent_period]]

        if not previous:
            return "Need historical data"

        recent_avg = sum(recent) / len(recent)
        previous_avg = sum(previous) / len(previous)

        improvement_pct = ((recent_avg - previous_avg) / previous_avg) * 100

        if improvement_pct > 3:
            return f"✓ IMPROVING: EF up {improvement_pct:.1f}% (aerobic gains)"
        elif improvement_pct < -3:
            return f"⚠️ DECLINING: EF down {improvement_pct:.1f}% (check fatigue/volume)"
        else:
            return f"→ STABLE: EF change {improvement_pct:.1f}%"

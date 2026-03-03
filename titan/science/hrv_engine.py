"""
HRV-Guided Training Engine

Adaptive training recommendations based on Heart Rate Variability analysis.

Scientific Basis:
- Kiviniemi, A.M. et al. (2007). Eur J Appl Physiol, 101(6), 743-751.
- Plews, D.J. et al. (2013). Int J Sports Physiol Perform, 8(5), 512-521.
- Vesterinen, V. et al. (2016). Med Sci Sports Exerc, 48(7), 1347-1354.

Key Findings:
- HRV-guided training: +8.3% VO2max vs +5.6% predefined training
- Fewer overtraining symptoms
- Better psychological adherence
"""

import math
from typing import List, Optional, Tuple


class HRVGuidedEngine:
    """
    Adaptive training based on Heart Rate Variability.

    Protocol (Kiviniemi):
    - HRV ≥ baseline: Proceed with planned intensity
    - HRV < baseline: Downgrade to easy/rest

    Advanced (Plews - elite athletes):
    - HRV < baseline - 1 SD: Modify session
    - HRV < baseline - 2 SD: Force rest
    """

    def __init__(self, baseline_days: int = 7):
        """Initialize HRV engine."""
        self.hrv_log: list[tuple[str, float]] = []  # (date, rmssd_value)
        self.baseline_days = baseline_days

    def add_hrv_measurement(self, measurement_date: str, rmssd: float) -> None:
        """Add morning HRV measurement (rMSSD in ms)."""
        self.hrv_log.append((measurement_date, rmssd))

    def calculate_baseline(self, days: int = 7) -> tuple[float | None, float | None]:
        """Calculate rolling baseline (mean ± SD)."""
        if len(self.hrv_log) < days:
            return None, None

        recent = [hrv for _, hrv in self.hrv_log[-days:]]
        baseline = sum(recent) / len(recent)
        variance = sum((x - baseline) ** 2 for x in recent) / len(recent)
        std_dev = variance**0.5

        return baseline, std_dev

    def get_training_recommendation(
        self, today_hrv: float, planned_session: str
    ) -> tuple[str, str, str]:
        """Apply HRV-guided decision rules."""
        baseline_result = self.calculate_baseline(self.baseline_days)

        if baseline_result[0] is None:
            return planned_session, "Insufficient HRV data - proceed with plan", "LOW"

        baseline, std_dev = baseline_result
        threshold_critical = baseline - (2 * std_dev)
        threshold_caution = baseline - std_dev

        if today_hrv < threshold_critical:
            return "REST", f"⚠️ HRV CRITICAL: {today_hrv:.1f} < {threshold_critical:.1f}", "HIGH"
        elif today_hrv < threshold_caution:
            if planned_session in ["INTERVALS", "TEMPO", "PROGRESSIVE", "HAMMER"]:
                return "EASY", f"⚠️ HRV LOW: {today_hrv:.1f} → Downgrade", "HIGH"
            else:
                return planned_session, "HRV slightly low but easy session OK", "MEDIUM"
        elif today_hrv >= baseline:
            return planned_session, f"✅ HRV NORMAL: {today_hrv:.1f} → Proceed", "HIGH"
        else:
            return planned_session, f"HRV acceptable: {today_hrv:.1f}", "MEDIUM"

    @staticmethod
    def calculate_rmssd_from_rr_intervals(rr_intervals_ms: list[float]) -> float | None:
        """Calculate rMSSD from RR intervals."""
        if len(rr_intervals_ms) < 2:
            return None
        diffs_squared = [
            (rr_intervals_ms[i + 1] - rr_intervals_ms[i]) ** 2
            for i in range(len(rr_intervals_ms) - 1)
        ]
        return round((sum(diffs_squared) / len(diffs_squared)) ** 0.5, 1)

    def get_hrv_summary(self) -> dict:
        """
        Return a summary dict consumed by DailyCoach, WeeklyPlanGenerator, etc.

        Keys:
            latest_hrv  – most recent rMSSD value (0 if no data)
            baseline    – rolling 7-day mean (0 if insufficient data)
            std_dev     – rolling 7-day SD  (0 if insufficient data)
            trend       – human-readable trend string
            data_points – number of measurements loaded
        """
        baseline, std_dev = self.calculate_baseline(self.baseline_days)
        latest_hrv = self.hrv_log[-1][1] if self.hrv_log else 0.0
        return {
            "latest_hrv": round(latest_hrv, 1),
            "baseline": round(baseline, 1) if baseline is not None else 0.0,
            "std_dev": round(std_dev, 1) if std_dev is not None else 0.0,
            "trend": self.get_trend_analysis(),
            "data_points": len(self.hrv_log),
        }

    def get_latest_hrv(self) -> float:
        """Return most recent rMSSD value (0.0 if no data)."""
        return round(self.hrv_log[-1][1], 1) if self.hrv_log else 0.0

    def calculate_ln_rmssd_deviation(self, short_days: int = 7, long_days: int = 28) -> float:
        """
        Normalised ln(rMSSD) deviation: short-term baseline vs long-term.

        Converts rMSSD to natural-log scale before averaging, as recommended
        by Plews et al. (2013) — ln-transform stabilises variance across
        fitness levels and makes deviations scale-independent.

        Returns:
            Float in [-1.0, +1.0].
            Positive = short-term HRV above long-term baseline (well-recovered).
            Typical physiological deviation ≈ ±0.3 ln-units.

        Returns 0.0 if insufficient data for either window.
        """
        if not self.hrv_log:
            return 0.0
        safe_log = [math.log(r) for _, r in self.hrv_log if r > 0]
        if not safe_log:
            return 0.0
        recent_log = safe_log[-short_days:]
        long_log = safe_log[-long_days:]
        if not recent_log or not long_log:
            return 0.0
        mean_short = sum(recent_log) / len(recent_log)
        mean_long = sum(long_log) / len(long_log)
        # Normalise: ±0.3 ln-units = ±1.0 (saturates beyond that)
        return round(max(-1.0, min(1.0, (mean_short - mean_long) / 0.3)), 3)

    def get_trend_analysis(self) -> str:
        """Analyze HRV trend over time."""
        if len(self.hrv_log) < 14:
            return "Need 14+ days for trend analysis"
        recent_avg = sum(hrv for _, hrv in self.hrv_log[-7:]) / 7
        previous_avg = sum(hrv for _, hrv in self.hrv_log[-14:-7]) / 7
        if previous_avg == 0:
            return "➡️ STABLE: HRV baseline zero"
        change_pct = ((recent_avg - previous_avg) / previous_avg) * 100

        if change_pct > 5:
            return f"📈 IMPROVING: HRV up {change_pct:.1f}%"
        elif change_pct < -5:
            return f"📉 DECLINING: HRV down {change_pct:.1f}%"
        else:
            return f"➡️ STABLE: HRV change {change_pct:.1f}%"

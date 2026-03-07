"""Biomechanics Analysis - Cadence, Stride, Form"""



MODULE_VERSION = "1.0.0"

class BiomechanicsAnalysis:
    """Running biomechanics optimization"""

    @staticmethod
    def optimal_cadence(height_cm: int) -> tuple[int, int]:
        """
        Optimal cadence range based on height.

        General rule: Taller = slightly lower cadence
        Target: 170-180 spm for most runners
        """
        if height_cm >= 185:
            return (165, 175)
        elif height_cm >= 175:
            return (170, 180)
        else:
            return (175, 185)

    @staticmethod
    def stride_length(speed_m_s: float, cadence_spm: int) -> float:
        """
        Calculate stride length from speed and cadence.

        Formula: stride_length = (speed * 60) / cadence
        """
        if cadence_spm == 0:
            return 0.0
        return round((speed_m_s * 60) / cadence_spm, 2)

    @staticmethod
    def analyze_form(cadence: int, vert_osc: float, gct: float) -> tuple[int, str, list[str]]:
        """
        Analyze running form quality.

        Args:
            cadence: Steps per minute
            vert_osc: Vertical oscillation in cm
            gct: Ground contact time in ms

        Returns:
            (score, status, issues)
        """
        score = 100
        issues = []

        # Cadence analysis
        if cadence < 160:
            score -= 15
            issues.append("Low cadence (increase turnover)")
        elif cadence > 195:
            score -= 10
            issues.append("Very high cadence (may be inefficient)")

        # Vertical oscillation
        if vert_osc > 12:
            score -= 15
            issues.append("High bounce (reduce vertical movement)")
        elif vert_osc < 6:
            score -= 5
            issues.append("Very low bounce (check form)")

        # Ground contact time
        if gct > 280:
            score -= 10
            issues.append("Long contact (improve leg stiffness)")
        elif gct < 180:
            score -= 5
            issues.append("Very short contact (may indicate overstriding)")

        # Status
        if score >= 80:
            status = "✅ EXCELLENT"
        elif score >= 70:
            status = "👍 GOOD"
        elif score >= 60:
            status = "⚠️ FAIR"
        else:
            status = "🛑 NEEDS WORK"

        return score, status, issues

    @staticmethod
    def form_efficiency_score(cadence: int, vert_osc: float, gct: float) -> float:
        """
        Calculate overall form efficiency (0-1 scale).

        Higher = more efficient
        """
        score, _, _ = BiomechanicsAnalysis.analyze_form(cadence, vert_osc, gct)
        return score / 100.0

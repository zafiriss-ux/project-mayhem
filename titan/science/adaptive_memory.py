"""
Adaptive Memory - Learning System for Training Patterns

Tracks training history to detect patterns and adaptations.
"""

from typing import List, Optional
from datetime import datetime


class AdaptiveMemory:
    """
    Adaptive learning system for training patterns.
    
    Tracks session history, monotony, supercompensation windows,
    and mechanical load risk.
    """

    def __init__(self):
        """Initialize adaptive memory system."""
        self.session_history: List[dict] = []
        self.readiness_avg_14d: float = 85
        self.monotony_index: float = 1.2
        self.supercomp_status: str = "BASELINE"
        self.adaptive_pace_factor: float = 1.00
        self.last_quality_sessions: List[datetime] = []
        self.last_3d_soreness: List[float] = []

    def log_session(
        self,
        date: datetime,
        session_type: str,
        load: float,
        rpe: float,
        drift: float,
        success_flag: bool,
        soreness: Optional[float] = None
    ) -> None:
        """
        Log a training session.
        
        Args:
            date: Session date
            session_type: Type (e.g., "TEMPO", "INTERVALS", "EASY")
            load: Training load value
            rpe: Rating of Perceived Exertion
            drift: HR drift percentage
            success_flag: Whether session objectives were met
            soreness: Optional soreness level (0-10)
        """
        self.session_history.append({
            "date": date,
            "type": session_type,
            "load": load,
            "rpe": rpe,
            "drift": drift,
            "success": success_flag
        })

        if session_type in ["TEMPO", "INTERVALS", "LONG_RUN", "PROGRESSIVE"]:
            self.last_quality_sessions.append(date)
            self.last_quality_sessions = self.last_quality_sessions[-5:]

        if soreness is not None:
            self.last_3d_soreness.append(soreness)
            self.last_3d_soreness = self.last_3d_soreness[-3:]

    def calculate_neural_adaptation(
        self,
        target_pace_sec: float,
        actual_pace_sec: float,
        avg_hr: float,
        threshold_hr: float
    ) -> str:
        """
        Detect neural adaptation (running faster at same HR).
        
        Args:
            target_pace_sec: Target pace in sec/km
            actual_pace_sec: Actual pace in sec/km
            avg_hr: Average heart rate
            threshold_hr: Threshold heart rate
            
        Returns:
            Adaptation status message
        """
        if actual_pace_sec < target_pace_sec and avg_hr <= threshold_hr:
            improvement = target_pace_sec - actual_pace_sec
            self.adaptive_pace_factor *= 0.995
            return (
                f"✓ NEURAL GAIN: +{improvement:.1f}s/km faster. "
                f"Pace factor → {self.adaptive_pace_factor:.3f}"
            )
        return "STABLE: Neural adaptation maintained."

    def check_monotony(self, load_7d: float, std_dev_load: float) -> str:
        """
        Check for training monotony (injury risk factor).
        
        Monotony = Mean Load / Standard Deviation
        High monotony = same workouts → injury risk
        
        Args:
            load_7d: 7-day average load
            std_dev_load: Standard deviation of 7-day loads
            
        Returns:
            Monotony status message
        """
        if std_dev_load == 0:
            return "⚠️ MONOTONY UNKNOWN (No variance)."

        monotony = load_7d / std_dev_load
        self.monotony_index = monotony

        if monotony > 2.5:
            return "⚠️ DANGER: Very high monotony. Force variation / rest."
        if monotony > 2.0:
            return "⚠️ RISK: High monotony. Add Fartlek or Rest."
        if monotony > 1.5:
            return "→ WATCH: Moderate monotony."
        return "✓ LOAD VARIATION: Healthy."

    def supercompensation_window(self, last_hard_session_hours: float) -> str:
        """
        Identify supercompensation window after hard training.
        
        Args:
            last_hard_session_hours: Hours since last hard session
            
        Returns:
            Supercompensation status
        """
        if 24 <= last_hard_session_hours <= 48:
            self.supercomp_status = "RECOVERY"
            return "→ RECOVERY WINDOW (Protein Synthesis active)"
        if 48 < last_hard_session_hours <= 72:
            self.supercomp_status = "PEAK"
            return "✓ SUPER-COMPENSATION PEAK (Go Hard Now)"
        self.supercomp_status = "BASELINE"
        return "→ BASELINE (Normal Training)"

    def session_density_index(self, now_dt: datetime) -> str:
        """
        Check spacing of quality sessions.
        
        Args:
            now_dt: Current datetime
            
        Returns:
            Session density status
        """
        if len(self.last_quality_sessions) < 2:
            return "SDI: Not enough data."

        last = self.last_quality_sessions[-1]
        delta_h = (now_dt - last).total_seconds() / 3600.0

        if delta_h < 24:
            return "⚠️ SDI: <24h since last quality. Force EASY."
        if delta_h < 36:
            return "⚠️ SDI: <36h. Downgrade intensity."
        if delta_h < 48:
            return "→ SDI: <48h. Caution."
        return "✓ SDI: Safe spacing."

    def mechanical_load_risk(
        self,
        easy_pace_today_sec: float,
        easy_pace_baseline_sec: float
    ) -> str:
        """
        Proxy for mechanical load injury risk.
        
        Uses soreness trend and easy pace degradation.
        
        Args:
            easy_pace_today_sec: Today's easy pace (sec/km)
            easy_pace_baseline_sec: Baseline easy pace (sec/km)
            
        Returns:
            Mechanical load risk status
        """
        risk_flags = []

        if len(self.last_3d_soreness) == 3 and sum(self.last_3d_soreness) / 3.0 >= 5:
            risk_flags.append("HIGH_SORENESS_TREND")

        if easy_pace_today_sec > easy_pace_baseline_sec * 1.08:
            risk_flags.append("EASY_PACE_DROP")

        if not risk_flags:
            return "MECH LOAD: OK"

        if "HIGH_SORENESS_TREND" in risk_flags and "EASY_PACE_DROP" in risk_flags:
            return "⚠️ MECH LOAD: HIGH RISK (Consider Rest / Downgrade)."

        return "→ MECH LOAD: Watch (Adjust volume/intensity)."

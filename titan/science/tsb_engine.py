"""TSB (Training Stress Balance) Engine - Performance Management"""

from titan.config.thresholds import ATL_DECAY_DAYS, CTL_DECAY_DAYS

MODULE_VERSION = "1.0.0"

class TSBEngine:
    """Training Stress Balance: CTL - ATL = Form"""

    def __init__(self):
        self.ctl, self.atl, self.tsb = 0.0, 0.0, 0.0
        self.daily_loads: list[tuple[str, float]] = []

    def add_daily_load(self, date: str, load: float) -> None:
        self.daily_loads.append((date, load))

    def calculate_ctl(self, decay: int | None = None) -> float | None:
        """Chronic Training Load (42-day EMA)"""
        if not self.daily_loads:
            return None
        decay_days = CTL_DECAY_DAYS if decay is None else decay
        ctl, alpha = self.daily_loads[0][1], 2.0 / (decay_days + 1)
        for _, load in self.daily_loads[1:]:
            ctl = (load * alpha) + (ctl * (1 - alpha))
        self.ctl = ctl
        return round(ctl, 1)

    def calculate_atl(self, decay: int | None = None) -> float | None:
        """Acute Training Load (7-day EMA)"""
        if not self.daily_loads:
            return None
        decay_days = ATL_DECAY_DAYS if decay is None else decay
        atl, alpha = self.daily_loads[0][1], 2.0 / (decay_days + 1)
        for _, load in self.daily_loads[1:]:
            atl = (load * alpha) + (atl * (1 - alpha))
        self.atl = atl
        return round(atl, 1)

    def calculate_tsb(self) -> tuple[float | None, str]:
        """Training Stress Balance"""
        ctl, atl = self.calculate_ctl(), self.calculate_atl()
        if ctl is None or atl is None:
            return None, "INSUFFICIENT DATA"
        tsb = ctl - atl
        self.tsb = tsb

        if tsb > 25:
            status = "⚠️ SEVERE DETRAINING"
        elif tsb > 15:
            status = "⚠️ DETRAINING"
        elif 5 < tsb <= 15:
            status = "✅ FRESH"
        elif -10 <= tsb <= 5:
            status = "🎯 RACE FORM"
        elif -30 < tsb < -10:
            status = "💪 PRODUCTIVE OVERLOAD"
        elif -50 < tsb <= -30:
            status = "⚠️ FUNCTIONAL OVERREACH"
        else:
            status = "🛑 OVERTRAINED"
        return round(tsb, 1), status

    def get_tsb_status(self) -> dict:
        """Return named TSB payload for governance/context wiring."""
        tsb_value, status = self.calculate_tsb()
        return {"tsb_value": tsb_value, "status": status}

    def get_latest_tsb(self) -> float:
        """Return current TSB value (0.0 if insufficient data)."""
        val, _ = self.calculate_tsb()
        return val if val is not None else 0.0

    def predict_race_day_tsb(self, days: int, loads: list[float]) -> float | None:
        """Predict future TSB"""
        if not loads or days > len(loads):
            return None
        temp_ctl, temp_atl = self.ctl, self.atl
        for load in loads[:days]:
            atl_alpha = 2 / (ATL_DECAY_DAYS + 1)
            ctl_alpha = 2 / (CTL_DECAY_DAYS + 1)
            temp_atl = (load * atl_alpha) + (temp_atl * (1 - atl_alpha))
            temp_ctl = (load * ctl_alpha) + (temp_ctl * (1 - ctl_alpha))
        return round(temp_ctl - temp_atl, 1)

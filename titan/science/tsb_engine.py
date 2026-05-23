"""TSB (Training Stress Balance) Engine - Performance Management"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING

from titan.config.thresholds import ATL_DECAY_DAYS, CTL_DECAY_DAYS

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

MODULE_VERSION = "1.0.0"


def compute_ctl_atl_tsb(
    daily_loads: list[tuple[str, float]],
    ctl_decay_days: int = 42,
    atl_decay_days: int = 7,
    reference_date: date | None = None,
) -> tuple[float, float, float]:
    """
    Canonical Banister EMA kernel.

    Args:
        daily_loads: List of (date_str, load) tuples, sorted ASC by date.
            Each tuple is ONE day's total load (pre-aggregated by caller).
        ctl_decay_days: EMA time constant for fitness (default 42).
        atl_decay_days: EMA time constant for fatigue (default 7).
        reference_date: Cutoff for ATL window. Defaults to today.

    Returns:
        (ctl, atl, tsb) rounded to 1dp.

    Invariants enforced:
        - Empty stream → (0.0, 0.0, 0.0)
        - Loads must be pre-aggregated per day
        - ATL uses date window, not item count
    """
    if not daily_loads:
        return 0.0, 0.0, 0.0

    ref = reference_date or date.today()
    atl_cutoff = (ref - timedelta(days=atl_decay_days)).isoformat()

    ctl_k = 2.0 / (ctl_decay_days + 1)
    atl_k = 2.0 / (atl_decay_days + 1)

    ctl = 0.0
    atl = 0.0

    for date_str, load in daily_loads:
        ctl = load * ctl_k + ctl * (1 - ctl_k)
        if date_str >= atl_cutoff:
            atl = load * atl_k + atl * (1 - atl_k)

    tsb = ctl - atl
    return (
        round(ctl, 1),
        round(atl, 1),
        round(tsb, 1),
    )


def replay_tsb(
    db: DatabaseManager,
    athlete_id: str,
    as_of_date: date,
    ctl_decay_days: int = CTL_DECAY_DAYS,
    atl_decay_days: int = ATL_DECAY_DAYS,
) -> tuple[float, float, float]:
    """
    Deterministic replay: compute CTL/ATL/TSB as it would have been on
    `as_of_date` using only activity data up to that date.

    Pure function of (activity_stream, date). Used for audit, drift
    detection, and regression testing.

    Returns (ctl, atl, tsb).
    """
    loads = db.get_training_load_history(
        athlete_id=athlete_id,
        days=ctl_decay_days * 5,  # 5τ warmup window
    )
    loads_up_to = [
        (d, load) for d, load in loads
        if d <= as_of_date.isoformat()
    ]
    return compute_ctl_atl_tsb(
        daily_loads=loads_up_to,
        ctl_decay_days=ctl_decay_days,
        atl_decay_days=atl_decay_days,
        reference_date=as_of_date,
    )


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

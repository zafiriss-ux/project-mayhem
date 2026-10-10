"""TSB (Training Stress Balance) Engine - Performance Management"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from titan.config.thresholds import ATL_DECAY_DAYS, CTL_DECAY_DAYS

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

MODULE_VERSION = "1.1.0"


def _today() -> date:
    """Today in UTC, the date the morning routine uses."""
    return datetime.now(UTC).date()


# Days of load history the CTL needs: five time constants, so a start from 0 is
# forgotten (e^-5 < 1%). replay_tsb used this warm-up already (SV-08, D-051).
LOAD_HISTORY_DAYS = 5 * CTL_DECAY_DAYS


def daily_load_series(
    daily_loads: list[tuple[str, float]],
    end_date: date,
) -> list[tuple[str, float]]:
    """One (date, load) per calendar day, from the first load to *end_date*.

    Days without a session get load 0, so a rest day lowers CTL and ATL. Loads on
    the same day are added; loads after *end_date* are left out.
    """
    by_day: dict[str, float] = {}
    for date_str, load in daily_loads:
        day = str(date_str)[:10]
        by_day[day] = by_day.get(day, 0.0) + float(load)
    end = end_date.isoformat()
    days = sorted(d for d in by_day if d <= end)
    if not days:
        return []
    current = date.fromisoformat(days[0])
    series = []
    while current <= end_date:
        iso = current.isoformat()
        series.append((iso, by_day.get(iso, 0.0)))
        current += timedelta(days=1)
    return series


def compute_ctl_atl_tsb(
    daily_loads: list[tuple[str, float]],
    ctl_decay_days: int = CTL_DECAY_DAYS,
    atl_decay_days: int = ATL_DECAY_DAYS,
    reference_date: date | None = None,
) -> tuple[float, float, float]:
    """
    Canonical Banister EMA kernel (TrainingPeaks form, SV-08, D-051).

    CTLtoday = CTLyesterday + (loadtoday − CTLyesterday) / time constant, and the
    same for ATL, over every calendar day: a day without training has load 0.
    Source: TrainingPeaks help articles 204071884 (CTL) and 204071894 (ATL).

    Args:
        daily_loads: (date_str, load) tuples, in any order. Days may be missing
            (rest days) or repeated (two sessions); the kernel builds the daily series.
        ctl_decay_days: time constant for fitness (default 42).
        atl_decay_days: time constant for fatigue (default 7).
        reference_date: last day of the series. Defaults to today.

    Returns:
        (ctl, atl, tsb) rounded to 1dp. Both start from 0 on the first loaded day.

    Invariants enforced:
        - Empty stream → (0.0, 0.0, 0.0)
        - One value per calendar day, rest days as 0
    """
    series = daily_load_series(daily_loads, reference_date or _today())
    if not series:
        return 0.0, 0.0, 0.0

    ctl_k = 1.0 / ctl_decay_days
    atl_k = 1.0 / atl_decay_days

    ctl = 0.0
    atl = 0.0
    for _date_str, load in series:
        ctl += (load - ctl) * ctl_k
        atl += (load - atl) * atl_k

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
        days=ctl_decay_days * 5,  # 5τ warmup window (LOAD_HISTORY_DAYS)
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

    def _kernel(self, ctl_decay_days: int, atl_decay_days: int) -> tuple[float, float, float]:
        return compute_ctl_atl_tsb(
            self.daily_loads,
            ctl_decay_days=ctl_decay_days,
            atl_decay_days=atl_decay_days,
            reference_date=_today(),
        )

    def calculate_ctl(self, decay: int | None = None) -> float | None:
        """Chronic Training Load (42-day time constant, rest days count as 0)."""
        if not self.daily_loads:
            return None
        decay_days = CTL_DECAY_DAYS if decay is None else decay
        self.ctl = self._kernel(decay_days, ATL_DECAY_DAYS)[0]
        return self.ctl

    def calculate_atl(self, decay: int | None = None) -> float | None:
        """Acute Training Load (7-day time constant, rest days count as 0)."""
        if not self.daily_loads:
            return None
        decay_days = ATL_DECAY_DAYS if decay is None else decay
        self.atl = self._kernel(CTL_DECAY_DAYS, decay_days)[1]
        return self.atl

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
            temp_atl += (load - temp_atl) / ATL_DECAY_DAYS
            temp_ctl += (load - temp_ctl) / CTL_DECAY_DAYS
        return round(temp_ctl - temp_atl, 1)

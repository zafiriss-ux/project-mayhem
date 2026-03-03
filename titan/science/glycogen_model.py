"""
Glycogen Depletion and Refueling Models

v5.7 addition:
- GlycogenDebtAccumulator: stateful daily accumulator integrating TRIMP,
  time above LT2, D' expenditure, intra-workout carbs, and overnight
  resynthesis. Triggers Norwegian Recovery Window Protocol when debt >= 7.

Static classes (GlycogenModel, GlycogenEngine) preserved for backward
compatibility.

Scientific Basis:
- Burke, L.M. et al. (2011). J Sports Sci, 29(S1), S17-S27.
- Ivy, J.L. et al. (1988). J Appl Physiol, 65(6), 2018-2023.
  Post-exercise glycogen resynthesis rate: max window 0-2h, 7 mmol/kg/hr.
- Cheuvront, S.N. et al. (2010). J Strength Cond Res, 24(10), 2653-2665.
  Plasma volume / sodium guard for heat + duration.
"""

from typing import Dict, List, Optional, Tuple


class GlycogenModel:
    """Estimate glycogen cost and refueling needs"""

    @staticmethod
    def estimate_glycogen_depletion(duration_min: float, intensity_pct_vo2max: float) -> dict:
        """Estimate glycogen cost of session"""
        if intensity_pct_vo2max > 85:
            rate, desc = 2.5, "HIGH (intervals/race)"
        elif intensity_pct_vo2max > 75:
            rate, desc = 1.8, "MODERATE-HIGH (tempo)"
        elif intensity_pct_vo2max > 65:
            rate, desc = 1.2, "MODERATE (steady)"
        else:
            rate, desc = 0.8, "EASY (fat burning)"

        return {
            "glycogen_depleted_g": round(duration_min * rate, 0),
            "intensity_classification": desc,
            "depletion_rate": rate,
            "refuel_recommendation": "1.2-1.5 g carbs/kg within 2h",
        }

    @staticmethod
    def daily_carb_recommendation(weight_kg: float, training_load: str) -> dict:
        """Daily carb needs (Burke et al. 2011)"""
        recs = {
            "LIGHT": (3, 5, "Recovery days"),
            "MODERATE": (5, 7, "Base training"),
            "HIGH": (6, 10, "Normal load"),
            "VERY_HIGH": (8, 12, "Heavy blocks"),
        }
        low, high, ctx = recs.get(training_load, (5, 7, "Moderate"))
        return {
            "carbs_g_per_kg_low": low,
            "carbs_g_per_kg_high": high,
            "total_carbs_range": f"{int(low * weight_kg)}-{int(high * weight_kg)}g",
            "context": ctx,
        }


class GlycogenEngine:
    """Simple glycogen status checker (from original TITAN)"""

    @staticmethod
    def glycogen_flag(low_carb_day: bool, back_to_back_quality: bool, weight: float) -> tuple:
        """
        Glycogen availability check.

        Args:
            low_carb_day: Is this a low-carb day?
            back_to_back_quality: Quality sessions on consecutive days?
            weight: Athlete weight in kg

        Returns:
            (hammer_allowed, min_carbs, flags)
        """
        flags = []
        hammer_allowed = True
        min_carbs = None

        if low_carb_day:
            hammer_allowed = False
            flags.append("LOW_GLYCOGEN: Hammer forbidden today")

        if back_to_back_quality:
            min_carbs = int(7 * weight)
            flags.append(f"BACK-TO-BACK QUALITY: Carbs ≥ {min_carbs}g required")

        if not flags:
            flags.append("GLYCOGEN OK: Normal fueling rules")

        return hammer_allowed, min_carbs, flags


class GlycogenDebtAccumulator:
    """
    Stateful daily glycogen debt accumulator (0–10 score).

    Integrates:
      TRIMP              → training-impulse-derived glycogen burn
      time_above_lt2     → high-intensity burn above LT2 threshold
      dprime_fraction    → fraction of D' anaerobic reserve spent
      intra_carb_g       → in-workout carbohydrate intake (refueling offset)
      overnight          → resynthesis during sleep (Burke model)

    Score interpretation:
      0–3  GOOD     — adequate glycogen availability
      4–6  MODERATE — monitor; prioritize carbohydrate timing
      7–10 CRITICAL  — Norwegian Recovery Window Protocol triggered

    Usage:
        accumulator = GlycogenDebtAccumulator()
        accumulator.update(date, trimp=95, time_above_lt2_min=18,
                           dprime_fraction=0.4, intra_carb_g=40, weight_kg=70)
        accumulator.overnight_resynthesis(sleep_hours=8)
        protocol = accumulator.norwegian_protocol(weight_kg=70)
    """

    MAX_DEBT = 10.0

    def __init__(self) -> None:
        self.daily_debt: float = 0.0
        self.debt_history: list[tuple[str, float]] = []  # (date, debt_score)

    # ── Session Debt Update ──────────────────────────────────────────────────

    def update(
        self,
        date: str,
        trimp: float,
        time_above_lt2_min: float,
        dprime_fraction: float,
        intra_carb_g: float,
        weight_kg: float,
    ) -> float:
        """
        Update daily glycogen debt after a training session.

        Burn model:
          TRIMP cost      = trimp × 0.015
          LT2 cost        = minutes_above_LT2 × 0.08
          D' anaerobic    = dprime_fraction × 1.5
          Refuel offset   = (intra_carb_g / weight_kg) × 0.12

        Args:
            date:              ISO date string
            trimp:             Session TRIMP (Edwards or Banister)
            time_above_lt2_min: Minutes spent above LT2 threshold
            dprime_fraction:   Fraction of D' reserve spent (0.0–1.0)
            intra_carb_g:      Carbohydrates consumed during session (grams)
            weight_kg:         Athlete body weight

        Returns:
            Updated debt score (0–10).
        """
        trimp_cost = trimp * 0.015
        lt2_cost = time_above_lt2_min * 0.08
        dprime_cost = max(0.0, min(1.0, dprime_fraction)) * 1.5
        refuel_credit = (intra_carb_g / max(weight_kg, 1.0)) * 0.12

        net_burn = trimp_cost + lt2_cost + dprime_cost - refuel_credit
        self.daily_debt = min(self.MAX_DEBT, max(0.0, self.daily_debt + net_burn))
        self.debt_history.append((date, round(self.daily_debt, 2)))
        return round(self.daily_debt, 2)

    # ── Overnight Resynthesis ────────────────────────────────────────────────

    def overnight_resynthesis(
        self,
        sleep_hours: float = 7.5,
        carb_availability: str = "MODERATE",
    ) -> float:
        """
        Apply overnight glycogen resynthesis.

        Resynthesis rate scales with sleep duration and carbohydrate availability.
        Ivy et al. (1988): max rate 7 mmol/kg/hr requires adequate carb intake.

        Args:
            sleep_hours:       Hours of sleep (affects resynthesis window)
            carb_availability: 'HIGH' | 'MODERATE' | 'LOW'

        Returns:
            Updated debt score after overnight recovery.
        """
        av_mult = {"HIGH": 1.3, "MODERATE": 1.0, "LOW": 0.6}.get(carb_availability, 1.0)
        # Base: 0.8 debt-units recovered per 8h well-fueled sleep
        recovery = 0.8 * (sleep_hours / 8.0) * av_mult
        self.daily_debt = max(0.0, self.daily_debt - recovery)
        return round(self.daily_debt, 2)

    @property
    def status(self) -> str:
        """Human-readable debt level."""
        if self.daily_debt < 4:
            return "GOOD"
        if self.daily_debt < 7:
            return "MODERATE"
        return "CRITICAL"

    # ── Norwegian Recovery Window Protocol ──────────────────────────────────

    def norwegian_protocol(self, weight_kg: float) -> dict | None:
        """
        Trigger Norwegian Recovery Window Protocol when debt >= 7.

        Based on Ivy et al. (1988) maximal glycogen resynthesis window.
        Phase A (0–2h post-exercise): highest resynthesis rate.
        Phase B (2–6h): sustained fueling to fill remaining stores.

        Returns:
            Protocol dict if triggered, None if debt < 7.
        """
        if self.daily_debt < 7.0:
            return None
        return {
            "triggered": True,
            "debt_score": round(self.daily_debt, 1),
            "status": "CRITICAL",
            "phase_a": {
                "window": "0–2h post-exercise",
                "carbs_g_per_kg_hr": 1.1,
                "carbs_g_total": round(1.1 * weight_kg, 0),
                "protein_g_per_kg": 0.3,
                "protein_g_total": round(0.3 * weight_kg, 0),
                "rationale": "Ivy et al. — max resynthesis rate window",
            },
            "phase_b": {
                "window": "2–6h post-exercise",
                "carbs_g_per_kg_hr": 0.8,
                "carbs_g_total": round(0.8 * weight_kg * 4, 0),
                "rationale": "Sustained fueling to restore full stores",
            },
        }

    # ── Electrolyte Guard ────────────────────────────────────────────────────

    @staticmethod
    def get_electrolyte_guard_status(
        dew_point_c: float,
        duration_min: float,
        session_type: str,
    ) -> dict | None:
        """Named accessor for electrolyte guard status (no logic change)."""
        return GlycogenDebtAccumulator.electrolyte_guard(
            dew_point_c=dew_point_c,
            duration_min=duration_min,
            session_type=session_type,
        )

    @staticmethod
    def electrolyte_guard(
        dew_point_c: float,
        duration_min: float,
        session_type: str,
    ) -> dict | None:
        """
        Sodium / plasma-volume guard for hot-humid conditions.

        Trigger: dew point > 18°C AND duration > 60 min AND quality session.
        Cheuvront et al. (2010): plasma volume drop >3% impairs performance.

        Args:
            dew_point_c:  Dew point temperature in °C
            duration_min: Session duration in minutes
            session_type: Session type string

        Returns:
            Alert dict if triggered, None otherwise.
        """
        QUALITY = {"TEMPO", "INTERVALS", "LONG_RUN", "RACE", "HAMMER"}
        if dew_point_c <= 18.0 or duration_min <= 60 or session_type not in QUALITY:
            return None
        sweat_ml_hr = 800 + (dew_point_c - 18) * 40
        total_sweat = sweat_ml_hr * (duration_min / 60)
        sodium_mg = round(total_sweat * 0.75, 0)  # ~750 mg/L average sweat sodium
        return {
            "triggered": True,
            "reason": f"Dew point {dew_point_c:.0f}°C + {duration_min:.0f}min quality session",
            "sodium_mg": sodium_mg,
            "fluid_ml_per_hr": round(sweat_ml_hr, 0),
            "recommendation": (
                f"Pre-load 500 mL fluid; target {round(sodium_mg / 1000, 1)} g sodium "
                f"+ {round(sweat_ml_hr / 4, 0):.0f} mL/15 min during session"
            ),
        }

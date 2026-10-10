"""
Critical Speed & D' Engine

Models endurance capacity and time to exhaustion.

v5.7 additions:
- CriticalSpeedTracker: stateful EWMA-stabilized CS with archetype inference,
  thermal degradation, GAP correction, and calibration confidence scoring.
- Static helpers preserved for backward compatibility.

Scientific Basis:
- Monod, H. & Scherrer, J. (1965). Work capacity of a synergic muscular group.
- Jones, A.M. et al. (2010). J Appl Physiol, 108(2), 452-462.
- Bellenger, C.R. et al. (2016). Sports Med, 46(9), 1351-1366. (EWMA α=0.3)
- Minetti, A.E. et al. (2002). J Appl Physiol, 93(3), 1039-1046. (GAP model)
- Jones, A.M. & Doust, J.H. (1997). J Sports Sci, 15(6), 643-648. (thermal)
"""

from datetime import UTC, date, datetime

from titan.config.thresholds import ESI_MODERATE_MIN

MODULE_VERSION = "1.0.0"


class CriticalSpeedEngine:
    """
    Critical Speed (CS) and D' (D-prime) modeling.

    CS = Maximum sustainable speed indefinitely
    D' = Finite work capacity above CS

    Used to predict time to exhaustion at any pace.
    """

    @staticmethod
    def estimate_cs_and_dprime(
        perfs: list[tuple[float, float]],
    ) -> tuple[float | None, float | None]:
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
        sum_xy = sum(x * y for x, y in zip(xs, ys, strict=False))

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
        cs_m_per_s: float | None, d_prime_m: float | None, pace_sec_per_km: float
    ) -> float | None:
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
        if d_prime_m <= 0:
            return None

        v = 1000.0 / pace_sec_per_km  # Convert to m/s

        if v <= cs_m_per_s:
            return None  # Pace is at or below CS (sustainable)

        t = d_prime_m / (v - cs_m_per_s)
        return t


# Input guards for a manually entered time-trial (D-039). They reject typing
# mistakes; they are not governance thresholds. Evidence: HEURISTIC.
TRIAL_DISTANCE_RANGE_M = (400.0, 42195.0)  # a 400 m effort up to a marathon
TRIAL_TIME_RANGE_S = (60.0, 6 * 3600.0)    # one minute up to six hours
TRIAL_SPEED_RANGE_M_S = (1.5, 8.0)         # brisk walk; 8 m/s is above every 800 m+ world record


def _parse_trial_distance(raw: str) -> float:
    text = raw.strip().lower().replace(",", ".")
    factor = 1.0
    for suffix in ("km", "k"):
        if text.endswith(suffix):
            text, factor = text[: -len(suffix)], 1000.0
            break
    else:
        if text.endswith("m"):
            text = text[:-1]
    try:
        return float(text) * factor
    except ValueError:
        raise ValueError(f"Invalid distance: '{raw}'") from None


def _parse_trial_time(raw: str) -> float:
    parts = raw.strip().replace(",", ".").split(":")
    if len(parts) > 3:
        raise ValueError(f"Invalid time: '{raw}'")
    try:
        values = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"Invalid time: '{raw}'") from None
    if any(v < 0 for v in values) or any(v >= 60 for v in values[1:]):
        raise ValueError(f"Invalid time: '{raw}'")
    seconds = 0.0
    for v in values:
        seconds = seconds * 60 + v
    return seconds


def parse_time_trial(distance: str, time: str) -> tuple[float, float]:
    """Parse a manually entered time-trial into ``(distance_m, time_sec)``.

    *distance* is metres ("5000", "5000m") or kilometres ("5k", "5km", "5,0km").
    *time* is seconds ("1110"), "mm:ss" ("18:30") or "h:mm:ss" ("1:25:00").
    Raises ``ValueError`` with a readable message when the input is malformed
    or outside the ``TRIAL_*`` ranges.
    """
    distance_m = _parse_trial_distance(distance)
    time_sec = _parse_trial_time(time)
    lo, hi = TRIAL_DISTANCE_RANGE_M
    if not lo <= distance_m <= hi:
        raise ValueError(f"Distance out of range: {distance_m:g} m (valid: {lo:g}–{hi:g} m)")
    lo, hi = TRIAL_TIME_RANGE_S
    if not lo <= time_sec <= hi:
        raise ValueError(f"Time out of range: {time_sec:g} s (valid: {lo:g}–{hi:g} s)")
    speed = distance_m / time_sec
    lo, hi = TRIAL_SPEED_RANGE_M_S
    if not lo <= speed <= hi:
        raise ValueError(f"Average speed not plausible: {speed:.2f} m/s (valid: {lo:g}–{hi:g} m/s)")
    return distance_m, time_sec


def parse_trial_date(raw: str | None, today: date) -> str:
    """Return the trial date as ISO text; empty means *today*, a future date is rejected."""
    if raw is None or not raw.strip():
        return today.isoformat()
    try:
        day = date.fromisoformat(raw.strip())
    except ValueError:
        raise ValueError(f"Invalid date: '{raw}' (use YYYY-MM-DD)") from None
    if day > today:
        raise ValueError(f"Date is in the future: {day.isoformat()}")
    return day.isoformat()


class CriticalSpeedTracker:
    """
    Stateful, EWMA-stabilized Critical Speed tracker.

    Responsibilities:
    - Maintain a smoothed CS estimate across multiple calibration events
      (EWMA α=0.3 — Bellenger et al. recommendation)
    - Infer fiber-type archetype from D′/CS ratio
    - Apply thermal degradation for heat conditions
    - Track calibration confidence for governance

    Workflow (ADR-0058: obtain tracker via EngineRegistry.from_db()):
        cs, d_prime = CriticalSpeedEngine.estimate_cs_and_dprime(perfs)
        tracker.update(date, cs, d_prime)
        cs_safe = tracker.apply_thermal(temp_c=28)
    """

    EWMA_ALPHA = 0.3  # Bellenger et al. — balances responsiveness vs stability

    def __init__(self) -> None:
        self.cs_raw_history: list[tuple[str, float]] = []  # (date, cs_m_per_s)
        self.cs_smoothed: float | None = None
        self.d_prime: float | None = None
        self.archetype: str = "HYBRID"
        self.confidence: float = 0.0

    # ── Calibration Update ───────────────────────────────────────────────────

    def update(self, date: str, cs_raw: float, d_prime: float) -> None:
        """
        Ingest a new CS estimate from a time-trial or race.

        EWMA smoothing prevents single-session distortion from:
          wind, downhill gradient, heat, race-day arousal.
        """
        self.cs_raw_history.append((date, cs_raw))
        self.d_prime = d_prime
        if self.cs_smoothed is None:
            self.cs_smoothed = cs_raw
        else:
            self.cs_smoothed = self.EWMA_ALPHA * cs_raw + (1 - self.EWMA_ALPHA) * self.cs_smoothed
        self._update_archetype()
        self._update_confidence()

    # ── Archetype Inference ──────────────────────────────────────────────────

    def _update_archetype(self) -> None:
        """
        Infer fiber-type dominance from D′/CS ratio.

        High D′ relative to CS → large anaerobic reservoir → speed-dominant.
        Low D′                 → lean anaerobic reserve  → endurance-dominant.

        Thresholds based on Jones et al. (2010) elite-athlete data.
        """
        if self.cs_smoothed is None or not self.d_prime or self.cs_smoothed <= 0:
            self.archetype = "HYBRID"
            return
        ratio = self.d_prime / self.cs_smoothed
        if ratio > 300:
            self.archetype = "SPEED"
        elif ratio < 150:
            self.archetype = "ENDURANCE"
        else:
            self.archetype = "HYBRID"

    @property
    def tau_w_prime_multiplier(self) -> float:
        """
        τW′ reconstitution multiplier by archetype.

        Speed-dominant athletes reconstitute D′ more slowly (larger reservoir,
        slower clearance kinetics).
        """
        return {"SPEED": 1.175, "ENDURANCE": 0.925, "HYBRID": 1.0}[self.archetype]

    # ── Calibration Confidence ───────────────────────────────────────────────

    def _update_confidence(self) -> None:
        """
        Confidence score (0.0–1.0) as function of:
          - Number of calibration performances (saturates at 5+) — 50% weight
          - Recency of most recent performance (full credit ≤ 21d) — 50% weight
        """
        n = len(self.cs_raw_history)
        n_score = min(n / 5.0, 1.0) * 0.5
        try:
            latest = max(datetime.fromisoformat(d).replace(tzinfo=UTC) for d, _ in self.cs_raw_history)
            days_since = (datetime.now(UTC) - latest).days
            recency_score = max(0.0, 1.0 - days_since / 42.0) * 0.5
        except Exception:
            recency_score = 0.0
        self.confidence = round(min(1.0, n_score + recency_score), 2)

    # ── Thermal Degradation ──────────────────────────────────────────────────

    def apply_thermal(self, temp_c: float, dew_point_c: float | None = None) -> float | None:
        """
        Return heat-adjusted CS.

        When dew_point_c is provided, uses the Environmental Stress Index (ESI):
          ESI = temp_c + 0.5 * dew_point_c
        Degradation begins at ESI_MODERATE_MIN (16.0) and follows the same
        ~2.5% per 5-unit ESI band formula, floored at 85% of CS.

        When dew_point_c is None, falls back to dry-bulb only:
          CS declines ~2.5% per 5°C above 20°C threshold.
          (Jones & Doust, 1997 — validated for ambient temperature range 15–35°C)

        Returns smoothed CS if stress index is at or below threshold (no degradation).
        Returns None if no CS estimate available.
        """
        if self.cs_smoothed is None:
            return None

        if dew_point_c is None:
            # Dry-bulb fallback: original behaviour
            if temp_c <= 20.0:
                return round(self.cs_smoothed, 3)
            excess_bands = (temp_c - 20.0) / 5.0
            factor = max(0.85, 1.0 - 0.025 * excess_bands)  # floor at 85% of CS
            return round(self.cs_smoothed * factor, 3)

        # ESI model: composite score accounts for humidity stress
        esi = temp_c + 0.5 * dew_point_c
        if esi <= ESI_MODERATE_MIN:
            return round(self.cs_smoothed, 3)
        excess_bands = (esi - ESI_MODERATE_MIN) / 5.0
        factor = max(0.85, 1.0 - 0.025 * excess_bands)  # floor at 85% of CS
        return round(self.cs_smoothed * factor, 3)

    # ── GAP Correction (static) ──────────────────────────────────────────────

    @staticmethod
    def gap_correct_pace(pace_sec_per_km: float, gradient_pct: float) -> float:
        """
        Grade Adjusted Pace (GAP) — flatten uphill/downhill pace to road-equivalent.

        Simplified Minetti et al. (2002) model:
          ~10 s/km per 1% positive gradient (uphill costs more)
          ~5  s/km per 1% negative gradient (downhill saves less)

        Args:
            pace_sec_per_km: Raw pace in sec/km
            gradient_pct:    Grade in % (positive = uphill, negative = downhill)

        Returns:
            Flat-equivalent pace in sec/km. Floored at 60 s/km (≈16.7 km/h).
        """
        adjustment = gradient_pct * 10.0 if gradient_pct >= 0 else gradient_pct * 5.0
        # downhill: smaller benefit
        return max(60.0, pace_sec_per_km - adjustment)

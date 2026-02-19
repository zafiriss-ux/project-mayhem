"""
Autonomic Fusion Engine (AFI) — Multi-Signal Autonomic Health Regulator

Scientific Basis:
- Plews, D.J. et al. (2013). Int J Sports Physiol Perform, 8(5), 512-521.
  HRV alone is insufficient: chronic HRV elevation can mask overtraining.
- Bellenger, C.R. et al. (2016). Sports Med, 46(9), 1351-1366.
  HRR is a stronger acute autonomic marker than resting HRV.
- Meeusen, R. et al. (2013). Med Sci Sports Exerc. 45(1), 186-205.
  CNS fatigue manifests with 24-48h delay (sympathetic rebound).
- Cheung, S.S. et al. (2000). Sports Med. 29(2), 73-105.
  Parasympathetic rebound can produce falsely elevated HRV.

Key Design Decisions:
1. Weighted fusion (not averaging) — HRV and HRR carry different information
2. 48h CNS Delay Buffer — captures delayed sympathetic strain
3. Parasympathetic Saturation Guard — detects HRV↑ + HRR↓ instability
4. MAD-based HRR z-score — robust to outliers (fever, altitude, equipment)
"""

import math
from typing import Dict, List, Optional, Tuple


class AutonomicFusionEngine:
    """
    Autonomic Fusion Index (AFI) — composite autonomic health estimator.

    Signal Weights (evidence-based):
      ln(rMSSD) deviation 7d vs 28d  →  0.40  (primary HRV signal)
      HRR60 z-score                  →  0.35  (acute autonomic marker)
      Sleep depth delta              →  0.15  (parasympathetic recovery)
      Respiration delta              →  0.10  (sympathetic tone proxy)

    AFI range: -1.0 (severely impaired) → +1.0 (optimal)

    With 48h CNS Delay Buffer:
        AFI_final = (AFI_today + 0.5 × AFI_yesterday) / 1.5

    Parasympathetic Saturation Guard:
        HRV >> baseline  AND  HRR impaired
        → Autonomic instability (functional overreaching)
        → Readiness clamp ≤ 25, disable Z4/Z5
    """

    _WEIGHTS: Dict[str, float] = {
        'ln_rmssd': 0.40,
        'hrr':      0.35,
        'sleep':    0.15,
        'resp':     0.10,
    }

    def __init__(self) -> None:
        # (date, hrr_60, hrr_120) — 60s and 120s post-effort HR recovery
        self.hrr_log: List[Tuple[str, int, int]] = []
        # Rolling AFI history for 48h CNS buffer
        self._afi_history: List[float] = []

    # ── HRR Input ───────────────────────────────────────────────────────────

    def add_hrr(self, date: str, hrr_60: int, hrr_120: int = 0) -> None:
        """Record a Heart Rate Recovery measurement."""
        self.hrr_log.append((date, hrr_60, hrr_120))

    # ── HRR Baseline (MAD-robust z-score) ───────────────────────────────────

    def _hrr_zscore(self, hrr_60_today: int) -> float:
        """
        Z-score of today's HRR60 against 28-day window.
        Uses MAD (Median Absolute Deviation) for outlier robustness:
          z = (x − median) / (1.4826 × MAD)

        Returns 0.0 if fewer than 3 historical records exist.
        """
        values = [h for _, h, _ in self.hrr_log[-28:]]
        if len(values) < 3:
            return 0.0
        n = len(values)
        sorted_v = sorted(values)
        median = sorted_v[n // 2] if n % 2 else (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2.0
        mad = sorted(abs(v - median) for v in values)[n // 2]
        if mad == 0:
            return 0.0
        return (hrr_60_today - median) / (1.4826 * mad)

    # ── AFI Computation ──────────────────────────────────────────────────────

    def calculate_afi(
        self,
        ln_rmssd_deviation: float,
        hrr_60_today: Optional[int] = None,
        sleep_depth_delta: float = 0.0,
        resp_delta: float = 0.0,
    ) -> float:
        """
        Calculate Autonomic Fusion Index (AFI).

        Args:
            ln_rmssd_deviation: Normalised ln(rMSSD) deviation, -1 to +1.
                                 Positive = short-term HRV above long-term baseline.
                                 Compute via HRVGuidedEngine.calculate_ln_rmssd_deviation().
            hrr_60_today:       BPM recovered at 60s post-effort.
                                 None if no measurement available.
            sleep_depth_delta:  Sleep depth vs baseline, -1 to +1.
                                 Compute from Garmin sleep stages delta.
            resp_delta:         Respiration rate delta vs baseline, -1 to +1.
                                 Positive = lower rate (better parasympathetic tone).

        Returns:
            AFI in [-1.0, +1.0].
        """
        W = self._WEIGHTS

        # HRR: z-score normalised to [-1, +1] by clamping at ±3σ
        if hrr_60_today is not None and len(self.hrr_log) >= 3:
            hrr_norm = max(-1.0, min(1.0, self._hrr_zscore(hrr_60_today) / 3.0))
        else:
            hrr_norm = 0.0

        def clamp(v: float) -> float:
            return max(-1.0, min(1.0, v))

        afi = (
            W['ln_rmssd'] * clamp(ln_rmssd_deviation) +
            W['hrr']      * hrr_norm +
            W['sleep']    * clamp(sleep_depth_delta) +
            W['resp']     * clamp(resp_delta)
        )
        return round(afi, 3)

    # ── 48h CNS Delay Buffer ─────────────────────────────────────────────────

    def apply_48h_buffer(self, afi_today: float) -> float:
        """
        Apply 48h CNS Delay Buffer to capture delayed sympathetic strain.

        CNS fatigue peaks 24-48h post-effort (Meeusen et al.).
        Formula:  AFI_final = (AFI_today + 0.5 × AFI_yesterday) / 1.5

        Returns:
            Buffered AFI in [-1.0, +1.0].
        """
        self._afi_history.append(afi_today)
        if len(self._afi_history) < 2:
            return afi_today
        afi_yesterday = self._afi_history[-2]
        raw = afi_today + 0.5 * afi_yesterday
        return round(max(-1.0, min(1.0, raw / 1.5)), 3)

    # ── Parasympathetic Saturation Guard ────────────────────────────────────

    def check_parasympathetic_guard(
        self,
        hrv_pct_above_baseline: float,
        hrr_60_today: Optional[int] = None,
    ) -> Dict:
        """
        Detect parasympathetic saturation: HRV appears high but autonomic
        system is actually unstable (functional overreaching risk).

        Pattern (Cheung / Plews):
          HRV > 110% of baseline  AND  HRR below expected (z < -1.5σ)

        Args:
            hrv_pct_above_baseline: (today_hrv - baseline) / baseline * 100.
                                     Positive = above baseline.
            hrr_60_today:           Today's HRR60 (None if unavailable).

        Returns:
            Dict with 'triggered', 'reason', 'readiness_clamp', 'disabled_zones'.
        """
        hrv_elevated = hrv_pct_above_baseline > 10.0  # >10% above baseline

        hrr_impaired = False
        if hrr_60_today is not None and len(self.hrr_log) >= 3:
            hrr_impaired = self._hrr_zscore(hrr_60_today) < -1.5

        if hrv_elevated and hrr_impaired:
            return {
                'triggered':        True,
                'reason':           (
                    f'Parasympathetic saturation: HRV +{hrv_pct_above_baseline:.0f}% above baseline '
                    f'with impaired HRR — autonomic instability risk'
                ),
                'readiness_clamp':  25,
                'disabled_zones':   [4, 5],
                'prescribed_type':  'EASY',
                'action':           'HARD_REST',
            }
        return {'triggered': False, 'readiness_clamp': 100, 'disabled_zones': []}

    # ── Unified Readiness Constraints ────────────────────────────────────────

    def get_readiness_constraints(
        self,
        afi_final: float,
        hrv_pct_above_baseline: float,
        hrr_60_today: Optional[int] = None,
    ) -> Dict:
        """
        Translate AFI + guard signals into readiness constraints for governance.

        Returns:
            Dict with:
              afi          — final AFI score (-1 to +1)
              afi_modifier — integer readiness adjustment (-20 to +10)
              parasympathetic_guard — guard result dict
              readiness_clamp — ceiling for readiness score
              disabled_zones  — list of heart-rate zones to block
        """
        guard = self.check_parasympathetic_guard(hrv_pct_above_baseline, hrr_60_today)
        # Map AFI linearly to readiness modifier: -1 → -20, +1 → +10
        afi_modifier = round(afi_final * 15)
        return {
            'afi':                 afi_final,
            'afi_modifier':        afi_modifier,
            'parasympathetic_guard': guard,
            'readiness_clamp':     guard['readiness_clamp'],
            'disabled_zones':      guard['disabled_zones'],
        }

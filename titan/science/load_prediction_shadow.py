"""Shadow-mode load prediction service for Phase 7 rollout.

This module intentionally does not influence session prescription.
It produces a forward-looking load estimate for observability only,
so ML paths can be validated before any athlete-facing activation.
"""

from dataclasses import dataclass
from typing import Dict, Iterable, List

from titan.science.ml_safety import enforce_ml_kill_switch


@dataclass(frozen=True)
class ShadowLoadPrediction:
    """Immutable prediction payload for downstream audit/UI surfaces."""

    predicted_load_7d: float
    trend: str
    model_name: str = "LSTM_SHADOW_BASELINE"
    mode: str = "SHADOW"
    evidence_label: str = "HEURISTIC"


class LoadPredictionShadowModel:
    """Deterministic shadow predictor using EWMA as an LSTM-compatible proxy.

    Rationale:
    - Keeps architecture stable while Phase 7 starts.
    - Provides a measurable baseline to compare against the future LSTM.
    - Never auto-applies decisions; output is informational only.
    """

    def __init__(self, alpha: float = 0.35) -> None:
        if not (0.0 < float(alpha) <= 1.0):
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = float(alpha)

    def predict_7d_load(
        self,
        recent_loads: Iterable[float],
        athlete_facing: bool = False,
    ) -> ShadowLoadPrediction:
        """Estimate next-7-day aggregate load from recent daily loads.

        Args:
            recent_loads: most-recent-first or oldest-first numeric daily loads.

        Returns:
            ShadowLoadPrediction payload for audit dashboards.
        """
        enforce_ml_kill_switch(path_name="load_prediction_shadow", athlete_facing=athlete_facing)

        values: list[float] = [max(0.0, float(v)) for v in recent_loads]
        if not values:
            return ShadowLoadPrediction(predicted_load_7d=0.0, trend="FLAT")

        # EWMA over supplied sequence; deterministic and dependency-free.
        ewma = values[0]
        for load in values[1:]:
            ewma = self.alpha * load + (1.0 - self.alpha) * ewma

        predicted = round(ewma * 7.0, 1)
        baseline = sum(values[-min(7, len(values)) :])

        if predicted > baseline * 1.08:
            trend = "UP"
        elif predicted < baseline * 0.92:
            trend = "DOWN"
        else:
            trend = "FLAT"

        return ShadowLoadPrediction(predicted_load_7d=predicted, trend=trend)

    @staticmethod
    def as_dict(prediction: ShadowLoadPrediction) -> dict[str, object]:
        """Serialize prediction payload for API/UI consumers."""
        return {
            "predicted_load_7d": prediction.predicted_load_7d,
            "trend": prediction.trend,
            "model_name": prediction.model_name,
            "mode": prediction.mode,
            "evidence_label": prediction.evidence_label,
        }

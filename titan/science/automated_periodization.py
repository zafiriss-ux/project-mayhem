"""Automated periodization scaffold for Phase 7 rollout.

This module is intentionally suggest-only. It proposes a conservative weekly
microcycle adjustment while preserving human confirmation before any apply step.
"""

from dataclasses import dataclass
from typing import Dict, Mapping

from titan.science.ml_safety import enforce_ml_kill_switch


@dataclass(frozen=True)
class PeriodizationSuggestion:
    """Immutable advisory payload for periodization review surfaces."""

    recommended_focus: str
    volume_adjustment_pct: float
    intensity_adjustment_pct: float
    confidence: float
    mode: str = "SUGGEST_ONLY"
    model_name: str = "GA_PERIODIZATION_BASELINE"
    evidence_label: str = "HEURISTIC"


class AutomatedPeriodizationEngine:
    """Deterministic proxy for a future genetic-algorithm planner.

    Phase intent:
    - Keep integration contracts stable for orchestration/UI wiring.
    - Provide explainable recommendations before introducing GA dependencies.
    - Enforce suggest-only mode until athlete confirmation is implemented.
    """

    def suggest(
        self,
        state: Mapping[str, float],
        athlete_facing: bool = False,
    ) -> PeriodizationSuggestion:
        enforce_ml_kill_switch(path_name="automated_periodization", athlete_facing=athlete_facing)

        readiness = max(0.0, min(1.0, float(state.get("readiness", 0.5))))
        fatigue = max(0.0, min(1.0, float(state.get("fatigue", 0.5))))
        monotony = max(0.0, float(state.get("monotony", 1.3)))
        compliance = max(0.0, min(1.0, float(state.get("compliance", 0.85))))

        if fatigue >= 0.72 or readiness <= 0.35:
            focus = "RECOVERY"
            volume = -0.18
            intensity = -0.12
        elif readiness >= 0.70 and fatigue <= 0.45 and compliance >= 0.80:
            focus = "BUILD"
            volume = 0.10
            intensity = 0.05
        else:
            focus = "STABILIZE"
            volume = 0.00
            intensity = 0.00

        if monotony >= 1.8:
            volume = min(volume, -0.08)
            intensity = min(intensity, -0.05)
            if focus == "BUILD":
                focus = "STABILIZE"

        confidence = self._confidence(readiness, fatigue, compliance)

        return PeriodizationSuggestion(
            recommended_focus=focus,
            volume_adjustment_pct=round(volume, 3),
            intensity_adjustment_pct=round(intensity, 3),
            confidence=confidence,
        )

    @staticmethod
    def as_dict(suggestion: PeriodizationSuggestion) -> dict[str, object]:
        return {
            "recommended_focus": suggestion.recommended_focus,
            "volume_adjustment_pct": suggestion.volume_adjustment_pct,
            "intensity_adjustment_pct": suggestion.intensity_adjustment_pct,
            "confidence": suggestion.confidence,
            "mode": suggestion.mode,
            "model_name": suggestion.model_name,
            "evidence_label": suggestion.evidence_label,
        }

    @staticmethod
    def _confidence(readiness: float, fatigue: float, compliance: float) -> float:
        spread = abs(readiness - fatigue)
        base = 0.45 + min(0.40, spread * 0.5)
        quality = min(0.15, compliance * 0.15)
        return round(min(0.95, base + quality), 3)

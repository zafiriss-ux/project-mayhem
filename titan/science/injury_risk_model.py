"""Injury risk ensemble scaffold for Phase 7 rollout.

This model is advisory-only in the current phase. It exposes a stable
contract and deterministic scoring so we can validate integration,
monitor recall, and gate rollout before any autonomous intervention.
"""

from dataclasses import dataclass
from typing import Dict, Mapping

from titan.science.ml_safety import enforce_ml_kill_switch


@dataclass(frozen=True)
class InjuryRiskAssessment:
    """Immutable advisory payload for audit/UI consumers."""

    risk_score: float
    risk_band: str
    model_name: str = "RF_GB_ENSEMBLE_BASELINE"
    mode: str = "ADVISORY"
    recall_target: float = 0.80
    evidence_label: str = "HEURISTIC"


class InjuryRiskEnsembleModel:
    """Deterministic proxy for the planned RF+GB injury-risk ensemble.

    Phase intent:
    - Keep the integration boundary stable for orchestration/UI.
    - Provide an explainable baseline before introducing external ML deps.
    - Enforce advisory mode only during shadow calibration.
    """

    def assess_risk(
        self,
        features: Mapping[str, float],
        athlete_facing: bool = False,
    ) -> InjuryRiskAssessment:
        enforce_ml_kill_switch(path_name="injury_risk_model", athlete_facing=athlete_facing)

        normalized = self._normalize(features)
        rf_score = self._rf_proxy(normalized)
        gb_score = self._gb_proxy(normalized)
        score = round((rf_score + gb_score) / 2.0, 3)

        if score >= 0.67:
            band = "HIGH"
        elif score >= 0.34:
            band = "MEDIUM"
        else:
            band = "LOW"

        return InjuryRiskAssessment(risk_score=score, risk_band=band)

    @staticmethod
    def as_dict(assessment: InjuryRiskAssessment) -> dict[str, object]:
        return {
            "risk_score": assessment.risk_score,
            "risk_band": assessment.risk_band,
            "model_name": assessment.model_name,
            "mode": assessment.mode,
            "recall_target": assessment.recall_target,
            "evidence_label": assessment.evidence_label,
        }

    @staticmethod
    def _normalize(features: Mapping[str, float]) -> dict[str, float]:
        return {
            "hrv_delta": float(features.get("hrv_delta", 0.0)),
            "tsb": float(features.get("tsb", 0.0)),
            "sleep_hours": max(0.0, float(features.get("sleep_hours", 7.0))),
            "soreness": min(10.0, max(0.0, float(features.get("soreness", 0.0)))),
            "acute_load_ratio": max(0.0, float(features.get("acute_load_ratio", 1.0))),
            "monotony": max(0.0, float(features.get("monotony", 1.0))),
        }

    def _rf_proxy(self, f: Mapping[str, float]) -> float:
        score = 0.0
        if f["hrv_delta"] <= -8:
            score += 0.30
        if f["tsb"] <= -20:
            score += 0.25
        if f["sleep_hours"] < 6.5:
            score += 0.15
        if f["soreness"] >= 7:
            score += 0.15
        if f["acute_load_ratio"] >= 1.4:
            score += 0.15
        return min(1.0, score)

    def _gb_proxy(self, f: Mapping[str, float]) -> float:
        score = 0.0
        score += min(0.25, max(0.0, (6.5 - f["sleep_hours"]) * 0.08))
        score += min(0.25, max(0.0, (-f["hrv_delta"] - 2.0) * 0.02))
        score += min(0.20, max(0.0, (-f["tsb"] - 8.0) * 0.01))
        score += min(0.20, max(0.0, (f["acute_load_ratio"] - 1.0) * 0.35))
        score += min(0.10, max(0.0, (f["monotony"] - 1.4) * 0.2))
        return min(1.0, score)

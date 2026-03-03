"""
Phase 7 hygiene — branch-coverage sweep and deliverable validation for the
ML features scaffold (load prediction, injury risk, automated periodization,
ML safety kill-switch).

Coverage targets (98 % → 100 % aggregate):
  load_prediction_shadow.py:
    * line 36  — ValueError raised when alpha ≤ 0 or alpha > 1
    * line 73  — trend = 'FLAT' (stable series, 7 identical loads)
  injury_risk_model.py:
    * line 52  — band = 'MEDIUM' (risk score 0.34–0.67)

Phase 7 deliverable smoke checks:
  - All 4 Phase 7 modules importable directly from titan.science public API
  - ml_safety.MLSafety: kill-switch default-ON; env toggle works
  - Evidence labels ('HEURISTIC') present on every payload dataclass
  - Mode strings correct: SHADOW / ADVISORY / SUGGEST_ONLY
  - All three model engines expose stable as_dict() contracts
  - Negative alpha rejects construction; zero alpha rejects construction
  - MEDIUM risk band reachable with realistic features
  - Flat trend reachable with long stable load history
  - AutomatedPeriodizationEngine.suggest(): STABILIZE branch with moderate
    monotony that does not reach BUILD threshold
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from titan.science.automated_periodization import (
    AutomatedPeriodizationEngine,
    PeriodizationSuggestion,
)
from titan.science.injury_risk_model import InjuryRiskAssessment, InjuryRiskEnsembleModel
from titan.science.load_prediction_shadow import LoadPredictionShadowModel, ShadowLoadPrediction
from titan.science.ml_safety import enforce_ml_kill_switch, is_ml_kill_switch_enabled

# ─────────────────────────────────────────────────────────────────────────────
# 1 · load_prediction_shadow — missing branches
# ─────────────────────────────────────────────────────────────────────────────

class TestLoadPredictionMissingBranches:
    """Hit the two uncovered lines in load_prediction_shadow.py."""

    def test_invalid_alpha_zero_raises_value_error(self):
        """line 36: raise ValueError when alpha == 0 (boundary excluded)."""
        with pytest.raises(ValueError, match="alpha must be in"):
            LoadPredictionShadowModel(alpha=0.0)

    def test_invalid_alpha_negative_raises_value_error(self):
        """line 36: raise ValueError when alpha < 0."""
        with pytest.raises(ValueError, match="alpha must be in"):
            LoadPredictionShadowModel(alpha=-0.1)

    def test_invalid_alpha_above_one_raises_value_error(self):
        """line 36: raise ValueError when alpha > 1."""
        with pytest.raises(ValueError, match="alpha must be in"):
            LoadPredictionShadowModel(alpha=1.1)

    def test_stable_seven_value_series_produces_flat_trend(self):
        """line 73: trend = 'FLAT' when prediction falls within ±8 % of baseline.

        With 7 identical loads the EWMA converges to the same value,
        predicted = ewma * 7 == sum(last 7) → ratio == 1.0 → FLAT.
        """
        model = LoadPredictionShadowModel(alpha=0.35)
        pred = model.predict_7d_load([60.0] * 7)

        assert pred.trend == 'FLAT'
        assert pred.predicted_load_7d > 0.0
        assert pred.mode == 'SHADOW'

    def test_exactly_one_value_returns_non_zero_prediction(self):
        """Single-element list: no EWMA iterations, trend branch still evaluated."""
        model = LoadPredictionShadowModel()
        pred = model.predict_7d_load([100.0])

        assert pred.predicted_load_7d > 0.0
        assert pred.trend in {'UP', 'DOWN', 'FLAT'}


# ─────────────────────────────────────────────────────────────────────────────
# 2 · injury_risk_model — MEDIUM band (line 52)
# ─────────────────────────────────────────────────────────────────────────────

class TestInjuryRiskMediumBand:
    """Cover the elif score >= 0.34 branch (band = 'MEDIUM')."""

    def test_moderate_risk_profile_returns_medium_band(self):
        """Features calibrated so combined score falls in [0.34, 0.67).

        RF proxy: hrv_delta <= -8 (+0.30) + tsb <= -20 (+0.25) = 0.55
        GB proxy: hrv term 0.14 + tsb term 0.17 + alr term 0.105     = ~0.415
        combined: (0.55 + 0.415) / 2 ≈ 0.483  →  MEDIUM
        """
        model = InjuryRiskEnsembleModel()
        assessment = model.assess_risk({
            'hrv_delta': -9.0,
            'tsb': -25.0,
            'sleep_hours': 7.5,
            'soreness': 3.0,
            'acute_load_ratio': 1.3,
            'monotony': 1.2,
        })

        assert assessment.risk_band == 'MEDIUM'
        assert 0.34 <= assessment.risk_score < 0.67

    def test_medium_risk_dict_contains_correct_mode(self):
        """as_dict() on a MEDIUM result still reports ADVISORY mode."""
        model = InjuryRiskEnsembleModel()
        assessment = model.assess_risk({'hrv_delta': -9.0, 'tsb': -25.0})
        payload = model.as_dict(assessment)

        assert payload['mode'] == 'ADVISORY'
        assert payload['evidence_label'] == 'HEURISTIC'


# ─────────────────────────────────────────────────────────────────────────────
# 3 · Phase 7 deliverable smoke checks
# ─────────────────────────────────────────────────────────────────────────────

class TestPhase7PublicAPI:
    """Verify all Phase 7 symbols are accessible from the titan.science namespace."""

    def test_load_prediction_symbols_in_science_namespace(self):
        import titan.science as ts
        assert hasattr(ts, 'LoadPredictionShadowModel')
        assert hasattr(ts, 'ShadowLoadPrediction')

    def test_injury_risk_symbols_in_science_namespace(self):
        import titan.science as ts
        assert hasattr(ts, 'InjuryRiskEnsembleModel')
        assert hasattr(ts, 'InjuryRiskAssessment')

    def test_periodization_symbols_in_science_namespace(self):
        import titan.science as ts
        assert hasattr(ts, 'AutomatedPeriodizationEngine')
        assert hasattr(ts, 'PeriodizationSuggestion')

    def test_ml_safety_module_importable(self):
        from titan.science import ml_safety  # noqa: F401 — import-only smoke check
        assert callable(ml_safety.is_ml_kill_switch_enabled)
        assert callable(ml_safety.enforce_ml_kill_switch)


class TestPhase7EvidenceLabels:
    """Every ML payload dataclass must carry an evidence_label field = 'HEURISTIC'."""

    def test_shadow_load_prediction_carries_heuristic_label(self):
        pred = LoadPredictionShadowModel().predict_7d_load([70, 75, 80])
        assert pred.evidence_label == 'HEURISTIC'

    def test_injury_risk_assessment_carries_heuristic_label(self):
        assessment = InjuryRiskEnsembleModel().assess_risk({})
        assert assessment.evidence_label == 'HEURISTIC'

    def test_periodization_suggestion_carries_heuristic_label(self):
        suggestion = AutomatedPeriodizationEngine().suggest({})
        assert suggestion.evidence_label == 'HEURISTIC'

    def test_evidence_label_surfaced_in_dict_contract(self):
        """Evidence label must survive serialisation through as_dict()."""
        model = LoadPredictionShadowModel()
        payload = model.as_dict(model.predict_7d_load([80]))
        assert payload['evidence_label'] == 'HEURISTIC'


class TestPhase7ModeStrings:
    """Each ML engine must advertise the correct phase-gate mode string."""

    def test_load_prediction_mode_is_shadow(self):
        pred = LoadPredictionShadowModel().predict_7d_load([50])
        assert pred.mode == 'SHADOW'

    def test_injury_risk_mode_is_advisory(self):
        assessment = InjuryRiskEnsembleModel().assess_risk({})
        assert assessment.mode == 'ADVISORY'

    def test_periodization_mode_is_suggest_only(self):
        suggestion = AutomatedPeriodizationEngine().suggest({})
        assert suggestion.mode == 'SUGGEST_ONLY'


class TestPhase7KillSwitchIntegration:
    """Kill-switch is default-ON; non-athlete-facing paths are always available."""

    def test_kill_switch_default_on_when_env_absent(self, monkeypatch):
        monkeypatch.delenv('TITAN_ML_KILL_SWITCH', raising=False)
        assert is_ml_kill_switch_enabled() is True

    def test_kill_switch_disabled_by_env_zero(self, monkeypatch):
        monkeypatch.setenv('TITAN_ML_KILL_SWITCH', '0')
        assert is_ml_kill_switch_enabled() is False

    def test_enforce_blocks_athlete_facing_when_switch_on(self, monkeypatch):
        monkeypatch.setenv('TITAN_ML_KILL_SWITCH', '1')
        with pytest.raises(RuntimeError, match="ML kill-switch active"):
            enforce_ml_kill_switch('test_path', athlete_facing=True)

    def test_enforce_is_noop_for_non_athlete_facing(self, monkeypatch):
        monkeypatch.setenv('TITAN_ML_KILL_SWITCH', '1')
        enforce_ml_kill_switch('test_path', athlete_facing=False)  # must not raise

    def test_all_engines_shadow_accessible_with_kill_switch_on(self, monkeypatch):
        monkeypatch.setenv('TITAN_ML_KILL_SWITCH', '1')
        load_pred = LoadPredictionShadowModel().predict_7d_load([50, 60])
        risk = InjuryRiskEnsembleModel().assess_risk({})
        suggestion = AutomatedPeriodizationEngine().suggest({})

        assert load_pred.mode == 'SHADOW'
        assert risk.mode == 'ADVISORY'
        assert suggestion.mode == 'SUGGEST_ONLY'


class TestPhase7DictContractStability:
    """All three model.as_dict() outputs must expose the full canonical key set."""

    def test_load_prediction_dict_keys(self):
        model = LoadPredictionShadowModel()
        payload = model.as_dict(model.predict_7d_load([50, 60]))
        assert set(payload) == {
            'predicted_load_7d',
            'trend',
            'model_name',
            'mode',
            'evidence_label',
        }

    def test_injury_risk_dict_keys(self):
        model = InjuryRiskEnsembleModel()
        payload = model.as_dict(model.assess_risk({}))
        assert set(payload) == {
            'risk_score',
            'risk_band',
            'model_name',
            'mode',
            'recall_target',
            'evidence_label',
        }

    def test_periodization_dict_keys(self):
        engine = AutomatedPeriodizationEngine()
        payload = engine.as_dict(engine.suggest({}))
        assert set(payload) == {
            'recommended_focus',
            'volume_adjustment_pct',
            'intensity_adjustment_pct',
            'confidence',
            'mode',
            'model_name',
            'evidence_label',
        }


# ─────────────────────────────────────────────────────────────────────────────
# 4 · AutomatedPeriodizationEngine — additional branch coverage
# ─────────────────────────────────────────────────────────────────────────────

class TestPeriodizationStabilizeBranch:
    """Cover the STABILIZE branch (readiness/fatigue both moderate, within BUILD gate)."""

    def test_moderate_state_produces_stabilize(self):
        """Neither BUILD nor RECOVERY conditions met → STABILIZE with zero adjustments."""
        engine = AutomatedPeriodizationEngine()
        suggestion = engine.suggest({
            'readiness': 0.55,
            'fatigue': 0.50,
            'monotony': 1.3,
            'compliance': 0.78,
        })

        assert suggestion.recommended_focus == 'STABILIZE'
        assert suggestion.volume_adjustment_pct == 0.0
        assert suggestion.intensity_adjustment_pct == 0.0

    def test_confidence_scales_with_readiness_fatigue_spread(self):
        """Wider readiness–fatigue spread → higher confidence."""
        engine = AutomatedPeriodizationEngine()
        high_spread = engine.suggest({'readiness': 0.90, 'fatigue': 0.10})
        low_spread = engine.suggest({'readiness': 0.55, 'fatigue': 0.50})

        assert high_spread.confidence > low_spread.confidence


# ─────────────────────────────────────────────────────────────────────────────
# 5 · Dataclass immutability (frozen=True contract)
# ─────────────────────────────────────────────────────────────────────────────

class TestPayloadImmutability:
    """Payload dataclasses are frozen; mutation must raise FrozenInstanceError."""

    def test_shadow_load_prediction_is_frozen(self):
        pred = LoadPredictionShadowModel().predict_7d_load([60])
        with pytest.raises(FrozenInstanceError):
            pred.trend = 'MUTATED'  # type: ignore[misc]

    def test_injury_risk_assessment_is_frozen(self):
        assessment = InjuryRiskEnsembleModel().assess_risk({})
        with pytest.raises(FrozenInstanceError):
            assessment.risk_band = 'MUTATED'  # type: ignore[misc]

    def test_periodization_suggestion_is_frozen(self):
        suggestion = AutomatedPeriodizationEngine().suggest({})
        with pytest.raises(FrozenInstanceError):
            suggestion.recommended_focus = 'MUTATED'  # type: ignore[misc]

"""
TITAN Science Module - Evidence-Based Training Science

All algorithms based on peer-reviewed research with proper citations.
"""

# Core science engines
from titan.science.acwr_engine import ACWREngine

# Adaptive systems
from titan.science.adaptive_memory import AdaptiveMemory
from titan.science.adaptive_priority_lock import AdaptivePriorityLock
from titan.science.automated_periodization import (
    AutomatedPeriodizationEngine,
    PeriodizationSuggestion,
)

# Biomechanics
from titan.science.biomechanics import BiomechanicsAnalysis
from titan.science.critical_speed import CriticalSpeedEngine

# Performance analysis
from titan.science.drift_engine import DriftEngine
from titan.science.durability_engine import DurabilityEngine
from titan.science.efficiency_engine import EfficiencyEngine
from titan.science.fatigue_engine import FatigueEngine
from titan.science.glycogen_model import GlycogenEngine, GlycogenModel
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.injury_risk_model import InjuryRiskAssessment, InjuryRiskEnsembleModel
from titan.science.lactate_logic import LactateLogic
from titan.science.load_prediction_shadow import LoadPredictionShadowModel, ShadowLoadPrediction
from titan.science.outcome_tracker import GovernanceDecision, OutcomeTracker
from titan.science.rcp_engine import RCPEngine
from titan.science.readiness_engine import ReadinessEngine

# Load and fatigue
from titan.science.trimp_engine import TRIMPEngine
from titan.science.tsb_engine import TSBEngine

# Governance infrastructure (v5.7+)
from titan.science.volume_load_gauge import VLGState, VolumeLoadGauge

__all__ = [
    # Core engines
    "ACWREngine",
    "HRVGuidedEngine",
    "TSBEngine",
    # Performance
    "DriftEngine",
    "EfficiencyEngine",
    "DurabilityEngine",
    "LactateLogic",
    "CriticalSpeedEngine",
    "RCPEngine",
    # Load management
    "TRIMPEngine",
    "GlycogenModel",
    "GlycogenEngine",
    "FatigueEngine",
    "ReadinessEngine",
    # Systems
    "AdaptiveMemory",
    "BiomechanicsAnalysis",
    # Governance infrastructure
    "VolumeLoadGauge",
    "VLGState",
    "AdaptivePriorityLock",
    "OutcomeTracker",
    "GovernanceDecision",
    "LoadPredictionShadowModel",
    "ShadowLoadPrediction",
    "InjuryRiskEnsembleModel",
    "InjuryRiskAssessment",
    "AutomatedPeriodizationEngine",
    "PeriodizationSuggestion",
]

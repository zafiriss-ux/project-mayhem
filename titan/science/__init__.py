"""
TITAN Science Module - Evidence-Based Training Science

All algorithms based on peer-reviewed research with proper citations.
"""

# Core science engines
from titan.science.acwr_engine import ACWREngine
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.tsb_engine import TSBEngine

# Performance analysis
from titan.science.drift_engine import DriftEngine
from titan.science.efficiency_engine import EfficiencyEngine
from titan.science.durability_engine import DurabilityEngine
from titan.science.lactate_logic import LactateLogic
from titan.science.critical_speed import CriticalSpeedEngine
from titan.science.rcp_engine import RCPEngine

# Load and fatigue
from titan.science.trimp_engine import TRIMPEngine
from titan.science.glycogen_model import GlycogenModel, GlycogenEngine
from titan.science.fatigue_engine import FatigueEngine
from titan.science.readiness_engine import ReadinessEngine

# Adaptive systems
from titan.science.adaptive_memory import AdaptiveMemory

# Biomechanics
from titan.science.biomechanics import BiomechanicsAnalysis

# Governance infrastructure (v5.7+)
from titan.science.volume_load_gauge import VolumeLoadGauge, VLGState
from titan.science.adaptive_priority_lock import AdaptivePriorityLock
from titan.science.outcome_tracker import OutcomeTracker, GovernanceDecision
from titan.science.load_prediction_shadow import LoadPredictionShadowModel, ShadowLoadPrediction
from titan.science.injury_risk_model import InjuryRiskEnsembleModel, InjuryRiskAssessment

__all__ = [
    # Core engines
    'ACWREngine',
    'HRVGuidedEngine',
    'TSBEngine',
    # Performance
    'DriftEngine',
    'EfficiencyEngine',
    'DurabilityEngine',
    'LactateLogic',
    'CriticalSpeedEngine',
    'RCPEngine',
    # Load management
    'TRIMPEngine',
    'GlycogenModel',
    'GlycogenEngine',
    'FatigueEngine',
    'ReadinessEngine',
    # Systems
    'AdaptiveMemory',
    'BiomechanicsAnalysis',
    # Governance infrastructure
    'VolumeLoadGauge',
    'VLGState',
    'AdaptivePriorityLock',
    'OutcomeTracker',
    'GovernanceDecision',
    'LoadPredictionShadowModel',
    'ShadowLoadPrediction',
    'InjuryRiskEnsembleModel',
    'InjuryRiskAssessment',
]

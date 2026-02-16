"""
TITAN Science Module - Evidence-Based Training Science

This module contains scientifically validated training engines and models based on
peer-reviewed research in exercise physiology, sports science, and endurance training.

All algorithms are based on published research with proper citations.
"""

from titan.science.acwr_engine import ACWREngine
from titan.science.adaptive_memory import AdaptiveMemory
from titan.science.biomechanics import BiomechanicsAnalysis
from titan.science.critical_speed import CriticalSpeedEngine
from titan.science.drift_engine import DriftEngine
from titan.science.durability_engine import DurabilityEngine
from titan.science.efficiency_engine import EfficiencyEngine
from titan.science.fatigue_engine import FatigueEngine
from titan.science.glycogen_model import GlycogenEngine, GlycogenModel
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.lactate_logic import LactateLogic
from titan.science.rcp_engine import RCPEngine
from titan.science.readiness_engine import ReadinessEngine
from titan.science.trimp_engine import TRIMPEngine
from titan.science.tsb_engine import TSBEngine

__all__ = [
    'ACWREngine',
    'AdaptiveMemory',
    'BiomechanicsAnalysis',
    'CriticalSpeedEngine',
    'DriftEngine',
    'DurabilityEngine',
    'EfficiencyEngine',
    'FatigueEngine',
    'GlycogenEngine',
    'GlycogenModel',
    'HRVGuidedEngine',
    'LactateLogic',
    'RCPEngine',
    'ReadinessEngine',
    'TRIMPEngine',
    'TSBEngine',
]

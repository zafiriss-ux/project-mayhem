"""
TITAN Core Modules
Foundational classes for athlete management, equipment tracking, and periodization
"""

from titan.core.athlete import UniversalAthleteProfile
from titan.core.database import AthleteDatabase, DatabaseManager
from titan.core.equipment import EquipmentManager
from titan.core.periodization import PeriodizationManager

__all__ = [
    'UniversalAthleteProfile',
    'DatabaseManager',
    'AthleteDatabase',
    'EquipmentManager',
    'PeriodizationManager',
]

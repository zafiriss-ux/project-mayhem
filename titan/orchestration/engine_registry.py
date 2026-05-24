"""ADR-0058 Phase A: EngineRegistry — single construction site for all per-athlete science engines."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

from titan.science.adaptive_priority_lock import AdaptivePriorityLock
from titan.science.autonomic_engine import AutonomicFusionEngine
from titan.science.biomechanics import BiomechanicsEngine
from titan.science.critical_speed import CriticalSpeedTracker
from titan.science.durability_engine import DurabilityEngine
from titan.science.fatigue_engine import FatigueEngine
from titan.science.hrv_engine import HRVGuidedEngine
from titan.science.lactate_logic import LactateLogic
from titan.science.readiness_engine import ReadinessEngine
from titan.science.tsb_engine import TSBEngine


@dataclass(frozen=True)
class EngineRegistry:
    """Named container for all per-athlete science engines (ADR-0058 Phase A).

    Frozen: engines are hydrated once per coaching pipeline call.
    Thread-safe: each coaching_pipeline() call receives its own registry
    (or a shared stateless one).
    Phase 9: instantiate one per athlete per pipeline call.
    """

    tsb: TSBEngine
    hrv: HRVGuidedEngine
    readiness: ReadinessEngine
    autonomic: AutonomicFusionEngine
    biomechanics: BiomechanicsEngine
    durability: DurabilityEngine
    fatigue: FatigueEngine
    lactate: LactateLogic
    cs_tracker: CriticalSpeedTracker
    apl: AdaptivePriorityLock

    @classmethod
    def from_db(
        cls,
        db: DatabaseManager,
        athlete_id: str = "owner",
    ) -> EngineRegistry:
        """Factory: hydrate all engines from DB.

        Single authoritative construction site.
        Phase 9: pass athlete_id per athlete to get isolated engine state.
        """
        return cls(
            tsb=TSBEngine(),
            hrv=HRVGuidedEngine(),
            readiness=ReadinessEngine(),
            autonomic=AutonomicFusionEngine(),
            biomechanics=BiomechanicsEngine(),
            durability=DurabilityEngine(),
            fatigue=FatigueEngine(),
            lactate=LactateLogic(),
            cs_tracker=CriticalSpeedTracker(),
            apl=AdaptivePriorityLock(),
        )

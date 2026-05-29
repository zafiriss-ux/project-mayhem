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
        """Single authoritative construction site for all per-athlete engines.

        CURRENT STATE (Phase 24 / ADR-0058 Phase A):
          All engines are constructed stateless. ``db`` and ``athlete_id``
          are accepted for forward-compatibility but are NOT YET WIRED.
          Post-construction DB hydration is performed by
          DailyCoach._hydrate_engines_from_db() in the coaching pipeline.

        TODO-Phase9: wire ``db`` and ``athlete_id`` here so each athlete's
          engine state (TSB load history, HRV baseline, CS performances,
          APL offsets) is loaded at construction time, eliminating the
          separate hydration call and enabling true per-athlete isolation.
          Tracked: TD-08 (schema descriptor prerequisite) → Phase 9 scope.

        TODO-B2c: DailyCoach.__init__ still constructs 7 engines directly
          (F2.1, Opus pre-Phase-24 audit 2026-05-29). Those will be removed
          in Phase 24 blocker B2c so from_db becomes the sole construction
          site for all 10 engine classes.
        """
        # TODO-Phase9: replace bare constructors with DB-hydrated equivalents.
        # Example for TSBEngine:
        #   loads = db.get_training_load_history(athlete_id=athlete_id, days=90)
        #   tsb = TSBEngine(); [tsb.add_load(d, v) for d, v in loads]
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

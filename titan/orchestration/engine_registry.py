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

        Phase 26 / ADR-0058 Phase B: DB hydration wired for TSB and HRV.
        CS performances are hydrated by DailyCoach for its athlete (D-037). The APL needs no hydration:
        it is stateless, and the per-athlete threshold offsets are loaded by
        ThresholdAdapter in coaching_pipeline() for ``context.athlete_id``.
        """
        loads = db.get_training_load_history(athlete_id=athlete_id, days=90)
        tsb = TSBEngine()
        for date_str, load in loads:
            tsb.add_daily_load(date_str, float(load))

        hrv_rows = db.get_hrv_history(days=30, athlete_id=athlete_id)
        hrv = HRVGuidedEngine()
        for date_str, rmssd in reversed(hrv_rows):
            hrv.add_hrv_measurement(date_str, rmssd)

        readiness = ReadinessEngine()

        # CS performances are read per athlete since v28 (D-037); DailyCoach
        # hydrates this tracker in _hydrate_engines_from_db for its own athlete.
        cs_tracker = CriticalSpeedTracker()

        # Stateless (no DB access); offsets live in ThresholdAdapter (see above).
        apl = AdaptivePriorityLock()

        return cls(
            tsb=tsb,
            hrv=hrv,
            readiness=readiness,
            autonomic=AutonomicFusionEngine(),
            biomechanics=BiomechanicsEngine(),
            durability=DurabilityEngine(),
            fatigue=FatigueEngine(),
            lactate=LactateLogic(),
            cs_tracker=cs_tracker,
            apl=apl,
        )

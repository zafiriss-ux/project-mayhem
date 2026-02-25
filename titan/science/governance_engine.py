"""
Governance Engine — Discipline & Behavioral Hard Locks

The kernel decides. The LLM explains.

This module enforces three hard behavioral constraints that protect
training integrity against ego, data-corruption, and model instability.
No soft suggestions — only binary hard gates applied AFTER plan generation
and BEFORE delivery to the athlete.

Hard Gates:
1. Parasympathetic Saturation Guard (via AutonomicFusionEngine)
   → Detects HRV↑ + HRR↓ pattern; forces REST + blocks Z4/Z5
2. Override Lockdown
   → override_ratio_14d > 80%: forces Zone 2 only for the entire period
3. CS Confidence Lock
   → cs_confidence < 70%: disables race simulation + requires calibration

Design Principle:
  apply_constraints() is the FINAL step in DailyCoach.run_morning_routine()
  before the Telegram message is composed. Nothing downstream can bypass it.
"""

from typing import Any, Dict, List, Optional


class GovernanceEngine:
    """
    Hard-lock discipline engine for TITAN OS v5.7.

    All three gates are evaluated independently; multiple can be active
    simultaneously. The most restrictive constraint wins.

    Thresholds (evidence-based + pragmatic):
      Override lockdown:   > 80% of last 14 days with deviation from plan
      CS confidence lock:  < 70% confidence in current CS estimate
      Parasympathetic guard: handled by AutonomicFusionEngine, consumed here
    """

    OVERRIDE_LOCKDOWN_THRESHOLD: float = 0.80
    CS_CONFIDENCE_THRESHOLD:     float = 0.70

    _QUALITY_SESSIONS = frozenset({'INTERVALS', 'TEMPO', 'RACE', 'HAMMER'})

    # ── Individual Gate Checks ───────────────────────────────────────────────

    def check_override_lockdown(self, db: Any) -> Dict:
        """
        Override Lockdown Gate.

        If the athlete has deviated from their prescribed sessions on > 80%
        of the last 14 days, all quality sessions are disabled.

        Rationale: systematic overriding destroys periodization logic and
        exposes the athlete to unplanned overload or underrecovery.

        Args:
            db: DatabaseManager instance

        Returns:
            Dict with 'locked', 'ratio', 'reason', 'max_zone',
                      'disabled_sessions', 'action'.
        """
        try:
            ratio = db.get_override_ratio(days=14)
        except Exception:
            ratio = 0.0

        if ratio > self.OVERRIDE_LOCKDOWN_THRESHOLD:
            return {
                'locked':            True,
                'ratio':             ratio,
                'reason':            (
                    f'Override ratio {ratio:.0%} (14d) > {self.OVERRIDE_LOCKDOWN_THRESHOLD:.0%} '
                    f'threshold — periodization integrity compromised'
                ),
                'max_zone':          2,
                'disabled_sessions': list(self._QUALITY_SESSIONS),
                'action':            'ZONE_2_ONLY',
            }
        return {'locked': False, 'ratio': ratio, 'max_zone': 5, 'disabled_sessions': []}

    def check_cs_confidence_lock(self, cs_tracker: Any) -> Dict:
        """
        CS Confidence Lock Gate.

        If the Critical Speed model has < 70% confidence (insufficient recent
        calibration data), race simulation and TTE predictions are disabled.
        A calibration session is prescribed instead.

        Args:
            cs_tracker: CriticalSpeedTracker instance

        Returns:
            Dict with 'locked', 'confidence', 'reason', 'required_session',
                      'disabled'.
        """
        confidence = getattr(cs_tracker, 'confidence', 1.0)
        if confidence < self.CS_CONFIDENCE_THRESHOLD:
            return {
                'locked':           True,
                'confidence':       confidence,
                'reason':           (
                    f'CS confidence {confidence:.0%} < {self.CS_CONFIDENCE_THRESHOLD:.0%} — '
                    f'calibration time-trial required before race simulation'
                ),
                'required_session': 'CS_CALIBRATION',
                'disabled':         ['RACE_SIMULATION', 'TTE_PREDICTION'],
            }
        return {'locked': False, 'confidence': confidence}

    # ── Unified Constraint Application ───────────────────────────────────────

    def apply_constraints(
        self,
        session_plan: Dict,
        context: Dict,
    ) -> Dict:
        """
        Apply all governance hard gates to the proposed session plan.

        Call order (DailyCoach):
            1. Generate session plan via WeeklyPlanGenerator
            2. Calculate readiness via AFI + TSB + glycogen
            3. → apply_constraints() — LAST step before Telegram composition

        Args:
            session_plan: Dict from WeeklyPlanGenerator (mutated in-place and returned)
            context: Dict with keys:
                'db'              — DatabaseManager (optional)
                'cs_tracker'      — CriticalSpeedTracker (optional)
                'afi_constraints' — Dict from AutonomicFusionEngine.get_readiness_constraints()

        Returns:
            Modified session_plan with added governance metadata.
        """
        db            = context.get('db')
        cs_tracker    = context.get('cs_tracker')
        afi_constr    = context.get('afi_constraints', {})
        applied_locks: List[str] = []

        # Gate 1: Parasympathetic saturation (highest priority)
        para_guard = afi_constr.get('parasympathetic_guard', {})
        if para_guard.get('triggered'):
            session_plan['session_type']        = 'EASY'
            session_plan['max_zone']            = 2
            session_plan['governance_override'] = para_guard['reason']
            applied_locks.append('PARASYMPATHETIC_GUARD')

        # Gate 2: Override lockdown
        if db:
            lock = self.check_override_lockdown(db)
            if lock['locked'] and session_plan.get('session_type') in lock['disabled_sessions']:
                session_plan['session_type']        = 'EASY'
                session_plan['max_zone']            = lock['max_zone']
                session_plan['governance_override'] = lock['reason']
                applied_locks.append('OVERRIDE_LOCKDOWN')

        # Gate 3: CS confidence lock (disables predictions, not sessions)
        if cs_tracker:
            cs_lock = self.check_cs_confidence_lock(cs_tracker)
            if cs_lock['locked']:
                session_plan['cs_prediction_disabled'] = True
                session_plan['required_calibration']   = True
                session_plan['cs_lock_reason']         = cs_lock['reason']
                applied_locks.append('CS_CONFIDENCE_LOCK')

        session_plan['governance_locks_applied'] = applied_locks
        session_plan['governance_clean']         = len(applied_locks) == 0
        return session_plan

    # ── Reporting (for LLM narrative) ────────────────────────────────────────

    def get_governance_report(
        self,
        db: Optional[Any] = None,
        cs_tracker: Optional[Any] = None,
        afi_constraints: Optional[Dict] = None,
    ) -> Dict:
        """
        Return full governance status for LLM narrative generation.

        The LLM receives this dict to EXPLAIN governance decisions —
        it never computes them. The kernel decides; the LLM explains.
        """
        return {
            'override_lockdown':     self.check_override_lockdown(db) if db else {'locked': False},
            'cs_confidence_lock':    self.check_cs_confidence_lock(cs_tracker) if cs_tracker else {'locked': False},
            'parasympathetic_guard': (afi_constraints or {}).get('parasympathetic_guard', {'triggered': False}),
        }

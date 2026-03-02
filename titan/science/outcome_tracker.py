"""
Outcome Tracker — connects governance decisions to session outcomes.

This is the foundational layer for calibration analytics. Without connecting
decision → outcome, thresholds remain policy heuristics forever.

Phase 1 (this module): in-memory store, structured logging, basic summary.
Phase 2 (future):      persist to DB table `governance_outcomes`, compute
                       threshold accuracy metrics, surface calibration
                       recommendations per parameter.

Observability contract:
  Every recorded event emits structured JSON with a `cause` field that
  classifies whether a governance lock was triggered by:
    - 'DATA_PROBLEM'    — missing, invalid, or uncomputable input signal
    - 'TRAINING_LOGIC'  — valid data exceeding a governance threshold
    - 'CLEAN'           — no locks applied

  This distinction is critical for debugging: a DATA_PROBLEM in production
  means an integration issue (Garmin sync, metric pipeline), not overtraining.
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Dict, List, Optional

from titan.core.database import DatabaseManager
from titan.config.evidence_registry import get_evidence

_log = logging.getLogger(__name__)


_LOCK_TO_HEURISTIC_PARAMETERS: Dict[str, List[str]] = {
    'READINESS_2OF4_DOWNGRADE': ['SUBJECTIVE_FATIGUE_2OF4'],
    'HARD_STOP_SAFETY_GATES': ['HARD_STOP_TSB_FLOOR'],
    'VO2_ELIGIBILITY_GATE': ['VO2_READINESS_MIN'],
}

_LOCK_TO_MODERATE_PARAMETERS: Dict[str, List[str]] = {
    'HARD_STOP_SAFETY_GATES': ['HARD_STOP_HRV_DELTA'],
    'VO2_ELIGIBILITY_GATE': ['VO2_GLYCOGEN_DEBT_MAX'],
}


@dataclass
class GovernanceDecision:
    """
    Snapshot of a governance decision for one session.

    Captures the input signal state at decision time so that if a threshold
    later proves miscalibrated, we can correlate it against historical decisions.
    """
    date: str
    session_planned: str          # session_type BEFORE governance
    session_post_governance: str  # session_type AFTER all gates
    locks_applied: List[str]
    governance_clean: bool
    phase: str
    vlg_color: str                # GREEN / YELLOW / RED at decision time
    apl_priority_vector: Dict[str, int]
    lock_thresholds_active: Dict[str, float]

    # Input signal snapshot — for future threshold calibration
    acwr: float
    tsb_value: float
    readiness_score: float
    glycogen_debt: float
    afi_value: Optional[float]

    # Outcome — filled post-session via record_outcome()
    outcome_rpe: Optional[int] = None
    outcome_completed: Optional[bool] = None
    outcome_session_type_actual: Optional[str] = None
    outcome_notes: Optional[str] = None


def _classify_lock_cause(
    locks_applied: List[str],
    acwr: float,
    readiness_score: float,
) -> str:
    """
    Classify the primary cause of a governance intervention.

    'DATA_PROBLEM'   — lock triggered by missing/invalid/uncomputable input.
    'TRAINING_LOGIC' — lock triggered by valid data exceeding a threshold.
    'CLEAN'          — no locks applied.

    This classification is heuristic at Phase 1. Phase 2 will propagate
    the cause field from individual gate events (GovernanceEngine already
    emits cause='DATA_PROBLEM' on invalid numeric inputs).
    """
    if not locks_applied:
        return 'CLEAN'

    # Proxy heuristic: if ACWR or readiness are implausible values that
    # default-replaced would produce, suspect a data pipeline problem.
    data_signals = []
    if acwr <= 0.0 or acwr > 3.0:
        data_signals.append('acwr_out_of_range')
    if readiness_score <= 0.0:
        data_signals.append('readiness_zero')

    # CS_CONFIDENCE_LOCK is by definition a data availability problem:
    # the model has insufficient calibration history, not a training excess.
    if 'CS_CONFIDENCE_LOCK' in locks_applied:
        data_signals.append('cs_calibration_missing')

    if data_signals:
        return 'DATA_PROBLEM'

    return 'TRAINING_LOGIC'


class OutcomeTracker:
    """
    In-memory store connecting governance decisions to session outcomes.

    Usage pattern in DailyCoach:
      1. record_decision() immediately after governance.apply_constraints()
      2. record_outcome() when the athlete reports post-session data
         (RPE, completion, actual session type if they deviated)
      3. get_calibration_summary() surfaces aggregate statistics
         once enough outcomes have accumulated (recommended ≥ 30 sessions)

    By default it runs in-memory only. If constructed with a DatabaseManager,
    decisions/outcomes are also persisted to SQLite and hydrated on startup.
    It emits structured JSON log lines at INFO level for every event.
    """

    def __init__(self, db: Optional[DatabaseManager] = None) -> None:
        self._db = db
        self._decisions: List[GovernanceDecision] = []
        if self._db is not None:
            self._hydrate_from_db()

    def _hydrate_from_db(self) -> None:
        """Restore in-memory tracker state from persisted governance outcomes."""
        try:
            persisted = self._db.get_governance_decisions()
        except Exception as exc:
            _log.warning('OutcomeTracker DB hydration failed: %s', exc)
            return

        self._decisions = [GovernanceDecision(**entry) for entry in persisted]

    # ── Recording ────────────────────────────────────────────────────────────

    def record_decision(
        self,
        session_planned: str,
        session_post_governance: str,
        locks_applied: List[str],
        governance_clean: bool,
        phase: str,
        vlg_color: str,
        apl_result: Dict,
        acwr: float,
        tsb_value: float,
        readiness_score: float,
        glycogen_debt: float,
        afi_value: Optional[float] = None,
        date: Optional[str] = None,
    ) -> GovernanceDecision:
        """
        Record a governance decision immediately after apply_constraints().

        Returns the GovernanceDecision dataclass for the caller to hold
        if it needs to attach an outcome via record_outcome() later.
        """
        cause = _classify_lock_cause(
            locks_applied=locks_applied,
            acwr=acwr,
            readiness_score=readiness_score,
        )

        decision = GovernanceDecision(
            date=date or datetime.now().strftime('%Y-%m-%d'),
            session_planned=str(session_planned),
            session_post_governance=str(session_post_governance),
            locks_applied=list(locks_applied),
            governance_clean=bool(governance_clean),
            phase=str(phase),
            vlg_color=str(vlg_color),
            apl_priority_vector=dict(apl_result.get('priority_vector', {})),
            lock_thresholds_active=dict(apl_result.get('lock_thresholds', {})),
            acwr=float(acwr),
            tsb_value=float(tsb_value),
            readiness_score=float(readiness_score),
            glycogen_debt=float(glycogen_debt),
            afi_value=float(afi_value) if afi_value is not None else None,
        )
        self._decisions.append(decision)
        if self._db is not None:
            self._db.save_governance_decision(asdict(decision))

        _log.info(json.dumps({
            'outcome_tracker': 'decision_recorded',
            'date': decision.date,
            'session_planned': decision.session_planned,
            'session_post_governance': decision.session_post_governance,
            'locks_applied': decision.locks_applied,
            'governance_clean': decision.governance_clean,
            'phase': decision.phase,
            'vlg_color': decision.vlg_color,
            'cause': cause,
            'acwr': round(decision.acwr, 3),
            'tsb_value': round(decision.tsb_value, 1),
            'readiness_score': round(decision.readiness_score, 1),
            'glycogen_debt': round(decision.glycogen_debt, 2),
        }, default=str))

        return decision

    def record_outcome(
        self,
        date: str,
        rpe: Optional[int] = None,
        completed: Optional[bool] = None,
        actual_session_type: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> bool:
        """
        Attach post-session outcome to the recorded decision for that date.

        Returns True if a matching decision was found and updated.
        Call this after the athlete's session (e.g., from Telegram /post-run command).
        """
        for decision in reversed(self._decisions):
            if decision.date == date:
                decision.outcome_rpe = rpe
                decision.outcome_completed = completed
                decision.outcome_session_type_actual = actual_session_type
                decision.outcome_notes = notes

                athlete_deviated = (
                    actual_session_type is not None
                    and actual_session_type.upper() != decision.session_post_governance.upper()
                )

                _log.info(json.dumps({
                    'outcome_tracker': 'outcome_recorded',
                    'date': date,
                    'session_post_governance': decision.session_post_governance,
                    'actual_session': actual_session_type,
                    'athlete_deviated': athlete_deviated,
                    'rpe': rpe,
                    'completed': completed,
                    'locks_applied': decision.locks_applied,
                }, default=str))
                if self._db is not None:
                    self._db.update_governance_outcome(
                        date=date,
                        rpe=rpe,
                        completed=completed,
                        actual_session_type=actual_session_type,
                        notes=notes,
                    )
                return True

        _log.warning(json.dumps({
            'outcome_tracker': 'outcome_record_miss',
            'date': date,
            'note': 'No decision found for this date — record_decision() must precede record_outcome()',
        }))
        return False

    # ── Query ────────────────────────────────────────────────────────────────

    def get_decisions(
        self,
        date: Optional[str] = None,
        with_outcomes_only: bool = False,
        phase: Optional[str] = None,
    ) -> List[GovernanceDecision]:
        """Return stored decisions, optionally filtered."""
        result = list(self._decisions)
        if date:
            result = [d for d in result if d.date == date]
        if phase:
            result = [d for d in result if d.phase.upper() == phase.upper()]
        if with_outcomes_only:
            result = [d for d in result if d.outcome_completed is not None]
        return result

    def get_lock_rate_by_phase(self) -> Dict[str, float]:
        """
        Return governance lock rate grouped by training phase.

        Useful for identifying whether a specific phase consistently
        triggers more locks than expected, which may indicate miscalibrated
        thresholds for that phase context.
        """
        by_phase: Dict[str, List[bool]] = {}
        for d in self._decisions:
            by_phase.setdefault(d.phase, []).append(not d.governance_clean)
        return {
            phase: round(sum(locked) / len(locked), 3)
            for phase, locked in by_phase.items()
            if locked
        }

    def get_lock_outcome_correlation(self, min_samples: int = 3) -> Dict[str, Dict]:
        """
        Correlate each lock trigger with downstream completion + RPE outcomes.

        This is a Phase-5 calibration primitive used to identify which gates
        are most strongly associated with session success/failure.
        """
        decided = [d for d in self._decisions if d.outcome_completed is not None]
        if not decided:
            return {}

        lock_names = sorted({lock for d in decided for lock in d.locks_applied})
        correlation: Dict[str, Dict] = {}

        for lock in lock_names:
            with_lock = [d for d in decided if lock in d.locks_applied]
            without_lock = [d for d in decided if lock not in d.locks_applied]

            if len(with_lock) < min_samples or len(without_lock) < min_samples:
                continue

            completion_with = sum(1 for d in with_lock if d.outcome_completed) / len(with_lock)
            completion_without = (
                sum(1 for d in without_lock if d.outcome_completed) / len(without_lock)
            )
            rpe_with_values = [d.outcome_rpe for d in with_lock if d.outcome_rpe is not None]
            rpe_without_values = [d.outcome_rpe for d in without_lock if d.outcome_rpe is not None]
            rpe_with = (
                round(sum(rpe_with_values) / len(rpe_with_values), 1)
                if rpe_with_values else None
            )
            rpe_without = (
                round(sum(rpe_without_values) / len(rpe_without_values), 1)
                if rpe_without_values else None
            )

            correlation[lock] = {
                'n_with_lock': len(with_lock),
                'n_without_lock': len(without_lock),
                'completion_with_lock': round(completion_with, 3),
                'completion_without_lock': round(completion_without, 3),
                'completion_delta_pp': round((completion_with - completion_without) * 100, 1),
                'avg_rpe_with_lock': rpe_with,
                'avg_rpe_without_lock': rpe_without,
            }

        return correlation

    # ── Calibration summary ──────────────────────────────────────────────────

    def get_calibration_summary(self) -> Dict:
        """
        Compute Phase-1 calibration metrics from recorded decisions + outcomes.

        Phase 1 is coarse aggregate statistics. Accurate threshold calibration
        requires ≥ 30 outcome-paired decisions and a DB-backed accumulation cycle.

        Returns a structured dict safe to log or display in Telegram /stats.
        """
        n_total = len(self._decisions)
        decided = [d for d in self._decisions if d.outcome_completed is not None]
        n_with_outcome = len(decided)

        if n_with_outcome == 0:
            return {
                'status': 'NO_OUTCOMES_YET',
                'n_decisions': n_total,
                'n_with_outcome': 0,
                'note': (
                    'Call record_outcome() after each session to enable '
                    'calibration analytics.'
                ),
            }

        n_locked = sum(1 for d in decided if not d.governance_clean)
        n_completed = sum(1 for d in decided if d.outcome_completed)
        n_deviated = sum(
            1 for d in decided
            if d.outcome_session_type_actual
            and d.outcome_session_type_actual.upper() != d.session_post_governance.upper()
        )
        rpe_values = [d.outcome_rpe for d in decided if d.outcome_rpe is not None]
        avg_rpe = round(sum(rpe_values) / len(rpe_values), 1) if rpe_values else None

        lock_rate = round(n_locked / n_with_outcome, 3)
        completion_rate = round(n_completed / n_with_outcome, 3)
        athlete_override_rate = round(n_deviated / n_with_outcome, 3)

        calibration_ready = n_with_outcome >= 30
        lock_outcome_correlation = self.get_lock_outcome_correlation()

        return {
            'status': 'CALIBRATION_AVAILABLE' if calibration_ready else 'ACCUMULATING',
            'n_decisions': n_total,
            'n_with_outcome': n_with_outcome,
            'governance_lock_rate': lock_rate,
            'completion_rate': completion_rate,
            'athlete_override_rate': athlete_override_rate,
            'avg_rpe_when_completed': avg_rpe,
            'lock_rate_by_phase': self.get_lock_rate_by_phase(),
            'lock_outcome_correlation': lock_outcome_correlation,
            'heuristic_promotion_candidates': self._get_heuristic_promotion_candidates(
                lock_outcome_correlation
            ),
            'moderate_promotion_candidates': self._get_moderate_promotion_candidates(
                lock_outcome_correlation
            ),
            'calibration_note': (
                'Ready for threshold calibration review.'
                if calibration_ready else
                f'Accumulate {30 - n_with_outcome} more outcome-paired sessions '
                f'before interpreting rates. Thresholds are policy heuristics until '
                f'at least 30 correlated outcomes exist.'
            ),
        }

    def _get_heuristic_promotion_candidates(
        self,
        lock_outcome_correlation: Dict[str, Dict],
    ) -> List[Dict]:
        """
        Build candidate list for HEURISTIC → MODERATE promotion review.

        A candidate is surfaced only when:
          - the lock maps to a HEURISTIC parameter,
          - there are at least 5 sessions in both with-lock / without-lock groups,
          - absolute completion delta is at least 8 percentage points.
        """
        candidates: List[Dict] = []

        for lock_name, params in _LOCK_TO_HEURISTIC_PARAMETERS.items():
            metrics = lock_outcome_correlation.get(lock_name)
            if not metrics:
                continue

            n_with = int(metrics.get('n_with_lock', 0) or 0)
            n_without = int(metrics.get('n_without_lock', 0) or 0)
            completion_delta_pp = float(metrics.get('completion_delta_pp', 0.0) or 0.0)

            if n_with < 5 or n_without < 5 or abs(completion_delta_pp) < 8.0:
                continue

            for parameter in params:
                evidence = get_evidence(parameter)
                if evidence is None or evidence.evidence_level != 'HEURISTIC':
                    continue

                candidates.append({
                    'parameter': parameter,
                    'trigger_lock': lock_name,
                    'n_with_lock': n_with,
                    'n_without_lock': n_without,
                    'completion_delta_pp': round(completion_delta_pp, 1),
                    'recommendation': (
                        'Review for HEURISTIC→MODERATE promotion with ADR + EvidenceRegistry update.'
                    ),
                })

        return sorted(candidates, key=lambda x: abs(x['completion_delta_pp']), reverse=True)

    def _get_moderate_promotion_candidates(
        self,
        lock_outcome_correlation: Dict[str, Dict],
    ) -> List[Dict]:
        """
        Build candidate list for MODERATE → STRONG promotion review.

        A candidate is surfaced only when:
          - the lock maps to a MODERATE parameter,
          - there are at least 8 sessions in both with-lock / without-lock groups,
          - absolute completion delta is at least 10 percentage points,
          - lock behavior appears in at least 2 distinct phases.
        """
        candidates: List[Dict] = []

        for lock_name, params in _LOCK_TO_MODERATE_PARAMETERS.items():
            metrics = lock_outcome_correlation.get(lock_name)
            if not metrics:
                continue

            n_with = int(metrics.get('n_with_lock', 0) or 0)
            n_without = int(metrics.get('n_without_lock', 0) or 0)
            completion_delta_pp = float(metrics.get('completion_delta_pp', 0.0) or 0.0)

            with_lock_phases = {
                d.phase for d in self._decisions
                if d.outcome_completed is not None and lock_name in d.locks_applied
            }
            phase_replication_count = len(with_lock_phases)

            if (
                n_with < 8
                or n_without < 8
                or abs(completion_delta_pp) < 10.0
                or phase_replication_count < 2
            ):
                continue

            for parameter in params:
                evidence = get_evidence(parameter)
                if evidence is None or evidence.evidence_level != 'MODERATE':
                    continue

                candidates.append({
                    'parameter': parameter,
                    'trigger_lock': lock_name,
                    'n_with_lock': n_with,
                    'n_without_lock': n_without,
                    'completion_delta_pp': round(completion_delta_pp, 1),
                    'phase_replication_count': phase_replication_count,
                    'recommendation': (
                        'Review for MODERATE→STRONG promotion after cross-profile replication '
                        'and EvidenceRegistry update.'
                    ),
                })

        return sorted(candidates, key=lambda x: abs(x['completion_delta_pp']), reverse=True)

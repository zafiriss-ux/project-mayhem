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

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.science.threshold_adapter import ThresholdAdapter

from titan.config import thresholds
from titan.config.evidence_registry import get_evidence
from titan.core.database import DatabaseManager

MODULE_VERSION = "1.0.0"

_log = logging.getLogger(__name__)


_LOCK_TO_HEURISTIC_PARAMETERS: dict[str, list[str]] = {
    "READINESS_2OF4_DOWNGRADE": ["SUBJECTIVE_FATIGUE_2OF4"],
    "HARD_STOP_SAFETY_GATES": ["HARD_STOP_TSB_FLOOR"],
    "VO2_ELIGIBILITY_GATE": ["VO2_READINESS_MIN"],
}

_LOCK_TO_MODERATE_PARAMETERS: dict[str, list[str]] = {
    "HARD_STOP_SAFETY_GATES": ["HARD_STOP_HRV_DELTA"],
    "VO2_ELIGIBILITY_GATE": ["VO2_GLYCOGEN_DEBT_MAX"],
}


@dataclass
class GovernanceDecision:
    """
    Snapshot of a governance decision for one session.

    Captures the input signal state at decision time so that if a threshold
    later proves miscalibrated, we can correlate it against historical decisions.
    """

    date: str
    session_planned: str  # session_type BEFORE governance
    session_post_governance: str  # session_type AFTER all gates
    locks_applied: list[str]
    governance_clean: bool
    phase: str
    vlg_color: str  # GREEN / YELLOW / RED at decision time
    apl_priority_vector: dict[str, int]
    lock_thresholds_active: dict[str, float]

    # Input signal snapshot — for future threshold calibration.
    # None: unknown at decision time, stored as NULL (OW-M2, ADR-0069 §4α).
    acwr: float | None
    tsb_value: float | None
    readiness_score: float
    glycogen_debt: float
    afi_value: float | None
    athlete_profile_id: str = "owner"

    # Outcome — filled post-session via record_outcome()
    outcome_rpe: int | None = None
    outcome_completed: bool | None = None
    outcome_session_type_actual: str | None = None
    outcome_notes: str | None = None
    decision_was_followed: bool = True
    override_outcome_exclusion: bool = False
    outcome_independence_ok: bool = True
    algorithm_version_snapshot: dict[str, str] | None = None

    def __post_init__(self) -> None:
        # MA-F3 (D-122): an athlete id that was passed but is empty never becomes
        # the owner's; only the field's default and the legacy "DEFAULT" do.
        if not isinstance(self.athlete_profile_id, str) or not self.athlete_profile_id.strip():
            raise ValueError("GovernanceDecision needs a non-empty athlete_profile_id")
        if self.athlete_profile_id == "DEFAULT":
            self.athlete_profile_id = "owner"


def _classify_lock_cause(
    locks_applied: list[str],
    acwr: float | None,
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
        return "CLEAN"

    # Proxy heuristic: if ACWR or readiness are implausible values that
    # default-replaced would produce, suspect a data pipeline problem.
    data_signals = []
    if acwr is None:
        data_signals.append("acwr_missing")
    elif acwr <= 0.0 or acwr > 3.0:
        data_signals.append("acwr_out_of_range")
    if readiness_score <= 0.0:
        data_signals.append("readiness_zero")

    # CS_CONFIDENCE_LOCK is by definition a data availability problem:
    # the model has insufficient calibration history, not a training excess.
    if "CS_CONFIDENCE_LOCK" in locks_applied:
        data_signals.append("cs_calibration_missing")

    if data_signals:
        return "DATA_PROBLEM"

    return "TRAINING_LOGIC"

def _parse_iso_date(value: str) -> datetime | None:
    """Return parsed YYYY-MM-DD date or None when invalid."""
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def _outcome_is_independent(decision_date: str, outcome_date: str) -> bool:
    """Independence guardrail: reuse only outcomes outside confounding window."""
    decision_dt = _parse_iso_date(decision_date)
    outcome_dt = _parse_iso_date(outcome_date)
    if decision_dt is None or outcome_dt is None:
        return False
    delta_days = (outcome_dt.date() - decision_dt.date()).days
    return delta_days >= thresholds.OUTCOME_INDEPENDENCE_WINDOW_DAYS


_SCIENCE_MODULE_NAMES = [
    "acwr_engine", "adaptive_memory", "adaptive_priority_lock",
    "automated_periodization", "autonomic_engine", "biomechanics",
    "critical_speed", "data_sanity", "data_trust", "drift_engine",
    "durability_engine", "efficiency_engine", "fatigue_engine",
    "glycogen_model", "governance_contracts", "governance_engine",
    "hrv_engine", "injury_risk_model", "intensity_governor",
    "lactate_logic", "load_prediction_shadow", "ml_safety",
    "outcome_tracker", "override_signal", "physiological_bounds",
    "rcp_engine", "readiness_engine", "trimp_engine",
    "tsb_engine", "volume_load_gauge",
]


def _algorithm_version_snapshot() -> dict[str, str]:
    """Collect MODULE_VERSION from all titan/science modules for calibration provenance."""
    import importlib

    snapshot: dict[str, str] = {}
    for mod_name in _SCIENCE_MODULE_NAMES:
        try:
            mod = importlib.import_module(f"titan.science.{mod_name}")
            snapshot[mod_name] = getattr(mod, "MODULE_VERSION", "MISSING")
        except Exception:
            snapshot[mod_name] = "IMPORT_ERROR"
    return snapshot


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

    def __init__(self, db: DatabaseManager | None = None, athlete_id: str = "owner") -> None:
        self._db = db
        self._athlete_id = athlete_id
        self._decisions: list[GovernanceDecision] = []
        if self._db is not None:
            self._hydrate_from_db()

    def _hydrate_from_db(self) -> None:
        """Restore in-memory tracker state from persisted governance outcomes."""
        try:
            persisted = self._db.get_governance_decisions(athlete_id=self._athlete_id)
        except Exception as exc:
            _log.warning("OutcomeTracker DB hydration failed: %s", exc)
            return

        self._decisions = [GovernanceDecision(**entry) for entry in persisted]

    # ── Recording ────────────────────────────────────────────────────────────

    def record_decision(
        self,
        session_planned: str,
        session_post_governance: str,
        locks_applied: list[str],
        governance_clean: bool,
        phase: str,
        vlg_color: str,
        apl_result: dict,
        acwr: float | None,
        tsb_value: float | None,
        readiness_score: float,
        glycogen_debt: float,
        athlete_profile_id: str | None = None,
        afi_value: float | None = None,
        date: str | None = None,
        replace_same_day: bool = False,
    ) -> GovernanceDecision:
        """
        Record a governance decision immediately after apply_constraints().

        Returns the GovernanceDecision dataclass for the caller to hold
        if it needs to attach an outcome via record_outcome() later.

        ``replace_same_day``: a morning retry that computed the day again supersedes the
        stored decision of that date in place instead of adding a second row (D-109).
        """
        cause = _classify_lock_cause(
            locks_applied=locks_applied,
            acwr=acwr,
            readiness_score=readiness_score,
        )

        decision = GovernanceDecision(
            date=date or datetime.now(UTC).strftime("%Y-%m-%d"),
            session_planned=str(session_planned),
            session_post_governance=str(session_post_governance),
            locks_applied=list(locks_applied),
            governance_clean=bool(governance_clean),
            phase=str(phase),
            athlete_profile_id=self._athlete_id if athlete_profile_id is None else athlete_profile_id,
            vlg_color=str(vlg_color),
            apl_priority_vector=dict(apl_result.get("priority_vector", {})),
            lock_thresholds_active=dict(apl_result.get("lock_thresholds", {})),
            acwr=float(acwr) if acwr is not None else None,
            tsb_value=float(tsb_value) if tsb_value is not None else None,
            readiness_score=float(readiness_score),
            glycogen_debt=float(glycogen_debt),
            afi_value=float(afi_value) if afi_value is not None else None,
            algorithm_version_snapshot=_algorithm_version_snapshot(),
        )
        replaced = False
        if replace_same_day:
            self._decisions = [
                d for d in self._decisions
                if not (d.date == decision.date and d.athlete_profile_id == decision.athlete_profile_id)
            ]
            replace = getattr(self._db, "replace_governance_decision_on", None)
            replaced = bool(replace(asdict(decision))) if replace is not None else False
        self._decisions.append(decision)
        if self._db is not None and not replaced:
            self._db.save_governance_decision(asdict(decision))

        _log.info(
            json.dumps(
                {
                    "outcome_tracker": "decision_recorded",
                    "date": decision.date,
                    "session_planned": decision.session_planned,
                    "session_post_governance": decision.session_post_governance,
                    "locks_applied": decision.locks_applied,
                    "governance_clean": decision.governance_clean,
                    "phase": decision.phase,
                    "athlete_profile_id": decision.athlete_profile_id,
                    "vlg_color": decision.vlg_color,
                    "cause": cause,
                    "acwr": round(decision.acwr, 3) if decision.acwr is not None else None,
                    "tsb_value": round(decision.tsb_value, 1) if decision.tsb_value is not None else None,
                    "readiness_score": round(decision.readiness_score, 1),
                    "glycogen_debt": round(decision.glycogen_debt, 2),
                },
                default=str,
            )
        )

        return decision

    def record_outcome(
        self,
        date: str,
        rpe: int | None = None,
        completed: bool | None = None,
        actual_session_type: str | None = None,
        notes: str | None = None,
        decision_was_followed: bool | None = None,
        outcome_date: str | None = None,
        athlete_id: str = "owner",
    ) -> bool:
        """
        Attach post-session outcome to the recorded decision for that date.

        Returns True if a matching decision was found and updated.
        Call this after the athlete's session (e.g., from Telegram /post-run command).
        Scoped to athlete_id — decisions belonging to other athletes are never matched.
        """
        for decision in reversed(self._decisions):
            if decision.date == date and decision.athlete_profile_id == athlete_id:
                decision.outcome_rpe = rpe
                decision.outcome_completed = completed
                decision.outcome_session_type_actual = actual_session_type
                decision.outcome_notes = notes

                athlete_deviated = (
                    actual_session_type is not None
                    and actual_session_type.upper() != decision.session_post_governance.upper()
                )
                followed = not athlete_deviated if decision_was_followed is None else decision_was_followed
                effective_outcome_date = outcome_date or date
                independence_ok = (
                    True
                    if outcome_date is None
                    else _outcome_is_independent(
                        decision_date=decision.date,
                        outcome_date=effective_outcome_date,
                    )
                )
                override_exclusion = not followed

                decision.decision_was_followed = bool(followed)
                decision.override_outcome_exclusion = override_exclusion
                decision.outcome_independence_ok = independence_ok
                decision.algorithm_version_snapshot = _algorithm_version_snapshot()

                event = {
                    "outcome_tracker": "outcome_recorded",
                    "date": date,
                    "session_post_governance": decision.session_post_governance,
                    "actual_session": actual_session_type,
                    "athlete_deviated": athlete_deviated,
                    "decision_was_followed": decision.decision_was_followed,
                    "override_outcome_exclusion": decision.override_outcome_exclusion,
                    "outcome_independence_ok": decision.outcome_independence_ok,
                    "outcome_date": effective_outcome_date,
                    "rpe": rpe,
                    "completed": completed,
                    "locks_applied": decision.locks_applied,
                }
                if not independence_ok or override_exclusion:
                    _log.warning(json.dumps({**event, "outcome_tracker": "outcome_guardrail_activated"}, default=str))
                _log.info(json.dumps(event, default=str))
                if self._db is not None:
                    self._db.update_governance_outcome(
                        date=date,
                        rpe=rpe,
                        completed=completed,
                        actual_session_type=actual_session_type,
                        notes=notes,
                        decision_was_followed=decision.decision_was_followed,
                        override_outcome_exclusion=decision.override_outcome_exclusion,
                        outcome_independence_ok=decision.outcome_independence_ok,
                        algorithm_version_snapshot=decision.algorithm_version_snapshot,
                        athlete_id=athlete_id,
                    )
                return True

        _log.warning(
            json.dumps(
                {
                    "outcome_tracker": "outcome_record_miss",
                    "date": date,
                    "note": "No decision found for this date — record_decision() must precede record_outcome()",
                }
            )
        )
        return False

    # ── Query ────────────────────────────────────────────────────────────────

    def get_decisions(
        self,
        date: str | None = None,
        with_outcomes_only: bool = False,
        phase: str | None = None,
        athlete_id: str = "owner",
    ) -> list[GovernanceDecision]:
        """Return stored decisions for athlete_id, optionally filtered further."""
        result = [d for d in self._decisions if d.athlete_profile_id == athlete_id]
        if date:
            result = [d for d in result if d.date == date]
        if phase:
            result = [d for d in result if d.phase.upper() == phase.upper()]
        if with_outcomes_only:
            result = [d for d in result if d.outcome_completed is not None]
        return result

    def get_lock_rate_by_phase(self, athlete_id: str = "owner") -> dict[str, float]:
        """
        Return governance lock rate grouped by training phase for athlete_id.

        Useful for identifying whether a specific phase consistently
        triggers more locks than expected, which may indicate miscalibrated
        thresholds for that phase context.
        """
        by_phase: dict[str, list[bool]] = {}
        for d in self._decisions:
            if d.athlete_profile_id != athlete_id:
                continue
            by_phase.setdefault(d.phase, []).append(not d.governance_clean)
        return {
            phase: round(sum(locked) / len(locked), 3)
            for phase, locked in by_phase.items()
            if locked
        }

    def get_lock_outcome_correlation(
        self, min_samples: int = 3, athlete_id: str = "owner"
    ) -> dict[str, dict]:
        """
        Correlate each lock trigger with downstream completion + RPE outcomes.

        This is a Phase-5 calibration primitive used to identify which gates
        are most strongly associated with session success/failure.
        Scoped to athlete_id — cross-athlete pooling is forbidden here.
        """
        decided = [
            d
            for d in self._decisions
            if d.athlete_profile_id == athlete_id
            and d.outcome_completed is not None
            and d.outcome_independence_ok
            and not d.override_outcome_exclusion
        ]
        if not decided:
            return {}

        lock_names = sorted({lock for d in decided for lock in d.locks_applied})
        correlation: dict[str, dict] = {}

        for lock in lock_names:
            with_lock = [d for d in decided if lock in d.locks_applied]
            without_lock = [d for d in decided if lock not in d.locks_applied]

            if len(with_lock) < min_samples or len(without_lock) < min_samples:
                continue

            completion_with = sum(1 for d in with_lock if d.outcome_completed) / len(with_lock)
            completion_without = sum(1 for d in without_lock if d.outcome_completed) / len(
                without_lock
            )
            rpe_with_values = [d.outcome_rpe for d in with_lock if d.outcome_rpe is not None]
            rpe_without_values = [d.outcome_rpe for d in without_lock if d.outcome_rpe is not None]
            rpe_with = (
                round(sum(rpe_with_values) / len(rpe_with_values), 1) if rpe_with_values else None
            )
            rpe_without = (
                round(sum(rpe_without_values) / len(rpe_without_values), 1)
                if rpe_without_values
                else None
            )

            correlation[lock] = {
                "n_with_lock": len(with_lock),
                "n_without_lock": len(without_lock),
                "completion_with_lock": round(completion_with, 3),
                "completion_without_lock": round(completion_without, 3),
                "completion_delta_pp": round((completion_with - completion_without) * 100, 1),
                "avg_rpe_with_lock": rpe_with,
                "avg_rpe_without_lock": rpe_without,
            }

        return correlation

    # ── Calibration summary ──────────────────────────────────────────────────

    def get_calibration_summary(self, athlete_id: str = "owner") -> dict:
        """
        Compute Phase-1 calibration metrics from recorded decisions + outcomes.

        Phase 1 is coarse aggregate statistics. Accurate threshold calibration
        requires ≥ 30 outcome-paired decisions and a DB-backed accumulation cycle.
        Scoped to athlete_id — cross-athlete pooling is forbidden.

        Returns a structured dict safe to log or display in Telegram /stats.
        """
        athlete_decisions = [d for d in self._decisions if d.athlete_profile_id == athlete_id]
        n_total = len(athlete_decisions)
        decided = [d for d in athlete_decisions if d.outcome_completed is not None]
        reusable = [
            d
            for d in decided
            if d.outcome_independence_ok and not d.override_outcome_exclusion
        ]
        n_with_outcome = len(decided)

        if n_with_outcome == 0:
            return {
                "status": "NO_OUTCOMES_YET",
                "n_decisions": n_total,
                "n_with_outcome": 0,
                "note": (
                    "Call record_outcome() after each session to enable calibration analytics."
                ),
            }

        n_locked = sum(1 for d in reusable if not d.governance_clean)
        n_completed = sum(1 for d in reusable if d.outcome_completed)
        n_deviated = sum(
            1
            for d in reusable
            if d.outcome_session_type_actual
            and d.outcome_session_type_actual.upper() != d.session_post_governance.upper()
        )
        rpe_values = [d.outcome_rpe for d in reusable if d.outcome_rpe is not None]
        avg_rpe = round(sum(rpe_values) / len(rpe_values), 1) if rpe_values else None

        n_reusable = len(reusable)
        lock_rate = round(n_locked / n_reusable, 3) if n_reusable else None
        completion_rate = round(n_completed / n_reusable, 3) if n_reusable else None
        athlete_override_rate = round(n_deviated / n_reusable, 3) if n_reusable else None

        n_lock_fired = sum(
            1 for d in athlete_decisions
            if d.locks_applied and d.outcome_completed is not None
        )
        n_fp = sum(
            1 for d in athlete_decisions
            if d.locks_applied
            and d.outcome_completed is not None
            and bool(d.outcome_completed)
            and not bool(d.decision_was_followed)
        )
        false_positive_rate = round(n_fp / n_lock_fired, 3) if n_lock_fired >= 5 else 0.0

        n_no_lock = sum(
            1 for d in athlete_decisions
            if not d.locks_applied and d.outcome_completed is not None
        )
        n_fn = sum(
            1 for d in athlete_decisions
            if not d.locks_applied
            and d.outcome_completed is not None
            and not bool(d.outcome_completed)
        )
        false_negative_rate = round(n_fn / n_no_lock, 3) if n_no_lock >= 5 else 0.0

        calibration_ready = n_reusable >= max(30, thresholds.CALIBRATION_MIN_OUTCOME_COUNT)
        lock_outcome_correlation = self.get_lock_outcome_correlation(athlete_id=athlete_id)

        return {
            "status": "CALIBRATION_AVAILABLE" if calibration_ready else "ACCUMULATING",
            "n_decisions": n_total,
            "n_with_outcome": n_with_outcome,
            "n_reusable_outcomes": n_reusable,
            "n_excluded_outcomes": n_with_outcome - n_reusable,
            "governance_lock_rate": lock_rate,
            "completion_rate": completion_rate,
            "false_positive_rate": false_positive_rate,
            "false_negative_rate": false_negative_rate,
            "athlete_override_rate": athlete_override_rate,
            "avg_rpe_when_completed": avg_rpe,
            "lock_rate_by_phase": self.get_lock_rate_by_phase(athlete_id=athlete_id),
            "lock_outcome_correlation": lock_outcome_correlation,
            "heuristic_promotion_candidates": self._get_heuristic_promotion_candidates(
                lock_outcome_correlation
            ),
            "moderate_promotion_candidates": self._get_moderate_promotion_candidates(
                lock_outcome_correlation
            ),
            "calibration_note": (
                "Ready for threshold calibration review."
                if calibration_ready
                else f"Accumulate {max(30, thresholds.CALIBRATION_MIN_OUTCOME_COUNT) - n_reusable} more reusable "
                f"outcome-paired sessions before interpreting rates. Outcomes with "
                f"override or failed independence checks are excluded from calibration reuse."
            ),
        }

    def check_calibration_diversity(self, athlete_id: str = "owner") -> bool:
        """
        Per-athlete calibration diversity gate (ADR-0033 L3-B).

        Returns True only when the athlete's outcome-paired dataset is
        large and diverse enough for threshold calibration review.
        Gate criteria:
          - ≥ 30 reusable paired decision→outcome records for athlete_id
          - ≥ 3 distinct session types in those records
          - No single session type accounts for > 60% of the dataset
        Cross-athlete pooling is explicitly forbidden.
        """
        from collections import Counter

        reusable = [
            d
            for d in self._decisions
            if d.athlete_profile_id == athlete_id
            and d.outcome_completed is not None
            and d.outcome_independence_ok
            and not d.override_outcome_exclusion
        ]
        n = len(reusable)
        if n < 30:  # noqa: PLR2004
            _log.warning(
                json.dumps(
                    {
                        "outcome_tracker": "calibration_diversity_insufficient",
                        "athlete_id": athlete_id,
                        "reason": "insufficient_records",
                        "n_records": n,
                        "required": 30,
                    }
                )
            )
            return False

        type_counts = Counter(d.session_post_governance for d in reusable)
        distinct_types = len(type_counts)
        max_fraction = max(type_counts.values()) / n

        if distinct_types < 3 or max_fraction > 0.60:  # noqa: PLR2004
            _log.warning(
                json.dumps(
                    {
                        "outcome_tracker": "calibration_diversity_insufficient",
                        "athlete_id": athlete_id,
                        "reason": "insufficient_diversity",
                        "distinct_types": distinct_types,
                        "max_type_fraction": round(max_fraction, 3),
                    }
                )
            )
            return False

        return True

    def get_calibration_analytics(self, athlete_id: str = "owner") -> list[dict]:
        """
        Return all decision records for athlete_id as dicts for calibration review.

        Cross-athlete pooling is explicitly forbidden — only records belonging
        to athlete_id are returned.
        """
        return [asdict(d) for d in self._decisions if d.athlete_profile_id == athlete_id]

    def _get_heuristic_promotion_candidates(
        self,
        lock_outcome_correlation: dict[str, dict],
    ) -> list[dict]:
        """
        Build candidate list for HEURISTIC → MODERATE promotion review.

        A candidate is surfaced only when:
          - the lock maps to a HEURISTIC parameter,
          - there are at least 5 sessions in both with-lock / without-lock groups,
          - absolute completion delta is at least 8 percentage points.
        """
        candidates: list[dict] = []

        for lock_name, params in _LOCK_TO_HEURISTIC_PARAMETERS.items():
            metrics = lock_outcome_correlation.get(lock_name)
            if not metrics:
                continue

            n_with = int(metrics.get("n_with_lock", 0) or 0)
            n_without = int(metrics.get("n_without_lock", 0) or 0)
            completion_delta_pp = float(metrics.get("completion_delta_pp", 0.0) or 0.0)

            if n_with < 5 or n_without < 5 or abs(completion_delta_pp) < 8.0:
                continue

            for parameter in params:
                evidence = get_evidence(parameter)
                if evidence is None or evidence.evidence_level != "HEURISTIC":
                    continue

                candidates.append(
                    {
                        "parameter": parameter,
                        "trigger_lock": lock_name,
                        "n_with_lock": n_with,
                        "n_without_lock": n_without,
                        "completion_delta_pp": round(completion_delta_pp, 1),
                        "recommendation": (
                            "Review for HEURISTIC→MODERATE promotion with ADR + EvidenceRegistry update."
                        ),
                    }
                )

        return sorted(candidates, key=lambda x: abs(x["completion_delta_pp"]), reverse=True)

    def _get_moderate_promotion_candidates(
        self,
        lock_outcome_correlation: dict[str, dict],
    ) -> list[dict]:
        """
        Build candidate list for MODERATE → STRONG promotion review.

        A candidate is surfaced only when:
          - the lock maps to a MODERATE parameter,
          - there are at least 8 sessions in both with-lock / without-lock groups,
          - absolute completion delta is at least 10 percentage points,
          - lock behavior appears in at least 2 distinct phases,
          - lock behavior appears in at least 2 distinct athlete profiles.
        """
        candidates: list[dict] = []

        for lock_name, params in _LOCK_TO_MODERATE_PARAMETERS.items():
            metrics = lock_outcome_correlation.get(lock_name)
            if not metrics:
                continue

            n_with = int(metrics.get("n_with_lock", 0) or 0)
            n_without = int(metrics.get("n_without_lock", 0) or 0)
            completion_delta_pp = float(metrics.get("completion_delta_pp", 0.0) or 0.0)

            with_lock_phases = {
                d.phase
                for d in self._decisions
                if d.outcome_completed is not None and lock_name in d.locks_applied
            }
            phase_replication_count = len(with_lock_phases)
            with_lock_profiles = {
                d.athlete_profile_id
                for d in self._decisions
                if d.outcome_completed is not None and lock_name in d.locks_applied
            }
            profile_replication_count = len(with_lock_profiles)

            if (
                n_with < 8
                or n_without < 8
                or abs(completion_delta_pp) < 10.0
                or phase_replication_count < 2
                or profile_replication_count < 2
            ):
                continue

            for parameter in params:
                evidence = get_evidence(parameter)
                if evidence is None or evidence.evidence_level != "MODERATE":
                    continue

                candidates.append(
                    {
                        "parameter": parameter,
                        "trigger_lock": lock_name,
                        "n_with_lock": n_with,
                        "n_without_lock": n_without,
                        "completion_delta_pp": round(completion_delta_pp, 1),
                        "phase_replication_count": phase_replication_count,
                        "profile_replication_count": profile_replication_count,
                        "recommendation": (
                            "Review for MODERATE→STRONG promotion after replicated cross-profile "
                            "and EvidenceRegistry update."
                        ),
                    }
                )

        return sorted(candidates, key=lambda x: abs(x["completion_delta_pp"]), reverse=True)

    # ── Calibration cycle ────────────────────────────────────────────────────

    def run_calibration_cycle(
        self,
        athlete_id: str,
        threshold_adapter: ThresholdAdapter,
        base_values: dict[str, float],
    ) -> dict[str, object]:
        """
        Execute one calibration cycle: evaluate summary rates → propose δT updates.

        Hard-stop gates are never adapted (delegated to ThresholdAdapter.is_hard_stop_gate).
        Returns a structured event record that is the authoritative output of this cycle;
        no additional side-effect emit is performed beyond ThresholdAdapter's DB write.
        """
        if not self.check_calibration_diversity(athlete_id):
            return {
                "status": "INSUFFICIENT_DIVERSITY",
                "athlete_id": athlete_id,
                "adaptations_attempted": 0,
                "adaptations_applied": 0,
                "circuit_breaker_active": False,
            }

        if threshold_adapter.is_circuit_breaker_active():
            return {
                "status": "CIRCUIT_BREAKER_ACTIVE",
                "athlete_id": athlete_id,
                "adaptations_attempted": 0,
                "adaptations_applied": 0,
                "circuit_breaker_active": True,
            }

        summary = self.get_calibration_summary(athlete_id)
        if summary["status"] != "CALIBRATION_AVAILABLE":
            return {
                "status": "ACCUMULATING",
                "athlete_id": athlete_id,
                "adaptations_attempted": 0,
                "adaptations_applied": 0,
                "circuit_breaker_active": False,
            }

        false_positive_rate = summary.get("false_positive_rate", 0.0)
        false_negative_rate = summary.get("false_negative_rate", 0.0)

        _FALSE_POS_THRESHOLD = 0.30
        _FALSE_NEG_THRESHOLD = 0.15

        attempted = 0
        applied = 0

        for threshold_name, base_value in base_values.items():
            if threshold_adapter.is_hard_stop_gate(threshold_name):
                continue
            direction = None
            if false_positive_rate > _FALSE_POS_THRESHOLD:
                direction = +1.0
            elif false_negative_rate > _FALSE_NEG_THRESHOLD:
                direction = -1.0
            if direction is not None:
                attempted += 1
                result = threshold_adapter.propose_adaptation(
                    threshold_name, direction, base_value
                )
                if result:
                    applied += 1

        return {
            "status": "CALIBRATION_COMPLETE",
            "athlete_id": athlete_id,
            "adaptations_attempted": attempted,
            "adaptations_applied": applied,
            "false_positive_rate": false_positive_rate,
            "false_negative_rate": false_negative_rate,
            "circuit_breaker_active": False,
            "thresholds_evaluated": list(base_values.keys()),
            "timestamp": datetime.now(UTC).isoformat(),
        }

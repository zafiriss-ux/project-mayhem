"""
Daily Coach - Main Orchestrator (v5.7 Closed-Loop Sovereign)
Orchestration order:
1.  Sync Garmin data
2.  Persist data to database (activities + daily metrics)
3.  HRV + HRR live update
4.  AFI computation (autonomic fusion)
5.  CS thermal adjustment (kinetic layer)
6.  Glycogen debt update (metabolic layer)
7.  Composite readiness (AFI + TSB + glycogen)
8.  Today's planned session (weekly plan)
9.  Governance hard gates  ← LAST before Telegram
10. Optimal running time
11. Nutrition plan
12. Send morning message via Telegram (LLM explains, kernel decides)

Architectural Boundary:
  The LLM (Telegram message) receives ONLY processed results.
  It never computes readiness, intensity zones, or session type.
  governance.apply_constraints() is the final, non-bypassable gate.
"""

import contextlib
import dataclasses
import json
import logging
import sqlite3
import threading
from datetime import UTC, datetime
from time import monotonic
from typing import TYPE_CHECKING, Any

from titan.core.structured_events import EventSeverity, structured_event_payload

if TYPE_CHECKING:
    from collections.abc import Callable

from titan.config.evidence_registry import get_metrics_under_review
from titan.config.thresholds import (
    CTL_DECAY_DAYS,
    ESI_DEW_POINT_FALLBACK_C,
    ESI_EXTREME_MIN,
    ESI_HIGH_MIN,
    ESI_MODERATE_MIN,
    ESI_PACE_ADJUSTMENT_EXTREME_SEC_PER_KM,
    ESI_PACE_ADJUSTMENT_HIGH_SEC_PER_KM,
    ESI_PACE_ADJUSTMENT_MODERATE_SEC_PER_KM,
    GARMIN_DATA_MAX_AGE_HOURS,
    HRV_DRIFT_THRESHOLD_MS,
)
from titan.core.database import DatabaseManager
from titan.integrations.biometric_router import BiometricRouter, ManualEntryAdapter
from titan.orchestration.coaching_pipeline import AthleteCoachingContext, coaching_pipeline
from titan.orchestration.contracts import (
    DailyCoachContext,
    DailyCoachContextContract,
    DailyCoachingPayload,
    DecisionResult,
    GarminSyncResult,
    PlannedEffect,
    TodaySessionPlan,
)
from titan.orchestration.engine_registry import EngineRegistry
from titan.science.adaptive_priority_lock import AdaptivePriorityLock
from titan.science.autonomic_engine import AutonomicFusionEngine
from titan.science.biomechanics import BiomechanicsEngine
from titan.science.critical_speed import CriticalSpeedTracker
from titan.science.data_sanity import DataSanityChecker, has_rejects, has_warns
from titan.science.data_trust import (
    DataTrustLevel,
    combine_trust_reports,
    evaluate_garmin_trust,
    evaluate_weather_trust,
)
from titan.science.durability_engine import DurabilityEngine
from titan.science.fatigue_engine import FatigueEngine
from titan.science.glycogen_model import GlycogenDebtAccumulator
from titan.science.governance_engine import GovernanceEngine
from titan.science.intensity_governor import IntensityGovernor
from titan.science.lactate_logic import LactateLogic
from titan.science.outcome_tracker import OutcomeTracker
from titan.science.volume_load_gauge import VolumeLoadGauge

_log = logging.getLogger(__name__)

DATA_MISSING = "DATA_MISSING"
ENGINE_ERROR = "ENGINE_ERROR"
PERSIST_ERROR = "PERSIST_ERROR"
DELIVERY_ERROR = "DELIVERY_ERROR"


_DEGRADED_ALERT_THRESHOLD_HOURS = 24


class DegradedModeTracker:
    """Track how long the system has been in degraded mode per failure type.

    On each morning routine, callers report which degraded flags are active.
    If any flag has been active for >= ``_DEGRADED_ALERT_THRESHOLD_HOURS``,
    a critical alert is fired via the provided callable.

    State is persisted to the ``degraded_mode_state`` SQLite table so that
    degradation timers survive process restarts (HD-06 / OBS-039).
    """

    def __init__(self, db: "DatabaseManager | None" = None) -> None:
        self._db = db
        self._degraded_since: dict[str, datetime] = {}
        if db is not None:
            self._hydrate_from_db()

    def _hydrate_from_db(self) -> None:
        """Restore degradation timers from the database on startup."""
        try:
            rows = self._db.get_all_degraded_mode_states()  # type: ignore[union-attr]
        except Exception:
            return
        for failure_type, ts_str in rows:
            with contextlib.suppress(ValueError, TypeError):
                self._degraded_since[failure_type] = datetime.fromisoformat(ts_str)
        if self._degraded_since:
            _daily_coach_event(
                "degraded_mode_restored",
                severity=EventSeverity.INFO,
                failure_types=list(self._degraded_since.keys()),
                count=len(self._degraded_since),
            )

    def _persist_state(self, failure_type: str, degraded_since: datetime | None) -> None:
        """Upsert or delete a single failure_type row via DatabaseManager."""
        if self._db is None:
            return
        try:
            if degraded_since is not None:
                self._db.upsert_degraded_mode_state(failure_type, degraded_since.isoformat())
            else:
                self._db.delete_degraded_mode_state(failure_type)
        except Exception as exc:
            _daily_coach_event(
                "degraded_mode_persist_failed",
                severity=EventSeverity.WARNING,
                failure_type=failure_type,
                error_class=type(exc).__name__,
            )

    def update(
        self,
        flags: dict[str, bool],
        alert_fn: "Callable[[str], None]",
    ) -> None:
        """Update tracker state and fire alerts for prolonged degraded periods.

        Args:
            flags: Mapping of failure_type → bool (True = currently degraded).
            alert_fn: Callable that sends an alert string to the operator.
        """
        now = datetime.now(UTC)
        for name, is_degraded in flags.items():
            if is_degraded:
                if name not in self._degraded_since:
                    self._degraded_since[name] = now
                    self._persist_state(name, now)
                else:
                    elapsed_hours = (now - self._degraded_since[name]).total_seconds() / 3600
                    if elapsed_hours >= _DEGRADED_ALERT_THRESHOLD_HOURS:
                        try:
                            alert_fn(
                                f"⚠️ TITAN degraded for >{int(elapsed_hours)}h — "
                                f"{name} unresolved. Check credentials/connectivity."
                            )
                        except Exception as exc:
                            _daily_coach_event(
                                "degraded_alert_failed",
                                failure_type=name,
                                error_class=type(exc).__name__,
                            )
                        # Reset timer after alerting to avoid alert storm
                        self._degraded_since[name] = now
                        self._persist_state(name, now)
            else:
                self._degraded_since.pop(name, None)
                self._persist_state(name, None)

    def get_degraded_since(self) -> dict[str, str | None]:
        """Return ISO 8601 timestamps per failure type, or None when healthy."""
        result: dict[str, str | None] = {}
        for name, ts in self._degraded_since.items():
            result[name] = ts.isoformat()
        return result


class PersistenceFailure(Exception):
    """Raised by _persist_garmin_data() when the DB transaction rolls back.

    Carries the default metric values so the caller can continue in degraded
    conservative mode without re-deriving them.
    """

    def __init__(self, today_rhr: int, today_sleep_score: int, today_sleep_hours: float) -> None:
        super().__init__("DB transaction rolled back — persistence failed")
        self.today_rhr = today_rhr
        self.today_sleep_score = today_sleep_score
        self.today_sleep_hours = today_sleep_hours


def _daily_coach_event(
    action: str,
    *,
    severity: EventSeverity | str = EventSeverity.INFO,
    **fields,
) -> None:
    """Emit a structured orchestration event as a single JSON log line."""
    _log.info(json.dumps(structured_event_payload("daily_coach", action, severity=severity, **fields), default=str))


def _failure_class_for_step(step_number: int, error: Exception) -> str:
    """Map a step failure to the canonical daily coach failure taxonomy."""
    if step_number == 2:
        return PERSIST_ERROR
    if step_number == 12:
        return DELIVERY_ERROR
    if isinstance(error, (KeyError, TypeError, ValueError)):
        return DATA_MISSING
    return ENGINE_ERROR


def _safe_float(value, default: float = 0.0) -> float:
    """Convert value to float safely."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    """Convert value to int safely."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _compute_esi(*, temperature_c: float, dew_point_c: float) -> tuple[str, int]:
    """Compute ESI level and target pace adjustment in sec/km."""
    score = float(temperature_c) + (0.5 * float(dew_point_c))
    if score >= ESI_EXTREME_MIN:
        return "EXTREME", ESI_PACE_ADJUSTMENT_EXTREME_SEC_PER_KM
    if score >= ESI_HIGH_MIN:
        return "HIGH", ESI_PACE_ADJUSTMENT_HIGH_SEC_PER_KM
    if score >= ESI_MODERATE_MIN:
        return "MODERATE", ESI_PACE_ADJUSTMENT_MODERATE_SEC_PER_KM
    return "LOW", 0


def _apply_esi_context_to_session(
    session: dict,
    *,
    esi_level: str,
    esi_pace_adjustment_sec_per_km: int,
) -> dict:
    updated = dict(session)
    updated["esi_level"] = esi_level
    updated["esi_pace_adjustment_sec_per_km"] = esi_pace_adjustment_sec_per_km
    updated["adjusted_target"] = (
        f"+{esi_pace_adjustment_sec_per_km}s/km pace adjustment"
        if esi_pace_adjustment_sec_per_km > 0
        else "No pace adjustment"
    )
    return updated


def _apply_esi_context_to_optimal_time(
    optimal_time: dict,
    *,
    esi_level: str,
    esi_pace_adjustment_sec_per_km: int,
) -> dict:
    updated = dict(optimal_time)
    updated["esi_level"] = esi_level
    updated["esi_pace_adjustment_sec_per_km"] = esi_pace_adjustment_sec_per_km
    updated["adjusted_target"] = (
        f"+{esi_pace_adjustment_sec_per_km}s/km"
        if esi_pace_adjustment_sec_per_km > 0
        else "No adjustment"
    )
    return updated


# Mapping from Garmin activityType.typeKey values to internal session_type constants.
# The act dict produced by GarminSync uses 'activity_type' (not 'session_type'), so
# a direct act.get('session_type', 'EASY') always falls through to the default.
_GARMIN_ACTIVITY_TYPE_MAP: dict[str, str] = {
    "running": "EASY",
    "interval_training": "INTERVALS",
    "tempo_run": "TEMPO",
    "long_run": "LONG_RUN",
}


class DailyCoach:
    """Daily coaching orchestrator with real data persistence."""

    def __init__(
        self,
        garmin_sync,
        weather_api,
        telegram_bot,
        hrv_engine,
        tsb_engine,
        readiness_engine,
        optimal_time_calc,
        nutrition_optimizer,
        weekly_planner,
        db: DatabaseManager | None = None,
        # v5.7 Closed-Loop engines (optional — auto-instantiated if None)
        autonomic_engine: AutonomicFusionEngine | None = None,
        cs_tracker:       CriticalSpeedTracker | None  = None,
        glycogen_accum:   GlycogenDebtAccumulator | None = None,
        governance:       GovernanceEngine | None      = None,
        fatigue_engine:    FatigueEngine | None         = None,
        # v5.7.1: APL governance infrastructure
        apl:              AdaptivePriorityLock | None  = None,
        volume_load_gauge: VolumeLoadGauge | None      = None,
        outcome_tracker:  OutcomeTracker | None        = None,
        # Athlete physiological HRmax — used as zone-boundary ceiling in TRIMP
        # calculation.  Source from AthleteProfile.max_hr (never session peak HR).
        athlete_max_hr: int = 0,
    ):
        self.garmin         = garmin_sync
        # Inject athlete HRmax into the sync instance so _sync_operation can
        # forward it to sync_activities() without changing sync_all()'s signature.
        if hasattr(garmin_sync, "athlete_max_hr"):
            garmin_sync.athlete_max_hr = athlete_max_hr
        self.weather        = weather_api
        self.telegram       = telegram_bot
        self.optimal_time   = optimal_time_calc
        self.nutrition      = nutrition_optimizer
        self.weekly_planner = weekly_planner
        # Database for persistent memory (CTL/ATL/TSB, RHR baselines, etc.)
        # db must always be injected — never create DatabaseManager() inside the pipeline
        # because the caller controls db_dir and the correct file cannot be inferred here.
        if db is None:
            raise TypeError(
                "DailyCoach requires an explicit db= argument. "
                "Pass the DatabaseManager instance created by the caller. "
                "Never instantiate DatabaseManager() inside the pipeline."
            )
        self.db = db
        # v5.7: Closed-Loop science engines — ADR-0058 Phase A: held in EngineRegistry
        self.engines = EngineRegistry(
            tsb=tsb_engine,
            hrv=hrv_engine,
            readiness=readiness_engine,
            autonomic=autonomic_engine or AutonomicFusionEngine(),
            biomechanics=BiomechanicsEngine(),
            durability=DurabilityEngine(),
            fatigue=fatigue_engine or FatigueEngine(),
            lactate=LactateLogic(),
            cs_tracker=cs_tracker or CriticalSpeedTracker(),
            apl=apl or AdaptivePriorityLock(),
        )
        self.glycogen   = glycogen_accum   or GlycogenDebtAccumulator()
        self.governance = governance       or GovernanceEngine()
        # v5.7.1: APL governance infrastructure
        self.vlg            = volume_load_gauge or VolumeLoadGauge()
        self.outcome_tracker = outcome_tracker or OutcomeTracker(db=self.db)
        self.athlete_max_hr = athlete_max_hr
        self._routine_thread: threading.Thread | None = None
        self._routine_started_monotonic: float | None = None
        self._routine_mutex = threading.Lock()
        self._degraded_tracker = DegradedModeTracker(db=self.db)
        self._startup_hydration_confidence: dict[str, bool] = {
            "hrv": False,
            "weight": False,
            "load": False,
            "hrr": False,
            "cs": False,
        }
        self._startup_confidence_applies_next_routine = True
        # Restore in-memory state of science engines from DB on startup
        self._startup_hydration_confidence = self._hydrate_engines_from_db()
        metrics_under_review = get_metrics_under_review()
        if metrics_under_review:
            _daily_coach_event(
                "metrics_under_review",
                metrics=metrics_under_review,
                count=len(metrics_under_review),
            )

    # ═══════════════════════════════════════════════════════════════════════
    # BACKWARD-COMPAT ENGINE PROPERTIES (ADR-0058 Phase A)
    # Getters check instance __dict__ first (for DailyCoach.__new__ test
    # factories), then fall back to self.engines.*.
    # Setters: if engines exists, rebuild via dataclasses.replace(); if not
    # (factory-constructed without __init__), store directly in __dict__.
    # These properties will be removed in a future cleanup phase.
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def tsb(self):
        if 'tsb' in self.__dict__:
            return self.__dict__['tsb']
        return self.engines.tsb

    @tsb.setter
    def tsb(self, value):
        if 'engines' in self.__dict__:
            self.engines = dataclasses.replace(self.engines, tsb=value)
        else:
            self.__dict__['tsb'] = value

    @property
    def hrv(self):
        if 'hrv' in self.__dict__:
            return self.__dict__['hrv']
        return self.engines.hrv

    @hrv.setter
    def hrv(self, value):
        if 'engines' in self.__dict__:
            self.engines = dataclasses.replace(self.engines, hrv=value)
        else:
            self.__dict__['hrv'] = value

    @property
    def readiness(self):
        if 'readiness' in self.__dict__:
            return self.__dict__['readiness']
        return self.engines.readiness

    @readiness.setter
    def readiness(self, value):
        if 'engines' in self.__dict__:
            self.engines = dataclasses.replace(self.engines, readiness=value)
        else:
            self.__dict__['readiness'] = value

    @property
    def autonomic(self):
        if 'autonomic' in self.__dict__:
            return self.__dict__['autonomic']
        return self.engines.autonomic

    @autonomic.setter
    def autonomic(self, value):
        if 'engines' in self.__dict__:
            self.engines = dataclasses.replace(self.engines, autonomic=value)
        else:
            self.__dict__['autonomic'] = value

    @property
    def cs_tracker(self):
        if 'cs_tracker' in self.__dict__:
            return self.__dict__['cs_tracker']
        return self.engines.cs_tracker

    @cs_tracker.setter
    def cs_tracker(self, value):
        if 'engines' in self.__dict__:
            self.engines = dataclasses.replace(self.engines, cs_tracker=value)
        else:
            self.__dict__['cs_tracker'] = value

    @property
    def fatigue(self):
        if 'fatigue' in self.__dict__:
            return self.__dict__['fatigue']
        return self.engines.fatigue

    @fatigue.setter
    def fatigue(self, value):
        if 'engines' in self.__dict__:
            self.engines = dataclasses.replace(self.engines, fatigue=value)
        else:
            self.__dict__['fatigue'] = value

    @property
    def apl(self):
        if 'apl' in self.__dict__:
            return self.__dict__['apl']
        return self.engines.apl

    @apl.setter
    def apl(self, value):
        if 'engines' in self.__dict__:
            self.engines = dataclasses.replace(self.engines, apl=value)
        else:
            self.__dict__['apl'] = value

    # _engine-suffix aliases for external callers that use those names
    @property
    def tsb_engine(self):
        return self.engines.tsb

    @property
    def hrv_engine(self):
        return self.engines.hrv

    @property
    def readiness_engine(self):
        return self.engines.readiness

    @property
    def autonomic_engine(self):
        return self.engines.autonomic

    @property
    def biomechanics_engine(self):
        return self.engines.biomechanics

    @property
    def durability_engine(self):
        return self.engines.durability

    @property
    def fatigue_engine(self):
        return self.engines.fatigue

    @property
    def lactate_engine(self):
        return self.engines.lactate

    @property
    def cs_tracker_engine(self):
        return self.engines.cs_tracker

    @property
    def apl_engine(self):
        return self.engines.apl

    # ═══════════════════════════════════════════════════════════════════════
    # PUBLIC ENTRY POINT
    # ═══════════════════════════════════════════════════════════════════════

    def run_morning_routine(
        self,
        soreness: int | None = None,
        subjective_fatigue_score: int | None = None,
    ) -> bool:
        """Execute complete morning coaching routine.

        Args:
            soreness: Subjective soreness/fatigue score 0-10. Defaults to 5
                (neutral) when not provided. Pass explicitly when calling
                from a UI or Telegram handler that has already collected
                the value interactively.
            subjective_fatigue_score: Explicit fatigue score 0-10. Defaults
                to ``soreness`` when omitted.

        Note:
            This method contains no console I/O. All interactive prompts must
            be handled by the caller (e.g. UI layer, Telegram command handler)
            before invoking this method.
        """
        # Apply neutral defaults — no console I/O in the orchestration core
        if soreness is None:
            soreness = 5  # neutral default for headless / service runs
        soreness = max(0, min(10, int(soreness)))

        if subjective_fatigue_score is None:
            subjective_fatigue_score = soreness
        subjective_fatigue_score = max(0, min(10, int(subjective_fatigue_score)))

        _daily_coach_event(
            "routine_started",
            started_at=datetime.now(UTC).strftime('%Y-%m-%d %H:%M'),
        )

        def _run_step(step_number: int, step_name: str, fn):
            try:
                result = fn()
            except Exception as exc:
                _daily_coach_event(
                    "step_event",
                    step_number=step_number,
                    step_name=step_name,
                    outcome="FAILED",
                    failure_class=_failure_class_for_step(step_number, exc),
                    error_class=type(exc).__name__,
                    error_message=str(exc),
                )
                raise
            else:
                _daily_coach_event(
                    "step_event",
                    step_number=step_number,
                    step_name=step_name,
                    outcome="SUCCESS",
                    failure_class=None,
                )
                return result

        # ── Step 1: Sync Garmin ──────────────────────────────────────────────
        _daily_coach_event("step_started", step_number=1, step_name="sync_garmin")
        garmin_data: GarminSyncResult = _run_step(1, "sync_garmin", self.garmin.sync_all)

        # ── Step 2: Persist to DB ────────────────────────────────────────────
        today_str = datetime.now(UTC).strftime('%Y-%m-%d')
        persistence_degraded = False
        try:
            today_rhr, today_sleep_score, today_sleep_hours = _run_step(
                2,
                "persist_garmin_data",
                lambda: self._persist_garmin_data(garmin_data, today_str),
            )
        except PersistenceFailure as pf:
            today_rhr = pf.today_rhr
            today_sleep_score = pf.today_sleep_score
            today_sleep_hours = pf.today_sleep_hours
            persistence_degraded = True
            _daily_coach_event(
                "persistence_degraded_mode",
                reason="DB transaction rolled back",
                intensity_ceiling="EASY",
            )
            try:
                self.telegram.send_alert(
                    "⚠️ Persistence failure — today's session data was not written to the "
                    "database. Training prescription is conservative (EASY). "
                    "Data will be re-synced on next cycle."
                )
            except Exception as alert_exc:
                _daily_coach_event(
                    "persistence_degraded_alert_failed",
                    error_class=type(alert_exc).__name__,
                    error_message=str(alert_exc),
                )

        sync_status = str(garmin_data.get("status", "ok"))
        total_records = (
            len(garmin_data.get("activities", []))
            + len(garmin_data.get("sleep", []))
            + len(garmin_data.get("hrv", []))
            + len(garmin_data.get("weight", []))
        )
        sync_ok = sync_status != "timeout_cancelled" and total_records > 0
        sync_error_class = (
            "GARMIN_TIMEOUT" if sync_status == "timeout_cancelled"
            else ("GARMIN_EMPTY_SYNC" if total_records == 0 else None)
        )
        self.db.record_sync_outcome(
            source="garmin",
            attempted_at=datetime.now(tz=UTC),
            success=sync_ok,
            error_class=sync_error_class,
        )
        if sync_error_class == "GARMIN_EMPTY_SYNC":
            _daily_coach_event(
                "garmin_sync_empty",
                severity=EventSeverity.WARNING,
                activities=len(garmin_data.get("activities", [])),
                sleep=len(garmin_data.get("sleep", [])),
                hrv=len(garmin_data.get("hrv", [])),
                weight=len(garmin_data.get("weight", [])),
                detail="Garmin sync returned zero records across all data types; staleness gate will evaluate.",
            )

        garmin_data_stale = False
        hours_since_success = GARMIN_DATA_MAX_AGE_HOURS + 1
        garmin_sync_state = self.db.get_last_sync_outcome("garmin") or {}
        last_success_ts = garmin_sync_state.get("last_success_ts")
        if isinstance(last_success_ts, datetime):
            hours_since_success = (datetime.now(tz=UTC) - last_success_ts.astimezone(UTC)).total_seconds() / 3600
            if hours_since_success > GARMIN_DATA_MAX_AGE_HOURS:
                garmin_data_stale = True
                _daily_coach_event(
                    "garmin_data_stale",
                    severity="CRITICAL",
                    hours_since_last_success=round(hours_since_success, 2),
                    max_age_hours=GARMIN_DATA_MAX_AGE_HOURS,
                    last_error_class=garmin_sync_state.get("last_error_class"),
                )
                try:
                    self.telegram.send_structured_alert(
                        event_type="garmin_data_stale",
                        lock_code="GARMIN_DATA_STALE",
                        message=(
                            "Garmin data is stale (>26h since last successful sync). "
                            "Training prescription is conservative (EASY maintenance)."
                        ),
                    )
                except Exception as alert_exc:
                    _daily_coach_event(
                        "garmin_staleness_alert_failed",
                        error_class=type(alert_exc).__name__,
                        error_message=str(alert_exc),
                    )

        garmin_trust = evaluate_garmin_trust(
            data_age_hours=hours_since_success,
            sync_status=sync_status,
            quality_flags=list(garmin_data.get("quality_flags", [])),
        )
        garmin_report_payload = {k: v for k, v in garmin_trust.to_payload().items() if k != 'checked_at'}

        # ── Step 3: Feed live HRV + HRR into engines ────────────────────────
        def _step3_feed_hrv_hrr() -> None:
            if garmin_data.get('hrv'):
                for entry in garmin_data['hrv']:
                    self.hrv.add_hrv_measurement(entry['date'], entry['rmssd'])
            if garmin_data.get('hrr'):
                for entry in garmin_data['hrr']:
                    hrr60  = _safe_int(entry.get('hrr_60', 0)) or None
                    hrr120 = _safe_int(entry.get('hrr_120', 0))
                    if hrr60:
                        self.autonomic.add_hrr(entry['date'], hrr60, hrr120)
                        self.db.save_hrr(entry['date'], hrr60, hrr120)

        _run_step(3, "feed_hrv_hrr", _step3_feed_hrv_hrr)

        # ── Step 4: AFI — Autonomic Fusion Index ────────────────────────────
        _daily_coach_event("step_started", step_number=4, step_name="compute_afi")
        ln_dev   = self.hrv.calculate_ln_rmssd_deviation(short_days=7, long_days=28)
        hrv_summary   = self.hrv.get_hrv_summary()
        latest_hrv   = _safe_float(hrv_summary.get('latest_hrv'), 0.0)
        baseline_hrv = _safe_float(hrv_summary.get('baseline'), 50.0)
        hrv_pct_above = ((latest_hrv - baseline_hrv) / baseline_hrv * 100) if baseline_hrv else 0.0
        today_hrr60  = (self.autonomic.hrr_log[-1][1] if self.autonomic.hrr_log else None)

        # Sleep depth delta: map Garmin sleep score to -1..+1 (70 = baseline)
        sleep_delta = max(-1.0, min(1.0, (today_sleep_score - 70) / 30))

        def _step4_compute_afi():
            afi_raw_local = self.autonomic.calculate_afi(
                ln_rmssd_deviation=ln_dev,
                hrr_60_today=today_hrr60,
                sleep_depth_delta=sleep_delta,
            )
            afi_final_local = self.autonomic.apply_48h_buffer(afi_raw_local)
            afi_constraints_local = self.autonomic.get_readiness_constraints(
                afi_final_local,
                hrv_pct_above,
                today_hrr60,
            )
            return afi_final_local, afi_constraints_local

        afi_final, afi_constraints = _run_step(4, "compute_afi", _step4_compute_afi)
        _daily_coach_event(
            "afi_computed",
            afi=f"{afi_final:+.3f}",
            archetype=self.cs_tracker.archetype,
        )

        # ── Step 5: TSB + kinetic state ──────────────────────────────────────
        tsb_value, tsb_status = _run_step(5, "calculate_tsb", self.tsb.calculate_tsb)
        today_temp = garmin_data.get('temperature_c') or 20.0
        cs_thermal = self.cs_tracker.apply_thermal(today_temp)

        # ── Step 6: Glycogen debt update ─────────────────────────────────────
        recent_trimp = self._get_recent_trimp(garmin_data.get('activities', []))
        if recent_trimp > 0:
            self.glycogen.update(
                date               = today_str,
                trimp              = recent_trimp,
                time_above_lt2_min = garmin_data.get('time_above_lt2_min', 0),
                dprime_fraction    = garmin_data.get('dprime_fraction', 0.0),
                intra_carb_g       = garmin_data.get('intra_carb_g', 0.0),
                weight_kg          = garmin_data.get('weight_kg', 70.0),
            )
        self.glycogen.overnight_resynthesis(
            sleep_hours       = today_sleep_hours,
            carb_availability = 'MODERATE',
        )
        _run_step(6, "update_glycogen", lambda: self.db.update_glycogen_debt(today_str, self.glycogen.daily_debt))

        # ── Pre-pipeline: baseline RHR (DB read; alert fires here if unavailable) ──
        _daily_coach_event("step_started", step_number=7, step_name="analyze_readiness")
        baseline_rhr = self._get_baseline_rhr(days=7)
        baseline_rhr_for_comparison = baseline_rhr
        if baseline_rhr is None:
            baseline_rhr_for_comparison = float(today_rhr or 50)
            _daily_coach_event(
                "baseline_rhr_degraded_mode",
                today_rhr=today_rhr or 50,
                fallback_baseline_rhr=baseline_rhr_for_comparison,
            )
            try:
                self.telegram.send_alert(
                    title="⚠️ Data Integrity: RHR Baseline Unavailable",
                    message=(
                        "Baseline RHR could not be read from DB.\n"
                        "H3 gate is operating in degraded mode — "
                        "using today's RHR as its own baseline (delta = 0).\n"
                        "Check database health."
                    ),
                    level="warning",
                )
            except Exception as _alert_exc:
                _daily_coach_event(
                    "baseline_rhr_degraded_alert_failed",
                    error_class=type(_alert_exc).__name__,
                    detail=str(_alert_exc),
                )

        # ── Pre-pipeline: read + reset startup confidence flags ───────────────
        startup_hydration_confidence = getattr(
            self,
            "_startup_hydration_confidence",
            {"hrv": False, "weight": False, "load": False, "hrr": False, "cs": False},
        )
        startup_confidence_applies = getattr(self, "_startup_confidence_applies_next_routine", False)
        self._startup_confidence_applies_next_routine = False

        # ── Decision Pipeline (steps 7–11, pure: no DB writes, no Telegram) ──
        context = AthleteCoachingContext(
            athlete_id="default",
            coach=self,
            db=self.db,
            garmin_data=garmin_data,
            soreness=soreness,
            subjective_fatigue_score=subjective_fatigue_score,
            today_rhr=today_rhr,
            today_sleep_score=today_sleep_score,
            today_sleep_hours=today_sleep_hours,
            baseline_rhr_for_comparison=baseline_rhr_for_comparison,
            persistence_degraded=persistence_degraded,
            garmin_data_stale=garmin_data_stale,
            latest_hrv=latest_hrv,
            baseline_hrv=baseline_hrv,
            hrv_summary=hrv_summary,
            afi_final=afi_final,
            afi_constraints=afi_constraints,
            tsb_value=tsb_value,
            tsb_status=tsb_status,
            cs_thermal=cs_thermal,
            garmin_trust=garmin_trust,
            garmin_report_payload=garmin_report_payload,
            startup_hydration_confidence=startup_hydration_confidence,
            startup_confidence_applies=startup_confidence_applies,
            engines=getattr(self, "engines", None),
        )

        # ── Delegated pipeline/effect execution ───────────────────────────────
        return coaching_pipeline(context)

    # ═══════════════════════════════════════════════════════════════════════
    # DECISION PIPELINE (steps 7–11, pure: no DB writes, no Telegram sends)
    # ═══════════════════════════════════════════════════════════════════════

    def _decision_pipeline(  # noqa: PLR0912, PLR0914, PLR0915
        self,
        *,
        garmin_data: GarminSyncResult,
        soreness: int,
        subjective_fatigue_score: int,
        today_rhr: int,
        today_sleep_score: int,
        today_sleep_hours: float,
        baseline_rhr_for_comparison: float,
        persistence_degraded: bool,
        garmin_data_stale: bool,
        latest_hrv: float,
        baseline_hrv: float,
        hrv_summary: dict,
        afi_final: float,
        afi_constraints: dict,
        tsb_value: float,
        tsb_status: str,
        cs_thermal: float | None,
        garmin_trust: Any,
        garmin_report_payload: dict,
        startup_hydration_confidence: dict,
        startup_confidence_applies: bool,
    ) -> DecisionResult:
        """Deprecated compatibility shim — delegates to coaching_pipeline().

        Production path: run_morning_routine → coaching_pipeline().
        This method exists only for test call-sites; do not add logic here.

        Invariant: Read-only db access permitted.
        No db.save_*, no telegram.*, no self.db.transaction() for writes.
        All inputs are pre-computed signals from run_morning_routine() steps 1–6.
        """

        def _run_step(step_number: int, step_name: str, fn):
            try:
                result = fn()
            except Exception as exc:
                _daily_coach_event(
                    "step_event",
                    step_number=step_number,
                    step_name=step_name,
                    outcome="FAILED",
                    failure_class=_failure_class_for_step(step_number, exc),
                    error_class=type(exc).__name__,
                    error_message=str(exc),
                )
                raise
            else:
                _daily_coach_event(
                    "step_event",
                    step_number=step_number,
                    step_name=step_name,
                    outcome="SUCCESS",
                    failure_class=None,
                )
                return result

        # ── Step 7: Readiness ─────────────────────────────────────────────────
        readiness = _run_step(7, "analyze_readiness", lambda: self.readiness.analyze_readiness(
            today_hrv    = latest_hrv,
            baseline_hrv = baseline_hrv,
            today_rhr    = today_rhr or 50,
            baseline_rhr = baseline_rhr_for_comparison,
            sleep_score  = today_sleep_score,
            soreness     = soreness,
        ))
        readiness['score'] = max(0, min(100,
            readiness.get('score', 50) + afi_constraints.get('afi_modifier', 0)
        ))
        _clamp = afi_constraints.get('readiness_clamp')  # None = no clamp applied
        if _clamp is not None:
            readiness['score'] = min(readiness['score'], _clamp)

        fatigue_level, fatigue_tags = self.fatigue.classify_fatigue(
            hr_suppression=bool(garmin_data.get('hr_suppression', False)),
            rpe_mismatch=bool(garmin_data.get('rpe_mismatch', False)),
            pace_hr_divergence=bool(garmin_data.get('pace_hr_divergence', False)),
            soreness=subjective_fatigue_score,
        )

        # ── Step 7.5: Intensity governor (graduated YELLOW/RED gate) ─────────
        ig = IntensityGovernor()

        # ── Step 8: Today's planned session (from weekly plan) ───────────────
        esi_level, esi_pace_adjustment_sec_per_km = _compute_esi(
            temperature_c=_safe_float(garmin_data.get("temperature_c"), 20.0),
            dew_point_c=_safe_float(garmin_data.get("dew_point"), ESI_DEW_POINT_FALLBACK_C),
        )

        _daily_coach_event("step_started", step_number=8, step_name="load_today_session")

        def _load_today_session_with_esi() -> TodaySessionPlan:
            try:
                return self.weekly_planner.get_today_session(
                    esi_level=esi_level,
                    esi_pace_adjustment_sec_per_km=esi_pace_adjustment_sec_per_km,
                )
            except TypeError as exc:
                if "unexpected keyword argument" not in str(exc):
                    raise
                return self.weekly_planner.get_today_session()

        today_session: TodaySessionPlan = _run_step(8, "load_today_session", _load_today_session_with_esi)
        today_session = _apply_esi_context_to_session(
            today_session,
            esi_level=esi_level,
            esi_pace_adjustment_sec_per_km=esi_pace_adjustment_sec_per_km,
        )

        intensity_gate = ig.evaluate({
            'drift_pct': garmin_data.get('drift_pct'),
            'glycogen_debt': self.glycogen.daily_debt,

            'fatigue_level': fatigue_level,

            'acwr': garmin_data.get('acwr'),
            'readiness_score': readiness.get('score'),
            'planned_session': today_session.get('session_type', 'EASY'),
            'planned_volume_pct': today_session.get('volume_pct'),
        })

        # ── Step 9: Feed activities into load engines ─────────────────────
        self._feed_load_engines(garmin_data.get('activities', []))

        # ── Step 9a: VLG + APL priority resolution ────────────────────────
        # Aggregate the three load signals into a unified VLGState, then let
        # the APL resolve phase-aware gate ordering and adaptive thresholds.
        # Both results are injected into the governance context so that
        # GovernanceEngine reads them without any gate logic being altered.
        _acwr_for_vlg = garmin_data.get('acwr')
        _tsb_for_vlg = _safe_float(tsb_value, 0.0)
        vlg_state = self.vlg.resolve(
            tsb_value    = _tsb_for_vlg,
            acwr         = _acwr_for_vlg,
            glycogen_debt = self.glycogen.daily_debt,
        )
        _phase = str(today_session.get('phase', 'BASE') or 'BASE').upper()
        apl_result = self.apl.resolve(
            vlg_state      = vlg_state,
            afi_constraints = afi_constraints,
            phase          = _phase,
            cs_confidence  = _safe_float(getattr(self.cs_tracker, 'confidence', 0.0), 0.0),
        )

        # Capture session type before governance modifies it (for outcome tracking)
        _session_planned = str(today_session.get('session_type', 'EASY')).upper()

        if garmin_data_stale:
            today_session = {**today_session, "session_type": "EASY", "duration_min": min(int(today_session.get("duration_min", 45)), 45)}

        # ── Step 9b: Governance hard gates ──────────────────────────────────
        _daily_coach_event("step_started", step_number=9, step_name="apply_governance")
        # Initial garmin-only data_trust for governance context (weather added after step 10)
        data_trust: dict[str, Any] = {
            "overall": garmin_trust.trust_level.value,
            "reports": [garmin_report_payload],
        }
        context_payload = self._build_daily_coach_context(
            afi_constraints=afi_constraints,
            intensity_gate=intensity_gate,
            readiness_score=_safe_float(readiness.get('score', 50), 50),
            glycogen_debt=self.glycogen.daily_debt,
            fatigue_level=fatigue_level,
            acwr=_acwr_for_vlg,
            days_since_last_vo2=garmin_data.get('days_since_last_vo2'),
            fueling_confirmed=bool(garmin_data.get('fueling_confirmed', False)),
            planned_duration_min=_safe_int(today_session.get('duration_min', 45), 45),
            today_hrv=latest_hrv,
            baseline_hrv=baseline_hrv,
            hrv_std_dev=_safe_float(hrv_summary.get('std_dev'), 0.0),
            today_rhr=today_rhr or 50,
            baseline_rhr=baseline_rhr_for_comparison,
            sleep_score=today_sleep_score,
            subjective_fatigue_score=subjective_fatigue_score,
            tsb_value=_safe_float(tsb_value, 0.0),
            injury_flag=bool(garmin_data.get('injury_flag', False)),
            priority_vector=apl_result.get('priority_vector', {}),
            lock_thresholds=apl_result.get('lock_thresholds', {}),
            data_confidence_low=(
                sum(startup_hydration_confidence.values()) < 3 if startup_confidence_applies else None
            ),
            persistence_degraded=persistence_degraded,
            garmin_data_stale=garmin_data_stale,
            data_trust=data_trust,
        )
        context_payload["esi_level"] = esi_level
        context_payload["esi_pace_adjustment_sec_per_km"] = esi_pace_adjustment_sec_per_km
        context_payload["garmin_data_age_hours"] = garmin_trust.data_age_hours
        context_payload["garmin_data_trust_level"] = garmin_trust.trust_level.value

        # ADR-0055: source arbitration — Garmin preferred; ManualEntry fallback (≥48h stale)
        _today = datetime.now(UTC).strftime("%Y-%m-%d")
        _manual_adapter = ManualEntryAdapter(self.db)
        _router = BiometricRouter(
            garmin_age_hours=garmin_trust.data_age_hours,
            manual_adapter=_manual_adapter,
        )
        _router.get_hrv(_today, garmin_data.get("hrv_rmssd"))
        _router.get_rhr(_today, garmin_data.get("resting_hr"))
        context_payload["biometric_source"] = _router.active_source
        context_payload["biometric_fallback_active"] = _router.using_fallback

        # Compute degraded flags (passed to _effect_runner via decision_trace)
        _data_confidence_low = bool(
            sum(startup_hydration_confidence.values()) < 3 if startup_confidence_applies else False
        )

        today_session = _run_step(9, "apply_governance", lambda: self.governance.apply_constraints(
            session_plan=today_session,
            context=context_payload,
        ))
        if today_session.get('governance_locks_applied'):
            _daily_coach_event(
                "governance_locks_applied",
                locks=today_session['governance_locks_applied'],
            )

        self._ensure_vo2_eligibility_contract(today_session)




        # ── Step 10: Optimal time ────────────────────────────────────────────
        _daily_coach_event("step_started", step_number=10, step_name="calculate_optimal_time")
        def _calculate_optimal_time_with_esi() -> dict:
            try:
                return self.optimal_time.calculate_optimal_time(
                    session_type=today_session.get('session_type', 'EASY'),
                    duration_hours=today_session.get('duration_min', 45) / 60.0,
                    day_offset=0,
                    tsb_value=tsb_value,
                    esi_level=esi_level,
                    esi_pace_adjustment_sec_per_km=esi_pace_adjustment_sec_per_km,
                )
            except TypeError as exc:
                if "unexpected keyword argument" not in str(exc):
                    raise
                return self.optimal_time.calculate_optimal_time(
                    session_type=today_session.get('session_type', 'EASY'),
                    duration_hours=today_session.get('duration_min', 45) / 60.0,
                    day_offset=0,
                    tsb_value=tsb_value,
                )

        optimal_time = _run_step(10, "calculate_optimal_time", _calculate_optimal_time_with_esi)
        optimal_time = _apply_esi_context_to_optimal_time(
            optimal_time,
            esi_level=esi_level,
            esi_pace_adjustment_sec_per_km=esi_pace_adjustment_sec_per_km,
        )
        weather_data_quality = str(optimal_time.get('weather_data_quality', 'live'))
        weather_degraded_mode = weather_data_quality == 'synthetic'
        weather_trust = evaluate_weather_trust(data_quality=weather_data_quality, data_age_hours=0.0)

        overall_trust = combine_trust_reports([garmin_trust, weather_trust])
        weather_report_payload = {k: v for k, v in weather_trust.to_payload().items() if k != 'checked_at'}
        data_trust = {
            'overall': overall_trust.value,
            'reports': [garmin_report_payload, weather_report_payload],
        }

        # ── Step 11: Nutrition ───────────────────────────────────────────────
        _daily_coach_event("step_started", step_number=11, step_name="calculate_nutrition")
        weight_trend   = self.nutrition.analyze_weight_trend()
        current_weight = weight_trend.get('current_weight', 75.0)

        # Push latest weight into nutrition optimizer if Garmin provided it
        if garmin_data.get('weight'):
            latest_w = garmin_data['weight'][-1]
            self.nutrition.add_weight_entry(latest_w['date'], latest_w['weight_kg'])
            current_weight = latest_w['weight_kg']

        nutrition_plan = _run_step(11, "calculate_nutrition", lambda: self.nutrition.calculate_daily_nutrition(
            weight_kg    = current_weight,
            today_session= today_session,
        ))
        if not nutrition_plan:
            _daily_coach_event(
                "slo_alert",
                slo_key="nutrition_plan_missing",
                cause="NUTRITION_PIPELINE",
                session_type=today_session.get("session_type", "EASY"),
            )

        # ── Step 12: Send Telegram message (LLM explains, kernel decided) ────
        _daily_coach_event("step_started", step_number=12, step_name="send_telegram")
        # Glycogen / electrolyte advisory
        glycogen_protocol   = self.glycogen.norwegian_protocol(current_weight)
        electrolyte_alert   = GlycogenDebtAccumulator.electrolyte_guard(
            dew_point_c  = _safe_float(optimal_time.get('dew_point'), 15.0),
            duration_min = today_session.get('duration_min', 45),
            session_type = today_session.get('session_type', 'EASY'),
        )
        governance_report = self.governance.get_governance_report(
            db=self.db, cs_tracker=self.cs_tracker, afi_constraints=afi_constraints
        )

        decision_rationale = today_session.get('decision_rationale', {})
        coaching_data: DailyCoachingPayload = {
            # Session (post-governance)
            'session_type'      : today_session.get('session_type', 'EASY'),
            'duration'          : f"{today_session.get('distance_km', '?')} km",
            'details'           : today_session.get('details', ''),
            'governance_locks'  : today_session.get('governance_locks_applied', []),
            'primary_reason'    : decision_rationale.get('primary_reason', ''),
            'actionable_guidance': decision_rationale.get('actionable_guidance', ''),
            # Timing
            'optimal_time'      : 'N/A' if weather_degraded_mode else optimal_time.get('recommended_time', 'N/A'),
            'dew_point'         : 'N/A' if weather_degraded_mode else optimal_time.get('dew_point', 'N/A'),
            'conditions'        : 'N/A' if weather_degraded_mode else optimal_time.get('quality', 'N/A'),
            'esi_level'         : esi_level,
            'esi_pace_adjustment_sec_per_km': esi_pace_adjustment_sec_per_km,
            'adjusted_target'   : today_session.get('adjusted_target', 'No pace adjustment'),
            # Autonomic / HRV
            'hrv_status'        : hrv_summary.get('trend', 'N/A'),
            'hrv_value'         : round(latest_hrv, 1),
            'hrv_baseline'      : round(baseline_hrv, 1),
            'afi'               : afi_final,
            # Sleep
            'sleep_quality'     : today_sleep_score,
            'sleep_hours'       : round(today_sleep_hours, 1),
            # Readiness (AFI-adjusted)
            'readiness_score'   : readiness.get('score', 'N/A'),
            'subjective_fatigue_score': subjective_fatigue_score,
            'fatigue_level': fatigue_level,
            'fatigue_tags': fatigue_tags,
            # TSB / kinetic
            'tsb'               : round(tsb_value, 1) if tsb_value is not None else 0,
            'tsb_status'        : tsb_status,
            'cs_smoothed'       : round(self.cs_tracker.cs_smoothed, 3) if self.cs_tracker.cs_smoothed else None,
            'cs_thermal'        : round(cs_thermal, 3) if cs_thermal else None,
            'archetype'         : self.cs_tracker.archetype,
            # Metabolic
            'glycogen_debt'     : round(self.glycogen.daily_debt, 1),
            'glycogen_status'   : self.glycogen.status,
            'glycogen_protocol' : glycogen_protocol,
            'electrolyte_alert' : electrolyte_alert,
            # Nutrition
            'nutrition_plan'    : (
                f"{nutrition_plan.get('carbs_g', '?')}g carbs, "
                f"{nutrition_plan.get('protein_g', '?')}g protein"
            ),
            # Governance report (for LLM narrative only)
            'governance_report' : governance_report,
            'intensity_gate_result': today_session.get('intensity_gate_result'),
            'fueling_gate': today_session.get('fueling_gate'),
            'vo2_eligibility': today_session.get('vo2_eligibility'),
            'hrv_stress_context': today_session.get('hrv_stress_context'),
            'data_trust': data_trust,
        }
        if weather_degraded_mode:
            coaching_data['special_note'] = '⚠️ Weather data unavailable — optimal time window omitted'
        elif overall_trust == DataTrustLevel.SUSPECT:
            coaching_data['special_note'] = '⚠️ Some source data is suspect — recommendations remain conservative.'
        if esi_level != "LOW" and not coaching_data.get("actionable_guidance"):
            coaching_data["actionable_guidance"] = (
                f"ESI {esi_level}: adjust pace target by +{esi_pace_adjustment_sec_per_km}s/km."
            )

        # ── Build DecisionResult ─────────────────────────────────────────────
        _readiness_score = _safe_float(readiness.get('score', 50), 50)
        decision_trace: dict[str, Any] = {
            # Minimum required fields (ADR-0018 B2.6)
            "hrv": latest_hrv,
            "tsb": _tsb_for_vlg,
            "acwr": _acwr_for_vlg,
            "lock_codes_active": today_session.get('governance_locks_applied', []),
            "session_planned_pre_governance": _session_planned,
            "locks_applied": today_session.get('governance_locks_applied', []),
            "governance_clean": today_session.get('governance_clean', True),
            "phase": _phase,
            "vlg_color": getattr(vlg_state, 'color', 'GREEN'),
            "afi_value": afi_final,
            "readiness_score": _readiness_score,
            "glycogen_debt": self.glycogen.daily_debt,
            # Extra fields needed by _effect_runner
            "session_post_governance": today_session.get('session_type', 'EASY'),
            "apl_result": apl_result,
            "persistence_degraded": persistence_degraded,
            "garmin_data_stale": garmin_data_stale,
            "data_confidence_low": _data_confidence_low,
        }
        planned_effects: tuple[PlannedEffect, ...] = (
            PlannedEffect(effect_type="record_outcome", payload={}),
            PlannedEffect(effect_type="send_telegram", payload={}),
        )
        return DecisionResult(
            session_plan=today_session,
            coaching_payload=coaching_data,
            planned_effects=planned_effects,
            decision_trace=decision_trace,
            snapshot_at=datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S'),
        )

    # ═══════════════════════════════════════════════════════════════════════
    # EFFECT RUNNER (step 9c + step 12: outcome recording + Telegram delivery)
    # ═══════════════════════════════════════════════════════════════════════

    def _effect_runner(self, result: DecisionResult) -> bool:
        """Execute planned side-effects from the decision pipeline.

        Order: degraded-mode alert check → outcome recording → Telegram delivery.
        Returns True if Telegram delivery succeeded.
        """
        trace = result.decision_trace

        # ── Degraded mode duration tracking (T2-13 + ADR-0050) ───────────────
        self._degraded_tracker.update(
            flags={
                "persistence_degraded": bool(trace.get("persistence_degraded", False)),
                "data_confidence_low": bool(trace.get("data_confidence_low", False)),
                "garmin_data_stale": bool(trace.get("garmin_data_stale", False)),
                # ADR-0050: Garmin API degraded when consecutive failure threshold crossed.
                "garmin_api_degraded": bool(getattr(self.garmin, "is_api_degraded", False)),
            },
            alert_fn=lambda msg: self.telegram.send_alert(msg),
        )

        # ── Dispatch planned effects in order ─────────────────────────────────
        success = True
        for effect in result.planned_effects:
            if effect.effect_type == "record_outcome":
                self.outcome_tracker.record_decision(
                    session_planned=str(trace.get("session_planned_pre_governance", "EASY")),
                    session_post_governance=str(trace.get("session_post_governance", "EASY")),
                    locks_applied=list(trace.get("locks_applied", [])),
                    governance_clean=bool(trace.get("governance_clean", True)),
                    phase=str(trace.get("phase", "BASE")),
                    vlg_color=str(trace.get("vlg_color", "GREEN")),
                    apl_result=dict(trace.get("apl_result", {})),
                    acwr=_safe_float(trace.get("acwr"), 0.0),
                    tsb_value=float(trace.get("tsb", 0.0)),
                    readiness_score=float(trace.get("readiness_score", 50.0)),
                    glycogen_debt=float(trace.get("glycogen_debt", 0.0)),
                    afi_value=float(trace.get("afi_value", 0.0)),
                )

            elif effect.effect_type == "send_telegram":
                _daily_coach_event("step_started", step_number=12, step_name="send_telegram")
                try:
                    delivery_ok = self.telegram.send_daily_coaching(result.coaching_payload)
                except Exception as exc:
                    _daily_coach_event(
                        "step_event",
                        step_number=12,
                        step_name="send_telegram",
                        outcome="FAILED",
                        failure_class=DELIVERY_ERROR,
                        error_class=type(exc).__name__,
                        error_message=str(exc),
                    )
                    raise
                if not delivery_ok:
                    _daily_coach_event(
                        "step_event",
                        step_number=12,
                        step_name="send_telegram",
                        outcome="FAILED",
                        failure_class=DELIVERY_ERROR,
                        error_class="DELIVERY_ERROR",
                        error_message="Telegram delivery returned falsey result",
                    )
                    success = False
                else:
                    _daily_coach_event(
                        "step_event",
                        step_number=12,
                        step_name="send_telegram",
                        outcome="SUCCESS",
                        failure_class=None,
                    )

        if not success:
            _daily_coach_event(
                "slo_alert",
                slo_key="telegram_delivery_failed",
                cause="INTEGRATION_DELIVERY",
                session_type=result.session_plan.get("session_type", "EASY"),
            )
        _daily_coach_event(
            "routine_completed",
            outcome="SUCCESS" if success else "FAILED",
        )
        return success

    # ═══════════════════════════════════════════════════════════════════════
    # PRIVATE HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    @staticmethod
    def _ensure_vo2_eligibility_contract(session_plan: dict) -> None:
        """Normalize VO2 gate payload shape for downstream consumers."""
        vo2 = session_plan.get('vo2_eligibility')
        if not isinstance(vo2, dict):
            return

        failed = vo2.get('failed_conditions', [])
        if not isinstance(failed, list):
            failed = [str(failed)] if failed else []
        vo2['failed_conditions'] = [str(code) for code in failed]

        details = vo2.get('detailed_failed_conditions', [])
        if not isinstance(details, list):
            details = []
        normalized = [d for d in details if isinstance(d, dict) and 'code' in d]
        vo2['detailed_failed_conditions'] = normalized

    def _build_daily_coach_context(
        self,
        *,
        afi_constraints: dict[str, Any],
        intensity_gate: dict[str, Any],
        readiness_score: float,
        glycogen_debt: float,
        fatigue_level: str,
        acwr: float | None,
        days_since_last_vo2: Any,
        fueling_confirmed: bool,
        planned_duration_min: int,
        today_hrv: float,
        baseline_hrv: float,
        hrv_std_dev: float,
        today_rhr: int,
        baseline_rhr: float,
        sleep_score: int,
        subjective_fatigue_score: int,
        tsb_value: float,
        injury_flag: bool,
        priority_vector: dict[str, Any],
        lock_thresholds: dict[str, Any],
        data_confidence_low: bool | None = None,
        persistence_degraded: bool = False,
        garmin_data_stale: bool | None = None,
        data_trust: dict[str, Any] | None = None,
    ) -> DailyCoachContext:
        """Construct typed governance context payload consumed by GovernanceEngine."""
        payload = DailyCoachContextContract(
            db=self.db,
            cs_tracker=self.cs_tracker,
            afi_constraints=afi_constraints,
            intensity_gate_result=intensity_gate,
            readiness_score=readiness_score,
            glycogen_debt=glycogen_debt,
            fatigue_level=fatigue_level,
            acwr=acwr,
            days_since_last_vo2=days_since_last_vo2,
            fueling_confirmed=fueling_confirmed,
            planned_duration_min=planned_duration_min,
            today_hrv=today_hrv,
            baseline_hrv=baseline_hrv,
            hrv_std_dev=hrv_std_dev,
            today_rhr=today_rhr,
            baseline_rhr=baseline_rhr,
            sleep_score=sleep_score,
            subjective_fatigue_score=subjective_fatigue_score,
            tsb_value=tsb_value,
            injury_flag=injury_flag,
            priority_vector=priority_vector,
            lock_thresholds=lock_thresholds,
            garmin_data_stale=garmin_data_stale,
            data_trust=data_trust,
        ).to_payload()
        if data_confidence_low is not None:
            payload["data_confidence_low"] = data_confidence_low
        if persistence_degraded:
            payload["persistence_degraded"] = True
            payload["data_confidence_low"] = True
        return payload

    def _persist_garmin_data(
        self, garmin_data: dict, today_str: str
    ):
        """
        Persist all synced Garmin data to the database.

        Returns:
            (today_rhr, today_sleep_score, today_sleep_hours)
        """
        today_rhr         = 0
        # Conservative default: score 50 → sleep_delta ≈ -0.67, which discourages
        # training when sleep data is absent.  75 was optimistic (sleep_delta +0.17).
        today_sleep_score = 50
        today_sleep_hours = 7.5

        # ── Activities → training_log ─────────────────────────────────────
        activities = garmin_data.get('activities', [])

        # ── Sleep → extract RHR + sleep score ─────────────────────────────
        sleep_entries = garmin_data.get('sleep', [])
        for entry in sleep_entries:
            if not entry:
                continue
            # RHR note: sync_sleep() does NOT emit a restingHeartRate / rhr key.
            # The 'restingHeartRate' key only exists in the legacy raw Garmin API
            # shape (pre-flattening).  When the entry comes from sync_sleep() the
            # rhr variable will be 0 and today_rhr will remain 0 (→ None after
            # physiological validation), which is the correct conservative outcome.
            rhr = entry.get('restingHeartRate') or entry.get('rhr') or 0

            # F-29: prefer flattened 'sleep_score' from sync_sleep() (primary path).
            # Fall back to nested sleepScores for backward-compat with the raw
            # Garmin API shape.  Use explicit None checks so that a None sleep_score
            # (Garmin API did not provide a score) does not accidentally collapse to
            # the 0 sentinel and trigger the raw-key fallback with an empty dict.
            s_val = entry.get('sleep_score')
            if s_val is None:
                score = entry.get('sleepScores', {})
                if isinstance(score, dict):
                    overall = score.get('overall', {})
                    if isinstance(overall, dict):
                        s_val = overall.get('value')
                    else:
                        raw = _safe_float(overall, 0)
                        s_val = raw if raw else None
                else:
                    raw = _safe_float(score, 0)
                    s_val = raw if raw else None

            # F-29: prefer 'total_sleep_hours' from sync_sleep() (already in hours);
            # fall back to seconds-based keys from raw Garmin API shape.
            total_h = entry.get('total_sleep_hours') or 0
            dur_sec = 0 if total_h else (entry.get('sleepTimeSeconds') or entry.get('duration_sec', 0))

            if rhr:
                today_rhr = _safe_int(rhr)
            if s_val is not None:
                today_sleep_score = _safe_int(s_val)
            if total_h:
                today_sleep_hours = _safe_float(total_h)
            elif dur_sec:
                today_sleep_hours = _safe_float(dur_sec) / 3600.0

        # ── HRV → daily_metrics ───────────────────────────────────────────
        hrv_entries = garmin_data.get('hrv', [])
        latest_rmssd = None
        past_hrv_entries: list[dict] = []
        for entry in hrv_entries:
            entry_date = entry.get('date')
            rmssd_val = _safe_float(entry.get('rmssd', 0)) or None
            if entry_date == today_str:
                latest_rmssd = rmssd_val
            elif entry_date and rmssd_val is not None:
                # F-32: collect historical HRV entries for multi-day persistence
                past_hrv_entries.append({'date': entry_date, 'rmssd': rmssd_val})

        # ── Weight → daily_metrics ────────────────────────────────────────
        weight_entries = garmin_data.get('weight', [])
        latest_weight = None
        for entry in weight_entries:
            if entry.get('date') == today_str:
                latest_weight = _safe_float(entry.get('weight_kg', 0)) or None
                break

        from titan.science.physiological_bounds import validate_and_clamp

        phys_inputs = {
            "rhr_bpm": float(today_rhr) if today_rhr > 0 else None,
            "sleep_hours": today_sleep_hours if today_sleep_hours > 0 else None,
            "hrv_ms": latest_rmssd,
            "weight_kg": latest_weight,
        }
        validated_inputs, input_violations = validate_and_clamp(
            phys_inputs,
            "persist_garmin_data",
        )
        for v in input_violations:
            _daily_coach_event(
                "physiological_input_validation_failed",
                field=v.field,
                value=v.value,
                lo=v.lo,
                hi=v.hi,
                violation_action=v.action,
            )

        validated_rhr = validated_inputs["rhr_bpm"]
        today_rhr = int(round(validated_rhr)) if validated_rhr is not None else 0
        today_sleep_hours = validated_inputs["sleep_hours"] or 0.0
        latest_rmssd = validated_inputs["hrv_ms"]
        latest_weight = validated_inputs["weight_kg"]

        _sanity = DataSanityChecker()
        seen_activity_ids: set[str] = set()
        try:
            with self.db.transaction():
                for idx, act in enumerate(activities, start=1):
                    activity_date = act.get('date', today_str)

                    # ── Structural sanity check (ADR-0026 Layer 1) ───────────
                    sanity_violations = _sanity.check_activity(
                        act,
                        context="persist_garmin_data",
                        seen_activity_ids=seen_activity_ids,
                    )
                    if has_rejects(sanity_violations):
                        _daily_coach_event(
                            "activity_persist",
                            activity_index=idx,
                            activity_date=activity_date,
                            outcome="ACTIVITY_SANITY_REJECTED",
                            failure_class=None,
                        )
                        continue
                    activity_quality_flag = "degraded" if has_warns(sanity_violations) else None

                    try:
                        _est_load = act.get('estimated_training_load')
                        _tl_override = int(_est_load) if _est_load else None
                        self.db.save_session(
                            date              = activity_date,
                            session_type      = _GARMIN_ACTIVITY_TYPE_MAP.get(act.get('activity_type', ''), 'EASY'),
                            distance_km       = _safe_float(act.get('distance_km', 0)),
                            duration_sec      = _safe_int(act.get('duration_sec', 0)),
                            avg_hr            = _safe_int(act.get('avg_hr')) or None,
                            max_hr            = _safe_int(act.get('max_hr')) or None,
                            rpe               = act.get('rpe'),
                            training_load     = _tl_override,
                            notes             = act.get('name', ''),
                            garmin_activity_id= act.get('activity_id'),
                            quality_flag      = activity_quality_flag,
                            avg_pace_sec_per_km= _safe_int(act.get('avg_pace_sec_per_km')) or None,
                        )
                        _daily_coach_event(
                            "activity_persist",
                            activity_index=idx,
                            activity_date=activity_date,
                            outcome="ACTIVITY_PERSISTED",
                            failure_class=None,
                        )
                    except Exception as exc:
                        _daily_coach_event(
                            "activity_persist",
                            activity_index=idx,
                            activity_date=activity_date,
                            outcome="ACTIVITY_SKIPPED",
                            failure_class=PERSIST_ERROR,
                            error_class=type(exc).__name__,
                            error_message=str(exc),
                        )
                        raise

                daily_metric_violations = _sanity.check_daily_metrics(
                    {"date": today_str},
                    context="persist_garmin_data",
                )
                if has_rejects(daily_metric_violations):
                    _daily_coach_event(
                        "daily_metrics_persist_failed",
                        date=today_str,
                        error_class="DataSanityViolation",
                        error_message="daily_metrics_rejected",
                    )
                    raise ValueError("daily_metrics_rejected")

                hrv_sanity_violations = []
                if latest_rmssd is not None:
                    hrv_sanity_violations = _sanity.check_hrv(
                        {"date": today_str, "rmssd": latest_rmssd},
                        context="persist_garmin_data",
                    )
                    if has_rejects(hrv_sanity_violations):
                        latest_rmssd = None

                daily_quality_flag = "degraded" if has_warns(daily_metric_violations + hrv_sanity_violations) else None

                self.db.save_daily_metric(
                    date         = today_str,
                    weight       = latest_weight,
                    hrv          = latest_rmssd,
                    rhr          = today_rhr or None,
                    sleep_hours  = today_sleep_hours if today_sleep_hours > 0 else None,
                    sleep_quality= today_sleep_score if today_sleep_score > 0 else None,
                    quality_flag = daily_quality_flag,
                )

                # F-32: persist HRV for all historical days returned by sync_hrv()
                # INSERT OR IGNORE — never overwrite manually entered historical data.
                for past_hrv in past_hrv_entries:
                    past_hrv_sanity = _sanity.check_hrv(
                        {"date": past_hrv['date'], "rmssd": past_hrv['rmssd']},
                        context="persist_garmin_data",
                    )
                    if not has_rejects(past_hrv_sanity):
                        self.db.save_daily_metric_if_missing(
                            date=past_hrv['date'], hrv=past_hrv['rmssd']
                        )

            if activities:
                _daily_coach_event(
                    "activities_persisted",
                    count=len(activities),
                    date=today_str,
                )
            _daily_coach_event(
                "activity_persist",
                activity_index=None,
                activity_date=today_str,
                outcome="DAILY_METRICS_PERSISTED",
                failure_class=None,
            )
            _daily_coach_event("daily_metrics_persisted", date=today_str)
        except Exception as exc:
            _daily_coach_event(
                "activity_persist",
                activity_index=None,
                activity_date=today_str,
                outcome="DAILY_METRICS_SKIPPED",
                failure_class=PERSIST_ERROR,
                error_class=type(exc).__name__,
                error_message=str(exc),
            )
            _daily_coach_event(
                "daily_metrics_persist_failed",
                date=today_str,
                error_class=type(exc).__name__,
                error_message=str(exc),
            )
            raise PersistenceFailure(today_rhr, today_sleep_score, today_sleep_hours) from exc

        return today_rhr, today_sleep_score, today_sleep_hours

    def _get_baseline_rhr(self, days: int = 7) -> float | None:
        """
        Calculate rolling N-day average resting HR from database.
        Returns None if unavailable.
        """
        try:
            return self.db.get_baseline_rhr(days=days)
        except (sqlite3.Error, TypeError, ValueError, KeyError) as exc:
            _daily_coach_event(
                "baseline_rhr_unavailable",
                error_class=type(exc).__name__,
                detail=str(exc),
            )
            return None

    def run_morning_routine_async(self, trigger_source: str = "async_call") -> bool:
        """Schedule ``run_morning_routine`` in a daemon thread.

        Returns False if a routine is already running (lock not acquired),
        True if the routine thread was successfully started.
        """
        acquired = self._routine_mutex.acquire(blocking=False)
        if not acquired:
            _daily_coach_event(
                "morning_routine_skipped",
                trigger_source=trigger_source,
                reason="already_running",
            )
            return False

        def _run_and_release() -> None:
            try:
                self.run_morning_routine()
            finally:
                self._routine_mutex.release()

        t = threading.Thread(
            target=_run_and_release,
            name="DailyCoachRoutine",
            daemon=True,
        )
        self._routine_thread = t
        self._routine_started_monotonic = monotonic()
        t.start()
        return True

    def _get_recent_trimp(self, activities: list[dict]) -> float:
        """
        Extract TRIMP from synced activities for glycogen debt update.
        Falls back to sRPE-based estimate if no Garmin TRIMP available.
        """
        total = 0.0
        for act in activities:
            trimp = _safe_float(act.get('trimp', 0))
            if trimp > 0:
                total += trimp
            else:
                # Fallback: use training_load (sRPE proxy)
                total += _safe_float(act.get('training_load', 0)) * 0.6
        return round(total, 1)

    def _feed_load_engines(self, activities: list[dict]) -> None:
        """
        Refresh TSBEngine from DB after Garmin sync. Clears and reloads 42-day window.
        Uses training_load from DB so CTL/ATL are always current.
        """
        try:
            loads = self.db.get_training_load_history(days=CTL_DECAY_DAYS)
            self.tsb.daily_loads.clear()
            for date_str, load in loads:
                self.tsb.add_daily_load(date_str, float(load))
            _daily_coach_event("load_engines_refreshed", sessions=len(loads))
        except Exception as e:
            _log.exception("load_engines refresh failed: %s", e)
            _daily_coach_event(
                "load_engines_refresh_failed",
                error_class=type(e).__name__,
                error_message=str(e),
            )

    def _hydrate_engines_from_db(self) -> dict[str, bool]:
        """
        Restore in-memory science engine state from the database on startup.

        Prevents 'Digital Amnesia' after restarts:
        - HRVGuidedEngine needs 7-14 days of rMSSD history for baseline
        - NutritionOptimizer needs weight history for trend analysis
        - TSBEngine needs 42-day load history for correct CTL/ATL

        Called automatically at end of __init__.
        """
        with self._routine_mutex:
            return self._hydrate_engines_from_db_locked()

    def _hydrate_engines_from_db_locked(self) -> dict[str, bool]:
        """Inner body of _hydrate_engines_from_db, called under _routine_mutex."""
        _daily_coach_event("hydration_started")
        confidence = {
            "hrv": False,
            "weight": False,
            "load": False,
            "hrr": False,
            "cs": False,
        }

        # 1. HRV history — load 28 days so the HD-01 baseline-drift detector
        #    (window_days=14) has both a recent and an anchor window available.
        _HRV_HISTORY_DAYS = 28
        _DRIFT_WINDOW_DAYS = 14
        try:
            rows = self.db.get_hrv_history(days=_HRV_HISTORY_DAYS)
            self.hrv.hrv_log.clear()
            for date_str, rmssd in reversed(rows):
                self.hrv.add_hrv_measurement(date_str, rmssd)
            confidence["hrv"] = bool(rows)
            _daily_coach_event("hrv_hydrated", records=len(rows))
        except Exception as e:
            _daily_coach_event(
                "hrv_hydration_failed",
                error_class=type(e).__name__,
                error_message=str(e),
            )

        # HRV baseline drift check (HD-01 / INV-06).
        # Compares the mean of the most-recent _DRIFT_WINDOW_DAYS entries against
        # the mean of the earlier anchor window.  Returns False silently when
        # the log has fewer than _DRIFT_WINDOW_DAYS * 2 entries.
        _drift_check = getattr(self.hrv, "check_baseline_drift", None)
        if callable(_drift_check) and _drift_check(window_days=_DRIFT_WINDOW_DAYS):
            _recent = [v for _, v in self.hrv.hrv_log[-_DRIFT_WINDOW_DAYS:]]
            _anchor = [v for _, v in self.hrv.hrv_log[:-_DRIFT_WINDOW_DAYS]]
            if _recent and _anchor:  # guard: both windows must be non-empty
                _delta_ms = round(
                    sum(_recent) / len(_recent) - sum(_anchor) / len(_anchor), 2
                )
                _daily_coach_event(
                    "hrv_baseline_drift_warning",
                    severity=EventSeverity.WARNING,
                    delta_ms=_delta_ms,
                    threshold_ms=HRV_DRIFT_THRESHOLD_MS,
                    window_days=_DRIFT_WINDOW_DAYS,
                )
                confidence["hrv_baseline_drift"] = False

        # 2. Weight history (last 30 days, oldest first)
        try:
            rows = self.db.get_weight_history(days=30)
            for date_str, weight in reversed(rows):
                self.nutrition.add_weight_entry(date_str, weight)
            confidence["weight"] = bool(rows)
            _daily_coach_event("weight_hydrated", records=len(rows))
        except Exception as e:
            _daily_coach_event(
                "weight_hydration_failed",
                error_class=type(e).__name__,
                error_message=str(e),
            )

        # 3. Training load history → TSB engine (42-day window for CTL)
        try:
            loads = self.db.get_training_load_history(days=CTL_DECAY_DAYS)
            self.tsb.daily_loads.clear()
            for date_str, load in loads:
                self.tsb.add_daily_load(date_str, float(load))
            confidence["load"] = bool(loads)
            _daily_coach_event("training_load_hydrated", sessions=len(loads))
        except Exception as e:
            _log.exception("TSB hydration failed: %s", e)
            _daily_coach_event(
                "tsb_hydration_failed",
                error_class=type(e).__name__,
                error_message=str(e),
            )

        # 4. HRR history → Autonomic engine (28-day rolling baseline)
        try:
            hrr_rows = self.db.get_hrr_history(days=28)
            for date_str, hrr_60, hrr_120 in reversed(hrr_rows):
                self.autonomic.add_hrr(date_str, hrr_60, hrr_120 or 0)
            confidence["hrr"] = bool(hrr_rows)
            _daily_coach_event("hrr_hydrated", records=len(hrr_rows))
        except Exception as e:
            _daily_coach_event(
                "hrr_hydration_failed",
                error_class=type(e).__name__,
                error_message=str(e),
            )

        # 5. CS performances → CriticalSpeedTracker
        try:
            from titan.science.critical_speed import CriticalSpeedEngine
            perfs = self.db.get_cs_performances(limit=10)
            confidence["cs"] = bool(perfs)
            if len(perfs) >= 2:
                dist_time = [(dist, t) for _, dist, t in perfs]
                cs_raw, d_prime = CriticalSpeedEngine.estimate_cs_and_dprime(dist_time)
                if cs_raw and d_prime:
                    latest_date = perfs[0][0]
                    self.cs_tracker.update(latest_date, cs_raw, d_prime)
            _daily_coach_event(
                "cs_hydrated",
                performances=len(perfs),
                confidence=f"{self.cs_tracker.confidence:.0%}",
                archetype=self.cs_tracker.archetype,
            )
        except Exception as e:
            _daily_coach_event(
                "cs_hydration_failed",
                error_class=type(e).__name__,
                error_message=str(e),
            )

        # ── Temporal freshness check (ADR-0026 Layer 2) ─────────────────────
        try:

            from titan.config.thresholds import (
                STALE_DATA_HARD_CEILING_HOURS,
                STALE_DATA_WARN_HOURS,
            )

            last_ts = self.db.get_last_garmin_sync_timestamp()
            if last_ts is not None:
                now_utc = datetime.now(tz=UTC)
                hours_since = (now_utc - last_ts).total_seconds() / 3600
                if hours_since > STALE_DATA_HARD_CEILING_HOURS:
                    _daily_coach_event(
                        "data_confidence_low",
                        reason="stale_garmin_data",
                        hours_since_sync=round(hours_since, 1),
                        ceiling_hours=STALE_DATA_HARD_CEILING_HOURS,
                    )
                    confidence["freshness"] = False
                elif hours_since > STALE_DATA_WARN_HOURS:
                    _daily_coach_event(
                        "data_freshness_warn",
                        hours_since_sync=round(hours_since, 1),
                        warn_hours=STALE_DATA_WARN_HOURS,
                    )
                    confidence["freshness"] = True
                else:
                    confidence["freshness"] = True
            else:
                # No data at all — new athlete, not a staleness problem
                confidence["freshness"] = True
        except Exception as e:
            _daily_coach_event(
                "freshness_check_failed",
                error_class=type(e).__name__,
                error_message=str(e),
            )
            confidence["freshness"] = True  # non-fatal; do not degrade on check failure

        self._startup_hydration_confidence = confidence
        _daily_coach_event("startup_hydration_report", confidence=confidence)
        if sum(confidence.values()) < 3:
            _log.warning(
                json.dumps(
                    {
                        "flow": "daily_coach",
                        "action": "startup_low_confidence",
                        "confidence": confidence,
                    },
                    default=str,
                )
            )
        return confidence

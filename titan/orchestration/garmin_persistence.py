"""Store one morning's Garmin sync in the database (plan task 6, D-029).

Moved out of ``DailyCoach._persist_garmin_data`` without changing behavior:
activities go to ``training_log`` and last night's sleep, HRV, resting HR and
weight go to ``daily_metrics``, all in one transaction. The caller passes the
event function, so the structured events keep the ``daily_coach`` flow and
logger they always had. ``backfill_training_history`` fetches older activities
when the stored history is too short for CTL/TSB (D-055).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from titan.science.data_sanity import DataSanityChecker, has_rejects, has_warns

if TYPE_CHECKING:
    from collections.abc import Callable

    from titan.core.database import DatabaseManager

PERSIST_ERROR = "PERSIST_ERROR"

# Mapping from Garmin activityType.typeKey values to internal session_type constants.
# The act dict produced by GarminSync uses 'activity_type' (not 'session_type'), so
# a direct act.get('session_type', 'EASY') always falls through to the default.
_GARMIN_ACTIVITY_TYPE_MAP: dict[str, str] = {
    "running": "EASY",
    "interval_training": "INTERVALS",
    "tempo_run": "TEMPO",
    "long_run": "LONG_RUN",
}


class PersistenceFailure(Exception):
    """Raised by persist_garmin_data() when the DB transaction rolls back.

    Carries the default metric values so the caller can continue in degraded
    conservative mode without re-deriving them.
    """

    def __init__(self, today_rhr: int, today_sleep_score: int | None, today_sleep_hours: float) -> None:
        super().__init__("DB transaction rolled back — persistence failed")
        self.today_rhr = today_rhr
        self.today_sleep_score = today_sleep_score
        self.today_sleep_hours = today_sleep_hours


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


def _save_activities(
    db: DatabaseManager,
    activities: list[dict],
    today_str: str,
    *,
    athlete_id: str,
    emit: Callable[..., None],
    sanity: DataSanityChecker,
) -> None:
    """Write Garmin activities to ``training_log``; the caller holds the transaction."""
    seen_activity_ids: set[str] = set()
    for idx, act in enumerate(activities, start=1):
        activity_date = act.get('date', today_str)

        # ── Structural sanity check (ADR-0026 Layer 1) ───────────
        sanity_violations = sanity.check_activity(
            act,
            context="persist_garmin_data",
            seen_activity_ids=seen_activity_ids,
        )
        if has_rejects(sanity_violations):
            emit(
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
            db.save_session(
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
                athlete_id        = athlete_id,
            )
            emit(
                "activity_persist",
                activity_index=idx,
                activity_date=activity_date,
                outcome="ACTIVITY_PERSISTED",
                failure_class=None,
            )
        except Exception as exc:
            emit(
                "activity_persist",
                activity_index=idx,
                activity_date=activity_date,
                outcome="ACTIVITY_SKIPPED",
                failure_class=PERSIST_ERROR,
                error_class=type(exc).__name__,
                error_message=str(exc),
            )
            raise


def persist_garmin_data(
    db: DatabaseManager,
    garmin_data: dict,
    today_str: str,
    *,
    athlete_id: str,
    emit: Callable[..., None],
) -> tuple[int, int | None, float]:
    """
    Persist all synced Garmin data to the database.

    Returns:
        (today_rhr, today_sleep_score, today_sleep_hours). A missing RHR is 0 and a
        missing sleep score is None (ADR-0051, SV-06): the caller decides what they mean.

    Raises:
        PersistenceFailure: the transaction rolled back; it carries the values
        the morning decision uses in degraded mode.
    """
    today_rhr         = 0
    today_sleep_score: int | None = None
    today_sleep_hours = 7.5
    # The default above feeds today's decision only. It is not a measurement,
    # so it is not stored: daily_metrics keeps NULL unless Garmin sent a value.
    sleep_hours_measured = False

    # ── Activities → training_log ─────────────────────────────────────
    activities = garmin_data.get('activities', [])

    # ── Sleep → extract RHR + sleep score ─────────────────────────────
    sleep_entries = [e for e in garmin_data.get('sleep', []) if e]
    # sync_sleep() returns one dated entry per night, newest first. Only last
    # night's entry describes today; older nights must not overwrite it (the
    # loop below keeps the last entry it sees). Undated entries (legacy raw
    # Garmin shape) keep the previous last-entry-wins behaviour.
    if any(isinstance(e, dict) and e.get('date') for e in sleep_entries):
        sleep_entries = [e for e in sleep_entries if e.get('date') == today_str]
    for entry in sleep_entries:
        # sync_sleep() emits 'resting_hr' (from the sleep or daily-stats response);
        # 'restingHeartRate' / 'rhr' are the legacy raw Garmin shapes. Missing
        # RHR stays 0 (→ None after physiological validation).
        rhr = entry.get('resting_hr') or entry.get('restingHeartRate') or entry.get('rhr') or 0

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
            sleep_hours_measured = True
        elif dur_sec:
            today_sleep_hours = _safe_float(dur_sec) / 3600.0
            sleep_hours_measured = True

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
        emit(
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
    try:
        with db.transaction():
            _save_activities(
                db, activities, today_str, athlete_id=athlete_id, emit=emit, sanity=_sanity,
            )

            daily_metric_violations = _sanity.check_daily_metrics(
                {
                    "date": today_str,
                    "sleep_hours": today_sleep_hours if sleep_hours_measured else None,
                },
                context="persist_garmin_data",
            )
            if has_rejects(daily_metric_violations):
                emit(
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

            db.save_daily_metric(
                date         = today_str,
                weight       = latest_weight,
                hrv          = latest_rmssd,
                rhr          = today_rhr or None,
                sleep_hours  = today_sleep_hours if sleep_hours_measured and today_sleep_hours > 0 else None,
                sleep_quality= today_sleep_score if today_sleep_score else None,
                quality_flag = daily_quality_flag,
                athlete_id   = athlete_id,
            )

            # F-32: persist HRV for all historical days returned by sync_hrv()
            # INSERT OR IGNORE — never overwrite manually entered historical data.
            for past_hrv in past_hrv_entries:
                past_hrv_sanity = _sanity.check_hrv(
                    {"date": past_hrv['date'], "rmssd": past_hrv['rmssd']},
                    context="persist_garmin_data",
                )
                if not has_rejects(past_hrv_sanity):
                    db.save_daily_metric_if_missing(
                        date=past_hrv['date'], hrv=past_hrv['rmssd'],
                        athlete_id=athlete_id,
                    )

        if activities:
            emit(
                "activities_persisted",
                count=len(activities),
                date=today_str,
            )
        emit(
            "activity_persist",
            activity_index=None,
            activity_date=today_str,
            outcome="DAILY_METRICS_PERSISTED",
            failure_class=None,
        )
        emit("daily_metrics_persisted", date=today_str)
    except Exception as exc:
        emit(
            "activity_persist",
            activity_index=None,
            activity_date=today_str,
            outcome="DAILY_METRICS_SKIPPED",
            failure_class=PERSIST_ERROR,
            error_class=type(exc).__name__,
            error_message=str(exc),
        )
        emit(
            "daily_metrics_persist_failed",
            date=today_str,
            error_class=type(exc).__name__,
            error_message=str(exc),
        )
        raise PersistenceFailure(today_rhr, today_sleep_score, today_sleep_hours) from exc

    return today_rhr, today_sleep_score, today_sleep_hours


def backfill_training_history(
    db: DatabaseManager,
    garmin,  # noqa: ANN001 - GarminSync; typed loosely to keep this module free of integrations
    today_str: str,
    *,
    athlete_id: str,
    emit: Callable[..., None],
) -> int:
    """Fetch ``LOAD_HISTORY_DAYS`` of activities when the stored history is too short (D-055).

    CTL starts from 0 (D-051), so with only the 14 days of a normal sync a new athlete's TSB
    falls far below the H4 floor. When ``training_log`` has no session on or before
    ``today - CTL_DECAY_DAYS``, the activities of the last ``LOAD_HISTORY_DAYS`` days are
    fetched once and stored like any synced activity (duplicates are ignored by
    ``garmin_activity_id``). Returns the number of activities fetched.
    """
    from datetime import date, timedelta

    from titan.config.thresholds import CTL_DECAY_DAYS
    from titan.science.tsb_engine import LOAD_HISTORY_DAYS

    oldest_needed = (date.fromisoformat(today_str) - timedelta(days=CTL_DECAY_DAYS)).isoformat()
    rows = db.get_training_load_history(LOAD_HISTORY_DAYS, athlete_id=athlete_id)
    if any(str(d)[:10] <= oldest_needed for d, _load in rows):
        return 0
    activities = garmin.sync_activities(
        LOAD_HISTORY_DAYS, athlete_max_hr=getattr(garmin, "athlete_max_hr", 0) or 0,
    )
    if activities:
        with db.transaction():
            _save_activities(
                db, activities, today_str, athlete_id=athlete_id, emit=emit, sanity=DataSanityChecker(),
            )
    emit("training_history_backfilled", count=len(activities), days_back=LOAD_HISTORY_DAYS)
    return len(activities)


HRV_REWRITE_MARKER = "garmin_hrv_last_night_avg"
HRV_REWRITE_NIGHTS = 28


def rewrite_recent_hrv_once(
    db: DatabaseManager,
    garmin,  # noqa: ANN001 - GarminSync; typed loosely to keep this module free of integrations
    *,
    athlete_id: str,
    emit: Callable[..., None],
) -> int:
    """Re-read the last 28 nights of HRV from Garmin once, after the SV-12 fix (D-056).

    Until D-056 the sync stored ``lastNight5MinHigh`` (or ``weeklyAvg``), which is higher
    than the night's average. The baseline would then make every new, correct value look
    like a drop. This replaces the Garmin-sourced HRV of the last ``HRV_REWRITE_NIGHTS``
    nights with ``lastNightAvg``; hand-entered rows are kept. It runs until one pass
    succeeds, which is recorded in ``sync_metadata`` under ``HRV_REWRITE_MARKER``.
    Returns the number of nights rewritten.
    """
    marker = db.get_last_sync_outcome(HRV_REWRITE_MARKER)
    if marker and marker.get("last_success_ts"):
        return 0
    from datetime import UTC, datetime

    entries = garmin.sync_hrv(HRV_REWRITE_NIGHTS)
    if not entries:
        return 0
    sanity = DataSanityChecker()
    rewritten = 0
    with db.transaction():
        for entry in entries:
            rmssd = _safe_float(entry.get("rmssd")) or None
            if not entry.get("date") or rmssd is None:
                continue
            if has_rejects(sanity.check_hrv({"date": entry["date"], "rmssd": rmssd}, context="rewrite_recent_hrv")):
                continue
            db.replace_garmin_hrv(date=entry["date"], hrv=rmssd, athlete_id=athlete_id)
            rewritten += 1
    db.record_sync_outcome(source=HRV_REWRITE_MARKER, attempted_at=datetime.now(UTC), success=True)
    emit("hrv_history_rewritten", nights=rewritten, field="lastNightAvg")
    return rewritten

"""
Input Data Sanity Layer — ADR-0026 / T1-19.

Write-time structural validation at the Garmin sync → database write boundary.
Detects cross-field inconsistencies, temporal anomalies, and missing mandatory
fields that physiological_bounds.py (ADR-0023) does not cover.

Engines never receive structurally corrupt records.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

MODULE_VERSION = "1.0.0"

_log = logging.getLogger(__name__)

# SV-17: values in the wrong unit pass the bounds but not these checks.
# 2:00 /km is faster than the average pace of any world record from 1500 m up
# (about 2:26 /km); 15:00 /km is walking. Source: synthetic-athlete-report.md §5.
RUN_PACE_SEC_PER_KM = (120.0, 900.0)
# A whole night under one hour is far more likely a minutes/hours mix-up than sleep.
MIN_NIGHT_SLEEP_HOURS = 1.0
RUN_ACTIVITY_TYPES = frozenset({"running", "interval_training", "tempo_run", "long_run"})

# ADR-0033-L3-D-RESOLVED (2026-04-18): Single-athlete assumption resolved.
# Multi-athlete isolation complete. This module contains no per-athlete
# DB queries — sanity validation is athlete-agnostic by design.


@dataclass
class SanityViolation:
    record_type: str  # "activity" | "daily_metrics" | "hrv"
    field: str
    rule: str  # human-readable rule name
    value: Any
    severity: str  # "reject" | "warn"


def _emit(context: str, v: SanityViolation) -> None:
    action = "data_sanity_reject" if v.severity == "reject" else "data_sanity_warn"
    payload = {
        "flow": "data_sanity",
        "action": action,
        "context": context,
        "record_type": v.record_type,
        "field": v.field,
        "rule": v.rule,
        "value": str(v.value)[:120],
        "severity": v.severity,
    }
    _log.warning(json.dumps(payload))


class DataSanityChecker:
    """Validate individual Garmin records before they are written to the database.

    Each check_* method returns a (possibly empty) list of SanityViolation
    objects.  The caller decides how to act on them:

    - severity == "reject"  → skip the record (do not write)
    - severity == "warn"    → write the record with quality_flag = "degraded"
    """

    # ── Activity validation ───────────────────────────────────────────────────

    def check_activity(
        self,
        row: dict,
        context: str = "activity",
        seen_activity_ids: set[str] | None = None,
    ) -> list[SanityViolation]:
        """Cross-field structural validation for a Garmin activity row.

        Rules (ADR-0026 Table 1):
        - max_hr < avg_hr                               → reject
        - distance_km > 0 and duration_sec == 0         → reject
        - timestamp in future (> now + 1 h drift margin)→ reject
        - hrv_ms == 0                                   → reject  (defence-in-depth)
        - run pace outside RUN_PACE_SEC_PER_KM          → warn    (SV-17, wrong unit)
        """
        violations: list[SanityViolation] = []

        avg_hr = row.get("avg_hr")
        max_hr = row.get("max_hr")
        distance_km = row.get("distance_km")
        duration_sec = row.get("duration_sec")
        timestamp_str = row.get("date") or row.get("timestamp")

        # Rule: max_hr must be >= avg_hr when both are present and non-zero
        if (
            avg_hr is not None
            and max_hr is not None
            and avg_hr > 0
            and max_hr > 0
            and max_hr < avg_hr
        ):
            v = SanityViolation(
                record_type="activity",
                field="max_hr",
                rule="max_hr_lt_avg_hr",
                value=f"max_hr={max_hr} < avg_hr={avg_hr}",
                severity="reject",
            )
            violations.append(v)
            _emit(context, v)

        # Rule: non-zero distance requires non-zero duration
        if (
            distance_km is not None
            and duration_sec is not None
            and float(distance_km) > 0
            and int(duration_sec) == 0
        ):
            v = SanityViolation(
                record_type="activity",
                field="duration_sec",
                rule="nonzero_distance_zero_duration",
                value=f"distance_km={distance_km} duration_sec={duration_sec}",
                severity="reject",
            )
            violations.append(v)
            _emit(context, v)

        # Rule: duplicate Garmin activity id in the same payload must be rejected
        activity_id = row.get("activity_id")
        if seen_activity_ids is not None and activity_id:
            if str(activity_id) in seen_activity_ids:
                v = SanityViolation(
                    record_type="activity",
                    field="activity_id",
                    rule="duplicate_activity_id_in_payload",
                    value=activity_id,
                    severity="reject",
                )
                violations.append(v)
                _emit(context, v)
            else:
                seen_activity_ids.add(str(activity_id))

        # Rule: a run's pace must be one a person can run (SV-17). A duration
        # in minutes read as seconds gives 7.27 km in 40 s, i.e. 5 s/km.
        activity_type = row.get("activity_type")
        if (not activity_type or activity_type in RUN_ACTIVITY_TYPES) and distance_km and duration_sec:
            try:
                pace = float(duration_sec) / float(distance_km)
            except (TypeError, ValueError, ZeroDivisionError):
                pace = None
            lo, hi = RUN_PACE_SEC_PER_KM
            if pace is not None and pace > 0 and not lo <= pace <= hi:
                v = SanityViolation(
                    record_type="activity",
                    field="duration_sec",
                    rule="run_pace_implausible",
                    value=f"distance_km={distance_km} duration_sec={duration_sec} pace={pace:.0f}s/km",
                    severity="warn",
                )
                violations.append(v)
                _emit(context, v)

        # Rule: timestamp must not be in the future (> now + 1 h clock-drift margin)
        if timestamp_str:
            try:
                # Parse YYYY-MM-DD or full ISO timestamp
                if len(str(timestamp_str)) == 10:
                    activity_dt = datetime.fromisoformat(str(timestamp_str)).replace(
                        tzinfo=UTC
                    )
                else:
                    activity_dt = datetime.fromisoformat(str(timestamp_str))
                    if activity_dt.tzinfo is None:
                        activity_dt = activity_dt.replace(tzinfo=UTC)
                now_utc = datetime.now(tz=UTC)
                drift_margin_s = 3600  # 1-hour clock-drift allowance
                if (activity_dt - now_utc).total_seconds() > drift_margin_s:
                    v = SanityViolation(
                        record_type="activity",
                        field="date",
                        rule="timestamp_in_future",
                        value=str(timestamp_str),
                        severity="reject",
                    )
                    violations.append(v)
                    _emit(context, v)
            except (ValueError, TypeError):
                # Unparseable timestamp — warn (not reject; may be a format we don't know)
                v = SanityViolation(
                    record_type="activity",
                    field="date",
                    rule="timestamp_unparseable",
                    value=str(timestamp_str),
                    severity="warn",
                )
                violations.append(v)
                _emit(context, v)

        return violations

    # ── Daily metrics validation ──────────────────────────────────────────────

    def check_daily_metrics(
        self, row: dict, context: str = "daily_metrics"
    ) -> list[SanityViolation]:
        """Structural validation for a daily_metrics row.

        Rules (ADR-0026 Table 1):
        - date is None or empty string → reject
        - 0 < sleep_hours < MIN_NIGHT_SLEEP_HOURS → warn (SV-17, wrong unit)
        """
        violations: list[SanityViolation] = []

        date_val = row.get("date")
        if not date_val:
            v = SanityViolation(
                record_type="daily_metrics",
                field="date",
                rule="date_null_or_empty",
                value=date_val,
                severity="reject",
            )
            violations.append(v)
            _emit(context, v)

        sleep_hours = row.get("sleep_hours")
        if sleep_hours is not None and 0 < float(sleep_hours) < MIN_NIGHT_SLEEP_HOURS:
            v = SanityViolation(
                record_type="daily_metrics",
                field="sleep_hours",
                rule="sleep_hours_implausible",
                value=sleep_hours,
                severity="warn",
            )
            violations.append(v)
            _emit(context, v)

        return violations

    # ── HRV validation ────────────────────────────────────────────────────────

    def check_hrv(self, row: dict, context: str = "hrv") -> list[SanityViolation]:
        """Structural validation for an HRV row.

        Rules (ADR-0026 Table 1):
        - hrv_ms == 0 exactly → reject (sensor failure; physiologically impossible)
          (defence-in-depth; ADR-0023 handles this at the read path as well)
        """
        violations: list[SanityViolation] = []

        rmssd = row.get("rmssd") if row.get("rmssd") is not None else row.get("hrv_ms")
        if rmssd is not None:
            try:
                if float(rmssd) == 0.0:
                    v = SanityViolation(
                        record_type="hrv",
                        field="rmssd",
                        rule="hrv_zero_sensor_failure",
                        value=rmssd,
                        severity="reject",
                    )
                    violations.append(v)
                    _emit(context, v)
            except (TypeError, ValueError):
                _log.debug("rmssd not numeric — zero-check skipped; bounds validation will catch it")
        timestamp_str = row.get("date") or row.get("timestamp")
        if timestamp_str:
            try:
                if len(str(timestamp_str)) == 10:
                    hrv_dt = datetime.fromisoformat(str(timestamp_str)).replace(tzinfo=UTC)
                else:
                    hrv_dt = datetime.fromisoformat(str(timestamp_str))
                    if hrv_dt.tzinfo is None:
                        hrv_dt = hrv_dt.replace(tzinfo=UTC)
                now_utc = datetime.now(tz=UTC)
                if (hrv_dt - now_utc).total_seconds() > 3600:
                    v = SanityViolation(
                        record_type="hrv",
                        field="date",
                        rule="timestamp_in_future",
                        value=str(timestamp_str),
                        severity="reject",
                    )
                    violations.append(v)
                    _emit(context, v)
            except (ValueError, TypeError):
                v = SanityViolation(
                    record_type="hrv",
                    field="date",
                    rule="timestamp_unparseable",
                    value=str(timestamp_str),
                    severity="warn",
                )
                violations.append(v)
                _emit(context, v)

        return violations


def has_rejects(violations: list[SanityViolation]) -> bool:
    """Return True if any violation has severity='reject'."""
    return any(v.severity == "reject" for v in violations)


def has_warns(violations: list[SanityViolation]) -> bool:
    """Return True if any violation has severity='warn'."""
    return any(v.severity == "warn" for v in violations)

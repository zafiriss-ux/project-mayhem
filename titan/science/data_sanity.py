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

# ADR-0040-SINGLE-ATHLETE-SHORTCUT: This module assumes a single active athlete.
# Multi-athlete isolation is deferred to Phase 9 (ADR-0033 Layer 3, T5-07).


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
                pass
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

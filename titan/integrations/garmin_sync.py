"""
Garmin Connect Live API Integration

REAL implementation using garminconnect library (not mock).
"""

import contextlib
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from titan.core.structured_events import EventSeverity, structured_event_payload
from titan.orchestration.contracts import (
    GarminSyncResult,
    GarminSyncResultContract,
    HRVSyncMetrics,
    HRVSyncMetricsContract,
)
from titan.science.data_trust import evaluate_garmin_trust
from titan.science.trimp_engine import TRIMPEngine
from titan.utils.constants import _Secret

_log = logging.getLogger(__name__)

GARMIN_AUTH_FAIL = "GARMIN_AUTH_FAIL"
GARMIN_RATE_LIMIT = "GARMIN_RATE_LIMIT"
GARMIN_PAYLOAD_MALFORMED = "GARMIN_PAYLOAD_MALFORMED"
GARMIN_TIMEOUT = "GARMIN_TIMEOUT"
GARMIN_API_UNAVAILABLE = "GARMIN_API_UNAVAILABLE"
_DEFAULT_SYNC_TIMEOUT_S = 20
_GARTH_TOKEN_FILENAME = ".garth_token"
_LOGIN_RETRY_WAITS_S = (60, 120, 240)  # exponential backoff for 429 rate-limit retries


class _CredentialSecret:
    """Redacted credential wrapper with explicit reveal semantics."""

    __slots__ = ("_value",)

    def __init__(self, value: str | None):
        self._value = _Secret(value or "")

    def reveal(self) -> str:
        return str(self._value)

    def __bool__(self) -> bool:
        return bool(self._value)

    def __repr__(self) -> str:
        return "'***'"

    def __str__(self) -> str:
        return "***"


def _garmin_event(
    action: str,
    *,
    severity: EventSeverity | str = EventSeverity.INFO,
    **fields,
) -> None:
    """Emit a structured Garmin sync event as a single JSON log line."""
    _log.info(json.dumps(structured_event_payload("garmin_sync", action, severity=severity, **fields), default=str))


def _garmin_error_event(action: str, **fields) -> None:
    """Emit a structured Garmin sync event at ERROR level as a single JSON log line."""
    _log.error(
        json.dumps(
            structured_event_payload("garmin_sync", action, severity=EventSeverity.WARNING, **fields),
            default=str,
        )
    )


def _classify_failure(error: Exception) -> str:
    """Map integration/runtime exceptions to a stable Garmin failure class."""
    error_name = error.__class__.__name__.lower()
    message = str(error).lower()
    combined = f"{error_name} {message}"

    if (
        "auth" in combined
        or "credential" in combined
        or "unauthoriz" in combined
        or "forbidden" in combined
    ):
        return GARMIN_AUTH_FAIL
    if "429" in combined or "rate" in combined or "too many requests" in combined:
        return GARMIN_RATE_LIMIT
    if "timeout" in combined or isinstance(error, TimeoutError):
        return GARMIN_TIMEOUT
    if (
        "json" in combined
        or "keyerror" in combined
        or "valueerror" in combined
        or "typeerror" in combined
        or "malformed" in combined
        or "payload" in combined
    ):
        return GARMIN_PAYLOAD_MALFORMED
    return GARMIN_API_UNAVAILABLE


def _emit_failure(subsystem: str, failure_class: str, error: Exception, **fields: Any) -> None:
    _garmin_event(
        failure_class,
        subsystem=subsystem,
        failure_class=failure_class,
        error_class=error.__class__.__name__,
        error_message=str(error),
        **fields,
    )


def _resolve_sync_timeout_seconds() -> int:
    timeout_raw = os.getenv("GARMIN_SYNC_TIMEOUT_S", str(_DEFAULT_SYNC_TIMEOUT_S))
    try:
        timeout_s = int(timeout_raw)
    except ValueError:
        _garmin_event(
            "invalid_sync_timeout",
            subsystem="sync_all",
            configured_timeout=timeout_raw,
            fallback_timeout_s=_DEFAULT_SYNC_TIMEOUT_S,
            detail="GARMIN_SYNC_TIMEOUT_S is not an integer; using default timeout.",
        )
        return _DEFAULT_SYNC_TIMEOUT_S

    if timeout_s < 0:
        _garmin_event(
            "negative_sync_timeout",
            subsystem="sync_all",
            configured_timeout=timeout_s,
            fallback_timeout_s=_DEFAULT_SYNC_TIMEOUT_S,
            detail="GARMIN_SYNC_TIMEOUT_S is negative; using default timeout.",
        )
        return _DEFAULT_SYNC_TIMEOUT_S

    return timeout_s


class GarminSync:
    """
    Live Garmin Connect API integration.
    Uses the 'garminconnect' library for real data.
    """

    _instance_count: int = 0
    _instance_lock = threading.Lock()

    def __init__(self, email: str = None, password: str = None):
        with GarminSync._instance_lock:
            GarminSync._instance_count += 1
            instance_id = GarminSync._instance_count
        _log.info(
            "garmin_sync_instance_created",
            extra={
                "instance_id": instance_id,
                "total_instances": instance_id,
            },
        )
        if instance_id > 1:
            _log.warning(
                "garmin_sync_duplicate_instance",
                extra={
                    "instance_id": instance_id,
                    "total_instances": instance_id,
                    "detail": "Multiple GarminSync instances detected — expected exactly 1 in production",
                },
            )
        self.email = _CredentialSecret(email or os.getenv("GARMIN_EMAIL", ""))
        self.password = _CredentialSecret(password or os.getenv("GARMIN_PASSWORD", ""))
        self.client = None
        self.is_connected = False
        self.last_sync: str | None = None
        self.sync_history: list = []
        self.last_hrv_sync_metrics: HRVSyncMetrics = HRVSyncMetricsContract(
            days_back=0,
            synced_days=0,
            skipped_days=0,
        ).to_payload()
        self.last_connect_error: str | None = None
        self._connect_lock = threading.Lock()
        self._sync_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------ #
    # CONNECTION
    # ------------------------------------------------------------------ #
    def _get_token_path(self) -> Path:
        """Return path to the persisted Garth session token file."""
        try:
            from launcher.validator import get_data_directory
            base_dir = get_data_directory()
        except ModuleNotFoundError as err:
            if err.name not in {"launcher", "launcher.validator"}:
                raise
            base_dir = Path.home() / "Documents" / "TITAN"
        return base_dir / _GARTH_TOKEN_FILENAME

    def connect(self) -> bool:
        if not self.email or not self.password:
            self.last_connect_error = "Garmin credentials missing – run setup first."
            _garmin_event("connect_missing_credentials", subsystem="connect", detail="Garmin credentials missing – run setup first.")
            return False
        with self._connect_lock:
            # Re-check under lock: another thread may have connected while we waited.
            if self.is_connected and self.client is not None:
                return True
            return self._connect_impl()

    def _connect_impl(self) -> bool:
        """Actual connection logic. Must be called under ``_connect_lock``."""
        try:
            from garminconnect import Garmin

            token_path = self._get_token_path()

            # Try loading a persisted session token to avoid re-login 429s.
            if token_path.exists():
                try:
                    token_data = token_path.read_text(encoding="utf-8")
                    client = Garmin()
                    client.garth.loads(token_data)
                    # Verify the token is still accepted by the Garmin API.
                    # garth.loads() only deserialises from disk — it does NOT check the
                    # server.  A single lightweight call here ensures we catch expired
                    # tokens before any sync attempt, preventing the silent 0/0/0 failure.
                    client.connectapi("userprofile-service/socialProfile")
                    self.client = client
                    self.is_connected = True
                    self.last_connect_error = None
                    _garmin_event("connect_token_loaded", subsystem="connect", detail="Connected via saved Garth session token")
                    _garmin_event("connect_success", subsystem="connect", detail="Connected to Garmin Connect")
                    return True
                except Exception as token_err:
                    _token_failure_class = _classify_failure(token_err)
                    if _token_failure_class == GARMIN_RATE_LIMIT:
                        # Garmin rate-limited the verification ping.  The token may
                        # still be valid, but we cannot confirm it.  Attempt one
                        # lightweight data call as secondary validation to distinguish
                        # "rate-limited but valid" from "rate-limited and expired".
                        from datetime import date as _date
                        try:
                            client.get_user_summary(_date.today().isoformat())
                            # Secondary call succeeded — token is genuinely valid.
                            self.client = client
                            self.is_connected = True
                            self.last_connect_error = None
                            _garmin_event(
                                "connect_token_assumed_valid",
                                subsystem="connect",
                                error_class=token_err.__class__.__name__,
                                detail="Token ping rate-limited (429); secondary call succeeded; token valid",
                            )
                            return True
                        except Exception as secondary_err:
                            _secondary_failure_class = _classify_failure(secondary_err)
                            if _secondary_failure_class == GARMIN_RATE_LIMIT:
                                # Both calls rate-limited — preserve token and assume valid.
                                self.client = client
                                self.is_connected = True
                                self.last_connect_error = None
                                _garmin_event(
                                    "connect_token_assumed_valid",
                                    subsystem="connect",
                                    error_class=token_err.__class__.__name__,
                                    detail="Token ping rate-limited (429); secondary call also rate-limited; assuming token valid, skipping re-login",
                                )
                                return True
                            # Secondary call failed with auth (or other) error — token is stale.
                            # Delete the token and fall through to full re-login.
                            with contextlib.suppress(Exception):
                                token_path.unlink(missing_ok=True)
                            _garmin_event(
                                "connect_token_stale_after_429",
                                subsystem="connect",
                                primary_error_class=token_err.__class__.__name__,
                                secondary_error_class=secondary_err.__class__.__name__,
                                secondary_failure_class=_secondary_failure_class,
                                detail="Token ping rate-limited (429); secondary call failed; token stale, falling through to re-login",
                            )
                    _garmin_event(
                        "connect_token_load_failed",
                        subsystem="connect",
                        error_class=token_err.__class__.__name__,
                        detail="Saved token invalid or expired; falling back to full login",
                    )
                    # Delete the stale token so the next startup attempts a fresh login.
                    with contextlib.suppress(Exception):
                        token_path.unlink(missing_ok=True)

            # Full login — token missing or expired.
            # Retry up to 3 times with exponential backoff on GARMIN_RATE_LIMIT (429) only.
            client = None
            for _attempt in range(len(_LOGIN_RETRY_WAITS_S) + 1):
                try:
                    client = Garmin(self.email.reveal(), self.password.reveal())
                    client.login()
                    break
                except Exception as _login_err:
                    if (
                        _classify_failure(_login_err) != GARMIN_RATE_LIMIT
                        or _attempt >= len(_LOGIN_RETRY_WAITS_S)
                    ):
                        raise
                    # Delete the fallback token path before retrying.
                    _alt_token = Path.home() / "Documents" / "TITAN" / _GARTH_TOKEN_FILENAME
                    with contextlib.suppress(Exception):
                        _alt_token.unlink(missing_ok=True)
                    wait_s = _LOGIN_RETRY_WAITS_S[_attempt]
                    _garmin_event(
                        "connect_retry_429",
                        subsystem="connect",
                        attempt=_attempt + 1,
                        wait_s=wait_s,
                        detail=f"Rate-limited (429); retrying login in {wait_s}s",
                    )
                    time.sleep(wait_s)

            # Persist the new session token for future connections.
            try:
                token_path.parent.mkdir(parents=True, exist_ok=True)
                token_path.write_text(client.garth.dumps(), encoding="utf-8")
                _garmin_event("connect_token_saved", subsystem="connect", detail="Garth session token saved")
            except Exception as save_err:
                _garmin_event(
                    "connect_token_save_failed",
                    subsystem="connect",
                    error_class=save_err.__class__.__name__,
                    detail="Could not persist Garth session token",
                )

            self.client = client
            self.is_connected = True
            self.last_connect_error = None
            _garmin_event("connect_success", subsystem="connect", detail="Connected to Garmin Connect")
            return True
        except Exception as e:
            _log.debug("Garmin connection failed", exc_info=True)
            _log.error(
                "startup_failure",
                extra={
                    "component": "garmin_sync_connect",
                    "error_class": e.__class__.__name__,
                    "detail": str(e),
                },
            )
            self.last_connect_error = f"{e.__class__.__name__}: {e}"
            _garmin_event("connect_failed", subsystem="connect", failure_class=_classify_failure(e), error_class=e.__class__.__name__, detail="Garmin connection failed. Please retry or re-run Garmin setup.", error_message=str(e))
            self.is_connected = False
            return False

    def _ensure_connected(self) -> bool:
        if not self.is_connected or self.client is None:
            return self.connect()
        return True

    def _invalidate_session(self) -> None:
        """Reset auth state and delete the stale token file.

        Called whenever a sync method receives a GARMIN_AUTH_FAIL response so
        that the next _ensure_connected() call attempts a fresh login instead
        of re-using a session that the Garmin server has already rejected.
        """
        self.is_connected = False
        self.client = None
        with contextlib.suppress(Exception):
            self._get_token_path().unlink(missing_ok=True)
        _garmin_event(
            "session_invalidated",
            subsystem="auth",
            detail="Auth failure detected during sync; session invalidated for re-auth",
        )

    # ------------------------------------------------------------------ #
    # ACTIVITIES
    # ------------------------------------------------------------------ #
    def sync_activities(self, days_back: int = 7) -> list[dict]:
        if not self._ensure_connected():
            return []
        activities = []
        skipped_records = 0
        try:
            start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            end = datetime.now().strftime("%Y-%m-%d")
            raw = self.client.get_activities_by_date(start, end, "running")
            for a in raw:
                try:
                    dur_sec = int(a.get("duration", 0))
                    dist_m = float(a.get("distance", 0))
                    avg_hr = a.get("averageHR") or a.get("averageHeartRate", 0)
                    max_hr = a.get("maxHR") or a.get("maxHeartRate", 0)
                    pace_sec = int(dur_sec / (dist_m / 1000)) if dist_m > 0 else 0
                    trimp_val, _ = TRIMPEngine.calculate_edwards_trimp(
                        dur_sec / 60,
                        int(avg_hr) if avg_hr else 0,
                        int(max_hr) if max_hr else 0,
                    )
                    estimated_load = round(trimp_val, 1) if trimp_val else 0.0
                    activities.append(
                        {
                            "date": a.get("startTimeLocal", "")[:10],
                            "activity_type": a.get("activityType", {}).get("typeKey", "running"),
                            "distance_km": round(dist_m / 1000, 2),
                            "duration_sec": dur_sec,
                            "avg_hr": int(avg_hr) if avg_hr else 0,
                            "max_hr": int(max_hr) if max_hr else 0,
                            "avg_pace_sec_per_km": pace_sec,
                            "calories": int(a.get("calories", 0)),
                            "elevation_gain_m": int(a.get("elevationGain", 0)),
                            "activity_id": a.get("activityId"),
                            "estimated_training_load": estimated_load,
                        }
                    )
                except Exception as e:
                    skipped_records += 1
                    activity_id = a.get("activityId", "unknown")
                    _emit_failure(
                        "sync_activities",
                        GARMIN_PAYLOAD_MALFORMED,
                        e,
                        activity_id=activity_id,
                    )
                    _garmin_event("activity_skipped_malformed", subsystem="sync_activities", activity_id=activity_id, error_class=e.__class__.__name__, detail=f"Skipping malformed activity ({activity_id})", error_message=str(e))
                    continue
            _garmin_event("activities_synced", subsystem="sync_activities", count=len(activities), days_back=days_back, detail=f"Synced {len(activities)} activities")
            if skipped_records:
                _garmin_event("activity_skip_summary", subsystem="sync_activities", skipped_records=skipped_records, detail=f"Skipped {skipped_records} malformed activity record(s)")
            self._log_sync("activities", len(activities))
        except Exception as e:
            failure_class = _classify_failure(e)
            if failure_class == GARMIN_AUTH_FAIL:
                self._invalidate_session()
            _emit_failure("sync_activities", failure_class, e, days_back=days_back)
            _garmin_event("sync_activities_failed", subsystem="sync_activities", failure_class=failure_class, error_class=e.__class__.__name__, detail="Activity sync failed", error_message=str(e), days_back=days_back)
        return activities

    # ------------------------------------------------------------------ #
    # WEIGHT
    # ------------------------------------------------------------------ #
    def sync_weight(self, days_back: int = 30) -> list[dict]:
        if not self._ensure_connected():
            return []
        entries = []
        try:
            start = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            end = datetime.now().strftime("%Y-%m-%d")
            raw = self.client.get_weigh_ins(start, end)
            daily = raw.get("dailyWeightSummaries", [])
            for d in daily:
                summaries = d.get("allDayWeightSummaries") or [{}]
                summ = summaries[0]
                w_g = summ.get("latestWeight", summ.get("minWeight", 0))
                if w_g and w_g > 0:
                    entries.append(
                        {
                            "date": d.get("calendarDate", ""),
                            "weight_kg": round(w_g / 1000, 2),  # grams → kg
                            "bmi": summ.get("bmi"),
                            "source": "garmin",
                        }
                    )
            _garmin_event("weight_synced", subsystem="sync_weight", count=len(entries), days_back=days_back, detail=f"Synced {len(entries)} weight entries")
            self._log_sync("weight", len(entries))
        except Exception as e:
            failure_class = _classify_failure(e)
            if failure_class == GARMIN_AUTH_FAIL:
                self._invalidate_session()
            _emit_failure("sync_weight", failure_class, e, days_back=days_back)
            _garmin_event("sync_weight_failed", subsystem="sync_weight", failure_class=failure_class, error_class=e.__class__.__name__, detail="Weight sync failed", error_message=str(e), days_back=days_back)
        return entries

    # ------------------------------------------------------------------ #
    # SLEEP
    # ------------------------------------------------------------------ #
    def sync_sleep(self, days_back: int = 7) -> list[dict]:
        if not self._ensure_connected():
            return []
        sessions = []
        skipped_days = 0
        try:
            for i in range(days_back):
                d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                try:
                    raw = self.client.get_sleep_data(d)
                    summary = raw.get("dailySleepDTO", {})
                    if summary.get("sleepTimeSeconds"):
                        total_h = summary["sleepTimeSeconds"] / 3600
                        deep_h = summary.get("deepSleepSeconds", 0) / 3600
                        rem_h = summary.get("remSleepSeconds", 0) / 3600
                        sessions.append(
                            {
                                "date": d,
                                "total_sleep_hours": round(total_h, 2),
                                "deep_sleep_hours": round(deep_h, 2),
                                "rem_sleep_hours": round(rem_h, 2),
                                "sleep_score": summary.get("sleepScores", {})
                                .get("overall", {})
                                .get("value"),
                            }
                        )
                except Exception as e:
                    skipped_days += 1
                    failure_class = _classify_failure(e)
                    error_class = e.__class__.__name__
                    error_message = str(e)
                    _log.warning(
                        "Skipping sleep day %s (%s): %s",
                        d,
                        error_class,
                        error_message,
                    )
                    _garmin_event(
                        failure_class,
                        subsystem="sync_sleep",
                        failure_class=failure_class,
                        date=d,
                        error_class=error_class,
                        error_message=error_message,
                    )
                    if failure_class == GARMIN_AUTH_FAIL:
                        self._invalidate_session()
                        break
                    continue
        except Exception as e:
            failure_class = _classify_failure(e)
            if failure_class == GARMIN_AUTH_FAIL:
                self._invalidate_session()
            _emit_failure("sync_sleep", failure_class, e, days_back=days_back)
            _garmin_event("sync_sleep_failed", subsystem="sync_sleep", failure_class=failure_class, error_class=e.__class__.__name__, detail="Sleep sync failed", error_message=str(e), days_back=days_back)
        _garmin_event("sleep_synced", subsystem="sync_sleep", count=len(sessions), days_back=days_back, detail=f"Synced {len(sessions)} sleep sessions")
        if skipped_days:
            _garmin_event("sleep_skip_summary", subsystem="sync_sleep", skipped_days=skipped_days, detail=f"Skipped {skipped_days} malformed sleep record(s)")
        self._log_sync("sleep", len(sessions))
        return sessions

    # ------------------------------------------------------------------ #
    # HRV
    # ------------------------------------------------------------------ #
    def sync_hrv(self, days_back: int = 7) -> list[dict]:
        if not self._ensure_connected():
            self.last_hrv_sync_metrics = HRVSyncMetricsContract(
                days_back=days_back,
                synced_days=0,
                skipped_days=0,
            ).to_payload()
            _garmin_event("hrv_sync_metrics", **self.last_hrv_sync_metrics)
            return []
        hrv_data = []
        skipped_days = 0
        try:
            for i in range(days_back):
                d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
                try:
                    raw = self.client.get_hrv_data(d)
                    summary = raw.get("hrvSummary", {})
                    rmssd = summary.get("lastNight5MinHigh") or summary.get("weeklyAvg")
                    if rmssd:
                        hrv_data.append(
                            {
                                "date": d,
                                "rmssd": round(float(rmssd), 1),
                                "status": summary.get("status", ""),
                                "source": "garmin",
                            }
                        )
                except Exception as e:
                    skipped_days += 1
                    failure_class = _classify_failure(e)
                    error_class = e.__class__.__name__
                    error_message = str(e)
                    _log.warning(
                        "Skipping HRV day %s (%s): %s",
                        d,
                        error_class,
                        error_message,
                    )
                    _garmin_event(
                        failure_class,
                        subsystem="sync_hrv",
                        failure_class=failure_class,
                        date=d,
                        error_class=error_class,
                        error_message=error_message,
                    )
                    if failure_class == GARMIN_AUTH_FAIL:
                        self._invalidate_session()
                        break
                    continue
        except Exception as e:
            failure_class = _classify_failure(e)
            if failure_class == GARMIN_AUTH_FAIL:
                self._invalidate_session()
            _emit_failure("sync_hrv", failure_class, e, days_back=days_back)
            _garmin_event("sync_hrv_failed", subsystem="sync_hrv", failure_class=failure_class, error_class=e.__class__.__name__, detail="HRV sync failed", error_message=str(e), days_back=days_back)
        _garmin_event("hrv_synced", subsystem="sync_hrv", count=len(hrv_data), days_back=days_back, detail=f"Synced {len(hrv_data)} HRV measurements")
        if skipped_days:
            _garmin_event("hrv_skip_summary", subsystem="sync_hrv", skipped_days=skipped_days, detail=f"Skipped {skipped_days} malformed HRV record(s)")
        self.last_hrv_sync_metrics = HRVSyncMetricsContract(
            days_back=days_back,
            synced_days=len(hrv_data),
            skipped_days=skipped_days,
        ).to_payload()
        _garmin_event("hrv_sync_metrics", **self.last_hrv_sync_metrics)
        self._log_sync("hrv", len(hrv_data))
        return hrv_data

    # ------------------------------------------------------------------ #
    # FULL SYNC
    # ------------------------------------------------------------------ #
    def _sync_operation(self, days_back: int) -> GarminSyncResult:
        activities = self.sync_activities(days_back)
        weight = self.sync_weight(max(days_back, 14))
        sleep = self.sync_sleep(days_back)
        hrv = self.sync_hrv(days_back)
        hrv_metrics: HRVSyncMetrics = HRVSyncMetricsContract(
            days_back=int(self.last_hrv_sync_metrics.get("days_back", 0)),
            synced_days=int(self.last_hrv_sync_metrics.get("synced_days", 0)),
            skipped_days=int(self.last_hrv_sync_metrics.get("skipped_days", 0)),
        ).to_payload()
        payload: GarminSyncResult = GarminSyncResultContract(
            activities=activities,
            weight=weight,
            sleep=sleep,
            hrv=hrv,
            hrv_sync_metrics=hrv_metrics,
            data_trust=evaluate_garmin_trust(data_age_hours=0.0).to_payload(),
        ).to_payload()
        return payload

    def sync_all(self, days_back: int = 7) -> GarminSyncResult:
        _garmin_event("sync_all_started", subsystem="sync_all", days_back=days_back, detail="Full Garmin sync starting")
        self.last_sync = datetime.now().isoformat()
        started = time.monotonic()
        timeout_s = _resolve_sync_timeout_seconds()
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(self._sync_operation, days_back)
        try:
            payload = future.result(timeout=timeout_s)
        except FuturesTimeoutError:
            future.cancel()
            elapsed_s = round(time.monotonic() - started, 3)
            _garmin_event(
                "slo_alert",
                slo_key="garmin_sync_timeout",
                elapsed_s=elapsed_s,
                timeout_s=timeout_s,
                cause="INTEGRATION_LATENCY",
            )
            _garmin_event(
                "garmin_sync_cancelled",
                reason="timeout",
                timeout_seconds=timeout_s,
                operation_name="sync_all",
            )
            hrv_metrics: HRVSyncMetrics = HRVSyncMetricsContract(
                days_back=int(self.last_hrv_sync_metrics.get("days_back", 0)),
                synced_days=int(self.last_hrv_sync_metrics.get("synced_days", 0)),
                skipped_days=int(self.last_hrv_sync_metrics.get("skipped_days", 0)),
            ).to_payload()
            return GarminSyncResultContract(
                activities=[],
                weight=[],
                sleep=[],
                hrv=[],
                hrv_sync_metrics=hrv_metrics,
                status="timeout_cancelled",
                data_trust=evaluate_garmin_trust(
                    data_age_hours=0.0,
                    sync_status="timeout_cancelled",
                ).to_payload(),
            ).to_payload()
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

        elapsed_s = round(time.monotonic() - started, 3)
        if elapsed_s >= timeout_s:
            _garmin_event(
                "slo_alert",
                slo_key="garmin_sync_timeout",
                elapsed_s=elapsed_s,
                timeout_s=timeout_s,
                cause="INTEGRATION_LATENCY",
            )
        else:
            _garmin_event("sync_complete", elapsed_s=elapsed_s, timeout_s=timeout_s)
        return payload

    # ------------------------------------------------------------------ #
    # BACKGROUND THREAD
    # ------------------------------------------------------------------ #
    def start_background_sync(self, interval_hours: int = 6):
        if self._sync_thread and self._sync_thread.is_alive():
            return
        self._stop_event.clear()
        self._sync_thread = threading.Thread(
            target=self._bg_worker, args=(interval_hours,), daemon=True, name="GarminSync"
        )
        self._sync_thread.start()
        _garmin_event("background_sync_started", subsystem="background_sync", interval_hours=interval_hours, detail=f"Garmin background sync started (every {interval_hours}h)")

    def stop_background_sync(self):
        self._stop_event.set()
        if self._sync_thread and self._sync_thread.is_alive():
            worker_thread = self._sync_thread
            timeout_seconds = 5
            worker_thread.join(timeout=timeout_seconds)
            still_alive = worker_thread.is_alive()
            if still_alive:
                _garmin_error_event(
                    "worker_shutdown_timeout",
                    worker_name=worker_thread.name,
                    timeout_seconds=timeout_seconds,
                    still_alive=still_alive,
                )

    def _bg_worker(self, interval_hours: int):
        while not self._stop_event.is_set():
            try:
                self.sync_all()
            except Exception as e:
                _garmin_event("background_sync_error", subsystem="background_sync", failure_class=_classify_failure(e), error_class=e.__class__.__name__, detail="BG sync error", error_message=str(e), interval_hours=interval_hours)
            if self._stop_event.wait(timeout=float(interval_hours * 3600)):
                return

    def _log_sync(self, data_type: str, count: int):
        self.sync_history.append((data_type, datetime.now().isoformat(), count))
        if len(self.sync_history) > 100:
            self.sync_history = self.sync_history[-100:]

    def get_sync_summary(self) -> dict:
        return {
            "last_sync": self.last_sync,
            "total_syncs": len(self.sync_history),
            "is_connected": self.is_connected,
            "recent_syncs": self.sync_history[-5:],
            "last_hrv_sync_metrics": self.last_hrv_sync_metrics,
        }

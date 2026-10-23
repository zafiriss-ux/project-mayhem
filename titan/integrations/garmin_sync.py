"""
Garmin Connect Live API Integration

REAL implementation using garminconnect library (not mock).
"""

import base64
import contextlib
import json
import logging
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from titan.config.settings import get_settings
from titan.config.thresholds import GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT
from titan.core.structured_events import EventSeverity, structured_event_payload
from titan.integrations.biometric_source import (
    NormalizedBiometricSample,  # noqa: F401 — re-exported for external consumers
)
from titan.orchestration.contracts import (
    GarminSyncResult,
    GarminSyncResultContract,
    HRVSyncMetrics,
    HRVSyncMetricsContract,
)
from titan.science.data_trust import DataTrustLevel, evaluate_garmin_trust
from titan.science.trimp_engine import TRIMPEngine
from titan.utils.secrets import SecretStr, register_secret

_log = logging.getLogger(__name__)

GARMIN_AUTH_FAIL = "GARMIN_AUTH_FAIL"
GARMIN_RATE_LIMIT = "GARMIN_RATE_LIMIT"
GARMIN_PAYLOAD_MALFORMED = "GARMIN_PAYLOAD_MALFORMED"
GARMIN_TIMEOUT = "GARMIN_TIMEOUT"
GARMIN_API_UNAVAILABLE = "GARMIN_API_UNAVAILABLE"
_DEFAULT_SYNC_TIMEOUT_S = 90
# Bandit B105: file name, not a token.
_GARTH_TOKEN_FILENAME = ".garth_token"  # nosec B105
_LOGIN_RETRY_WAITS_S = (60, 120, 240)  # exponential backoff for 429 rate-limit retries
# Bandit B105: env var name, not a key.
_TITAN_TOKEN_KEY_ENV = "TITAN_GARTH_TOKEN_KEY"  # nosec B105
# Bandit B105: env var name of the athletes' key file, not a key (ADR-0067 D9.2).
_ATHLETE_TOKEN_KEY_FILE_ENV = "TITAN_TOKEN_KEY_FILE"  # nosec B105
_OWNER_ATHLETE_ID = "owner"
_ATHLETE_ID_IN_PATH = re.compile(r"[a-z0-9_-]+")

def _get_data_dir() -> Path:
    """Return TITAN_DATA_DIR as a Path — lazy so tests can monkeypatch TITAN_DATA_DIR.

    P26-05 / A1-F3: was a module-level constant that froze at first import,
    bypassing the P15-ARCH5 autouse cache_clear fixture.
    """
    return Path(get_settings().TITAN_DATA_DIR)


def _get_garth_token_path() -> Path:
    """Return the Garth token file path — lazy for the same reason as _get_data_dir."""
    return _get_data_dir() / _GARTH_TOKEN_FILENAME


def _write_private_file(path: Path, data: bytes) -> None:
    """Write ``data`` to ``path`` readable by the owner only (0o600).

    The Garmin session token grants account access. A plain write_bytes()
    honours the umask (0o644 by default), leaving the file readable by every
    local user — the same flaw as CVE-2026-54447 in garminconnect <= 0.3.4.
    The chmod also tightens a token file written by an earlier version.
    """
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    os.chmod(path, 0o600)


def _get_token_encryption_key() -> bytes | None:
    """Return Fernet-ready key bytes from env var, or None if unset/invalid.

    Fernet expects the URL-safe base64-encoded key (44 bytes) — we validate
    the env value is decodable but return it in encoded form for Fernet.
    """
    key = os.environ.get(_TITAN_TOKEN_KEY_ENV, "").strip()
    if not key:
        # Unset and empty are the same: .env.example ships "TITAN_GARTH_TOKEN_KEY=".
        return None
    try:
        decoded = base64.urlsafe_b64decode(key.encode())
        if len(decoded) != 32:  # noqa: PLR2004
            raise ValueError("key must decode to exactly 32 bytes")
        return key.encode()
    except Exception:
        _log.warning("Invalid TITAN_GARTH_TOKEN_KEY format — ignoring")
        return None


def validate_token_encryption_key() -> None:
    """Fail at construction on a key that is set but unusable (RBP-04, F-10).

    A malformed key used to be ignored with a WARNING, so the Garmin session
    was silently never saved. An absent key is left to _encrypt_token, which
    already refuses to save the session without one outside dev (TD-18).
    """
    if os.environ.get(_TITAN_TOKEN_KEY_ENV, "").strip() and _get_token_encryption_key() is None:
        raise ValueError(
            "TITAN_GARTH_TOKEN_KEY is set but is not a valid Fernet key "
            "(URL-safe base64 of 32 bytes). Fix it or remove it from .env."
        )


def _is_dev_environment() -> bool:
    """Return True when TITAN_ENV is explicitly set to dev or test."""
    return get_settings().TITAN_ENV.lower() in ("dev", "test")


def _encrypt_token(data: str) -> bytes:
    """Encrypt token string. Raises in production if key not configured."""
    from cryptography.fernet import Fernet

    key = _get_token_encryption_key()
    if key is None:
        if _is_dev_environment():
            _log.warning("garth_token_unencrypted_dev_mode")
            return data.encode()
        # Production: refuse to store token without encryption key (TD-18).
        raise RuntimeError(
            "TITAN_GARTH_TOKEN_KEY must be set in production. "
            "Set TITAN_ENV=dev to bypass in development."
        )
    return Fernet(key).encrypt(data.encode())


def _decrypt_token(data: bytes) -> str:
    """Decrypt token bytes. Falls back to plaintext decode in dev if key not set.

    When a key is configured and decryption fails, emits a structured
    TOKEN_DECRYPT_FAIL event and raises ValueError. Callers must treat
    this as an invalid token and trigger re-login — plaintext fallthrough
    is never permitted when a key is set (T5-101 / ADR-0050).
    """
    from cryptography.fernet import Fernet

    key = _get_token_encryption_key()
    if key is None:
        if _is_dev_environment():
            return data.decode()
        raise RuntimeError(
            "TITAN_GARTH_TOKEN_KEY must be set in production. "
            "Set TITAN_ENV=dev to bypass in development."
        )
    try:
        return Fernet(key).decrypt(data).decode()
    except Exception as exc:
        _garmin_event(
            "token_decrypt_failed",
            severity=EventSeverity.WARNING,
            failure_class="TOKEN_DECRYPT_FAIL",
            error_class=type(exc).__name__,
        )
        raise ValueError("Garmin token decryption failed — token invalid") from exc


def athlete_token_path(athlete_id: str) -> Path:
    """Token file of an athlete other than the owner: <data>/garmin/<athlete_id>/ (ADR-0067 D9.2).

    The id goes into a path, so only ``[a-z0-9_-]+`` is accepted.
    """
    if athlete_id == _OWNER_ATHLETE_ID or not _ATHLETE_ID_IN_PATH.fullmatch(athlete_id):
        raise ValueError(f"not an athlete id that can name a token folder: {athlete_id!r}")
    return _get_data_dir() / "garmin" / athlete_id / _GARTH_TOKEN_FILENAME


def _athlete_token_key() -> bytes:
    """The Fernet key for athletes' tokens, read from the file TITAN_TOKEN_KEY_FILE names.

    Fail-closed (ADR-0067 D9.2, D9.3): the file must exist outside the data folder, so a
    copy of the data folder alone does not decrypt the tokens, and on POSIX it must be
    readable by its owner only. There is no plaintext fallback, not even in dev.
    """
    raw = os.environ.get(_ATHLETE_TOKEN_KEY_FILE_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"{_ATHLETE_TOKEN_KEY_FILE_ENV} is not set")
    key_path = Path(raw).expanduser().resolve()
    data_dir = _get_data_dir().expanduser().resolve()
    if key_path == data_dir or data_dir in key_path.parents:
        raise RuntimeError(f"{_ATHLETE_TOKEN_KEY_FILE_ENV} must point outside the data folder")
    if os.name == "posix" and key_path.stat().st_mode & 0o077:
        raise RuntimeError(f"{_ATHLETE_TOKEN_KEY_FILE_ENV} must be readable by its owner only (0600)")
    key = key_path.read_bytes().strip()
    try:
        if len(base64.urlsafe_b64decode(key)) != 32:  # noqa: PLR2004
            raise ValueError("key must decode to exactly 32 bytes")
    except Exception as exc:
        raise RuntimeError(f"{_ATHLETE_TOKEN_KEY_FILE_ENV} does not hold a valid Fernet key") from exc
    return key


def create_athlete_token_key() -> Path:
    """Write a new athletes' key to the file TITAN_TOKEN_KEY_FILE names, mode 0600 (ADR-0067 D9.2).

    Refused when the file already exists: a new key would leave every stored athlete token
    unreadable. A file that would break the rules of ``_athlete_token_key`` is removed again.
    """
    from cryptography.fernet import Fernet

    raw = os.environ.get(_ATHLETE_TOKEN_KEY_FILE_ENV, "").strip()
    if not raw:
        raise RuntimeError(f"{_ATHLETE_TOKEN_KEY_FILE_ENV} is not set")
    key_path = Path(raw).expanduser().resolve()
    if key_path.exists():
        raise RuntimeError(f"{key_path} already exists; a new key would make every athlete token unreadable")
    key_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(Fernet.generate_key())
    try:
        _athlete_token_key()
    except Exception:
        key_path.unlink()
        raise
    return key_path


def encrypt_athlete_token(data: str) -> bytes:
    """Encrypt an athlete's Garth session with the athletes' key (ADR-0067 D9.2)."""
    from cryptography.fernet import Fernet

    return Fernet(_athlete_token_key()).encrypt(data.encode())


def decrypt_athlete_token(data: bytes) -> str:
    """Decrypt an athlete's token; any failure is an invalid token, never plaintext."""
    from cryptography.fernet import Fernet

    key = _athlete_token_key()
    try:
        return Fernet(key).decrypt(data).decode()
    except Exception as exc:
        _garmin_event(
            "token_decrypt_failed",
            severity=EventSeverity.WARNING,
            failure_class="TOKEN_DECRYPT_FAIL",
            error_class=type(exc).__name__,
        )
        raise ValueError("Garmin token decryption failed — token invalid") from exc


def _restrict_to_current_user(path: Path) -> None:
    """Windows: an ACL that grants the file to the account running TITAN only (ADR-0067 D9.3)."""
    import getpass
    import subprocess  # nosec B404 - a fixed system tool, no shell

    subprocess.run(  # nosec B603 B607 - fixed arguments, no shell
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{getpass.getuser()}:F"],
        check=True, capture_output=True,
    )


def _on_windows() -> bool:
    return os.name == "nt"


def _make_private_token_dirs(folder: Path) -> None:
    """Create ``garmin/`` and ``garmin/<athlete_id>/`` readable by the running account only (0700).

    The data folder itself is left alone. A folder made by an earlier version (0755) is
    tightened on the next write (D-108, TK-07).
    """
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    if _on_windows():
        return
    for path in (folder.parent, folder):
        os.chmod(path, 0o700)


def write_athlete_token(athlete_id: str, session: str) -> Path:
    """Write an athlete's encrypted token readable by the running account only (D9.2, D9.3).

    POSIX: 0600. Windows: the ACL is set on an empty file before any token byte is written;
    if it cannot be set, the file is removed and nothing is written.
    """
    path = athlete_token_path(athlete_id)
    data = encrypt_athlete_token(session)
    _make_private_token_dirs(path.parent)
    if _on_windows():
        _write_private_file(path, b"")
        try:
            _restrict_to_current_user(path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
    _write_private_file(path, data)
    return path


def relogin_athlete(db, athlete_id: str, email: str, password: str, prompt_mfa) -> str:  # noqa: ANN001
    """Log an athlete in to Garmin on the routine machine and store only the token (ADR-0067 D9).

    The athlete types the password (and MFA code) here; it is passed to Garmin and never
    stored or logged (D9.1). The account is bound first, so an account that belongs to
    another athlete is refused before any token is written (D9.4). Returns the bound id.
    """
    from garminconnect import Garmin

    if athlete_id == _OWNER_ATHLETE_ID:
        raise ValueError("the owner's Garmin login stays in .env")
    client = Garmin(email, password, prompt_mfa=prompt_mfa)
    client.login()
    garmin_user_id = str(getattr(client, "display_name", "") or "").strip()
    if not garmin_user_id:
        raise RuntimeError("Garmin did not return an account id after login")
    db.bind_garmin_account(athlete_id, garmin_user_id)
    write_athlete_token(athlete_id, client.client.dumps())
    db.set_garmin_token_state(athlete_id, "ok")
    _garmin_event("relogin_success", subsystem="connect", athlete_id=athlete_id, detail="Athlete token stored")
    return garmin_user_id


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


def _is_definite_token_rejection(error: BaseException) -> bool:
    """True only when Garmin itself refused the stored session (401 or an auth error).

    A network or proxy failure, a timeout, a 429 or a Garmin 5xx says nothing about the
    token, so an athlete's token is kept for those and the sync is tried again later
    (D-108, TK-02). requests' errors are OSError subclasses; an HTTP error carries its status.
    """
    status = getattr(getattr(error, "response", None), "status_code", None)
    if status is not None:
        return status == 401  # noqa: PLR2004
    if isinstance(error, OSError):
        return False
    if _classify_failure(error) == GARMIN_AUTH_FAIL:
        return True
    return re.search(r"\b401\b", str(error)) is not None


def _emit_failure(subsystem: str, failure_class: str, error: Exception, **fields: Any) -> None:
    _garmin_event(
        failure_class,
        subsystem=subsystem,
        failure_class=failure_class,
        error_class=error.__class__.__name__,
        error_message=str(error),
        **fields,
    )


def _emit_garmin_api_degraded(
    *,
    failure_class: str,
    sync_status: str,
    error_class: str,
    error_message: str,
    last_successful_sync_at: str | None,
    data_age_hours: float,
    trust_level: str,
    reasons: list[str],
    degraded_mode_expected: bool,
) -> None:
    """Emit ``garmin_api_degraded`` at CRITICAL severity per ADR-0050 D1 payload contract."""
    _log.error(
        json.dumps(
            structured_event_payload(
                "garmin_sync",
                "garmin_api_degraded",
                severity=EventSeverity.CRITICAL,
                failure_class=failure_class,
                sync_status=sync_status,
                error_class=error_class,
                error_message=error_message,
                last_successful_sync_at=last_successful_sync_at,
                data_age_hours=data_age_hours,
                trust_level=trust_level,
                reasons=reasons,
                degraded_mode_expected=degraded_mode_expected,
            ),
            default=str,
        )
    )


def _activity_utc_date(start_time_local: str) -> str:
    """Convert a Garmin startTimeLocal string to a UTC date (YYYY-MM-DD).

    HD-07: ``startTimeLocal[:10]`` truncation discards the timezone offset,
    assigning the local date rather than the UTC date.  When timezone info is
    present (e.g. ``"2026-04-04T01:30:00+03:00"``), ``fromisoformat`` parses
    it correctly; converting to UTC gives the correct day-bucket.  Strings
    without timezone info are returned as-is using ``[:10]`` (unchanged
    semantics for naive timestamps).
    """
    if not start_time_local:
        return ""
    try:
        dt = datetime.fromisoformat(start_time_local)
        if dt.tzinfo is not None:
            dt = dt.astimezone(UTC)
        return dt.strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return start_time_local[:10]


def _activity_day(activity: dict) -> str:
    """The activity's UTC day, the clock sleep, HRV and the morning use (OW-L5, D-131).

    Garmin's ``startTimeGMT`` is UTC; a run just after local midnight belongs to the UTC
    day before, as that night's sleep does. Without it, ``startTimeLocal`` as before.
    """
    gmt = activity.get("startTimeGMT")
    if isinstance(gmt, str) and len(gmt) >= 10:
        try:
            return date.fromisoformat(gmt[:10]).isoformat()
        except ValueError:
            pass
    return _activity_utc_date(activity.get("startTimeLocal", ""))


def _resolve_sync_timeout_seconds() -> int:
    try:
        timeout_s = get_settings().GARMIN_SYNC_TIMEOUT_S
    except ValueError:
        # A non-numeric GARMIN_SYNC_TIMEOUT_S makes TitanSettings construction raise a
        # pydantic ValidationError (a ValueError subclass) on the typed int field. Restore
        # the pre-P15-ARCH5 per-field resilience: fall back to the default timeout rather
        # than letting one malformed env var crash sync_all.
        _garmin_event(
            "invalid_sync_timeout",
            subsystem="sync_all",
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
    # Class defaults match the owner, for instances built without __init__ (as before step 4).
    athlete_id: str = _OWNER_ATHLETE_ID
    token_only: bool = False
    token_expired: bool = False

    def __init__(
        self,
        email: str = None,
        password: str = None,
        *,
        athlete_id: str = _OWNER_ATHLETE_ID,
        expected_garmin_user_id: str | None = None,
    ):
        validate_token_encryption_key()
        # The Garmin account bound to this athlete (athlete_accounts.garmin_user_id). An
        # athlete's token is used only when Garmin says it belongs to that account (MA-F1).
        self.expected_garmin_user_id = str(expected_garmin_user_id or "").strip() or None
        # The owner logs in with GARMIN_EMAIL/GARMIN_PASSWORD as before. Any other athlete
        # only ever uses their stored token: no password is held and no login happens in
        # the morning (ADR-0067 D9.1, D9.6). A missing or rejected token sets token_expired.
        self.athlete_id = athlete_id
        self.token_only = athlete_id != _OWNER_ATHLETE_ID
        if self.token_only:
            athlete_token_path(athlete_id)  # rejects an id that cannot name a folder
        self.token_expired = False
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
        if self.token_only:
            # Never the owner's credentials for another athlete.
            self.email = SecretStr()
            self.password = SecretStr()
        else:
            self.email = SecretStr(_value=email or get_settings().GARMIN_EMAIL.get_secret_value())
            self.password = SecretStr(_value=password or get_settings().GARMIN_PASSWORD.get_secret_value())
            # Garmin's error texts can quote the login: the owner's e-mail and password are
            # redacted from every log line like the bot token (OW-L4).
            register_secret(self.email.get_secret_value())
            register_secret(self.password.get_secret_value())
        self.client = None
        self.is_connected = False
        self.last_sync: str | None = None
        # Athlete physiological HRmax — injected by DailyCoach after construction
        # so that _sync_operation can forward it to sync_activities().
        self.athlete_max_hr: int = 0
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
        self._consecutive_failures: int = 0
        self._last_successful_sync_at: str | None = None

    @property
    def is_api_degraded(self) -> bool:
        """True when consecutive sync failures have crossed the non-transient threshold."""
        return self._consecutive_failures >= GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT

    def _compute_data_age_hours(self) -> float:
        """Hours since the last successful sync, or ``float('inf')`` if never synced."""
        if self._last_successful_sync_at is None:
            return float("inf")
        try:
            last = datetime.fromisoformat(self._last_successful_sync_at)
            # Ensure both sides are UTC-aware for correct comparison (HR-01)
            if last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            return max(0.0, (datetime.now(UTC) - last).total_seconds() / 3600)
        except Exception:
            return float("inf")

    # ------------------------------------------------------------------ #
    # CONNECTION
    # ------------------------------------------------------------------ #
    def _get_token_path(self) -> Path:
        """Return path to the persisted Garth session token file.

        Stored in TITAN_DATA_DIR (default /data; the launcher sets ~/Documents/TITAN) alongside titan_core.db.
        A startup warning is emitted if a legacy project-root token exists but
        the canonical data-dir path does not, prompting the operator to migrate.
        Another athlete's token is in their own folder (ADR-0067 D9.2).
        """
        if self.token_only:
            return athlete_token_path(self.athlete_id)
        token_path = _get_garth_token_path()
        legacy_path = Path(__file__).parent.parent.parent / _GARTH_TOKEN_FILENAME
        if legacy_path.exists() and not token_path.exists():
            _log.warning(
                "Legacy Garth token found at project root — "
                "move to %s for production use.",
                token_path,
            )
        return token_path

    def connect(self) -> bool:
        if not self.token_only and (not self.email or not self.password):
            self.last_connect_error = "Garmin credentials missing – run setup first."
            _garmin_event("connect_missing_credentials", subsystem="connect", detail="Garmin credentials missing – run setup first.")
            return False
        with self._connect_lock:
            # Re-check under lock: another thread may have connected while we waited.
            if self.is_connected and self.client is not None:
                return True
            return self._connect_impl()

    def _token_account_matches(self, profile) -> bool:  # noqa: ANN001
        """True only when the token's Garmin account is the one bound to this athlete (MA-F1).

        A token in an athlete's folder that answers for another Garmin account, or an athlete
        with no bound account, is never used: the athlete is paused until relogin and the
        token file is left as found for the operator.
        """
        token_account = str((profile or {}).get("displayName") or "").strip() if isinstance(profile, dict) else ""
        if self.expected_garmin_user_id and token_account == self.expected_garmin_user_id:
            return True
        self.token_expired = True
        self.last_connect_error = "Garmin token does not belong to this athlete's bound account; relogin needed"
        _garmin_event(
            "connect_token_account_mismatch",
            severity=EventSeverity.CRITICAL,
            subsystem="connect",
            athlete_id=self.athlete_id,
            detail=(
                "Token answers for another Garmin account; athlete paused until relogin"
                if self.expected_garmin_user_id
                else "No Garmin account bound to this athlete; token not used"
            ),
        )
        return False

    def _connect_impl(self) -> bool:
        """Actual connection logic. Must be called under ``_connect_lock``."""
        try:
            from garminconnect import Garmin

            token_path = self._get_token_path()

            if self.token_only:
                # A missing or unsafe key file is a setup fault, not an expired token:
                # stop before the token is read, so it is never deleted for it.
                try:
                    _athlete_token_key()
                except Exception as key_err:
                    self.last_connect_error = f"{key_err.__class__.__name__}: {key_err}"
                    _garmin_event(
                        "connect_token_key_unusable",
                        subsystem="connect",
                        athlete_id=self.athlete_id,
                        error_class=key_err.__class__.__name__,
                        detail=str(key_err),
                    )
                    return False

            # Try loading a persisted session token to avoid re-login 429s.
            if token_path.exists():
                athlete_token_data = ""  # nosec B105 - empty until read, not a password
                if self.token_only:
                    try:
                        athlete_token_data = decrypt_athlete_token(token_path.read_bytes())
                    except ValueError:
                        # A valid key that is not the one the token was written with (key
                        # rotated or replaced): a setup fault, so the token is kept (D-108).
                        self.last_connect_error = (
                            "Garmin token cannot be decrypted with the current TITAN_TOKEN_KEY_FILE; token kept"
                        )
                        _garmin_event(
                            "connect_token_key_mismatch",
                            severity=EventSeverity.CRITICAL,
                            subsystem="connect",
                            athlete_id=self.athlete_id,
                            detail="Token does not decrypt with the current key; token kept, no relogin marked",
                        )
                        return False
                token_loaded = False
                try:
                    token_data = (
                        athlete_token_data if self.token_only else _decrypt_token(token_path.read_bytes())
                    )
                    client = Garmin()
                    client.client.loads(token_data)
                    token_loaded = True
                    # Verify the token is still accepted by the Garmin API.
                    # client.loads() only deserialises from disk — it does NOT check the
                    # server.  A single lightweight call here ensures we catch expired
                    # tokens before any sync attempt, preventing the silent 0/0/0 failure.
                    profile = client.connectapi("userprofile-service/socialProfile")
                except Exception as token_err:
                    _token_failure_class = _classify_failure(token_err)
                    if _token_failure_class == GARMIN_RATE_LIMIT and self.token_only:
                        # The account of an athlete's token cannot be checked while Garmin
                        # rate-limits the profile call: keep the token, sync later (MA-F1).
                        self.last_connect_error = (
                            f"{token_err.__class__.__name__}: Garmin account check rate-limited; token kept"
                        )
                        _garmin_event(
                            "connect_token_check_failed",
                            subsystem="connect",
                            athlete_id=self.athlete_id,
                            error_class=token_err.__class__.__name__,
                            failure_class=_token_failure_class,
                            detail="Token account check rate-limited (429); token kept, sync retried later",
                        )
                        return False
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
                            if not _is_definite_token_rejection(secondary_err):
                                # An outage, not a rejection: keep the token, the owner's too, and
                                # do not log in now in a rate-limited window (D-108).
                                self.last_connect_error = (
                                    f"{secondary_err.__class__.__name__}: Garmin token check failed; token kept"
                                )
                                _garmin_event(
                                    "connect_token_check_failed",
                                    subsystem="connect",
                                    athlete_id=self.athlete_id,
                                    error_class=secondary_err.__class__.__name__,
                                    failure_class=_secondary_failure_class,
                                    detail="Token check failed (network or Garmin error); token kept, sync retried later",
                                )
                                return False
                            # Secondary call failed with non-rate-limit error — token is stale.
                            # Invalidate the session (resets auth state + deletes token file)
                            # and return False immediately.  Do NOT attempt a fresh login now:
                            # we are already in a rate-limited window and hammering the API
                            # with another login request risks compounding the problem.
                            # The token is deleted so the next scheduled sync cycle will
                            # automatically attempt a fresh credential login.
                            self._invalidate_session()
                            _garmin_event(
                                "connect_token_stale_after_429",
                                subsystem="connect",
                                primary_error_class=token_err.__class__.__name__,
                                secondary_error_class=secondary_err.__class__.__name__,
                                secondary_failure_class=_secondary_failure_class,
                                detail="Token ping rate-limited (429); secondary call failed; session invalidated, not retrying login in rate-limited window",
                            )
                            return False
                        else:
                            return True
                    # A token that does not load is unusable; one that loads is dropped only
                    # when Garmin itself rejects it.
                    if token_loaded and not _is_definite_token_rejection(token_err):
                        # Network down, proxy error or Garmin 5xx: the token may be fine, so it
                        # is kept (D-108, TK-02). An athlete's sync fails now and is retried later;
                        # the owner still tries the .env login as before.
                        self.last_connect_error = (
                            f"{token_err.__class__.__name__}: Garmin token check failed; token kept"
                        )
                        _garmin_event(
                            "connect_token_check_failed",
                            subsystem="connect",
                            athlete_id=self.athlete_id,
                            error_class=token_err.__class__.__name__,
                            failure_class=_token_failure_class,
                            detail=(
                                "Token check failed (network or Garmin error); token kept, sync retried later"
                                if self.token_only
                                else "Token check failed (network or Garmin error); token kept, trying full login"
                            ),
                        )
                        if self.token_only:
                            return False
                    else:
                        _garmin_event(
                            "connect_token_load_failed",
                            subsystem="connect",
                            athlete_id=self.athlete_id,
                            error_class=token_err.__class__.__name__,
                            detail=(
                                "Garmin rejected the saved token; token removed, athletes relogin needed"
                                if self.token_only
                                else "Saved token invalid or expired; falling back to full login"
                            ),
                        )
                        # Delete the rejected token so the next startup attempts a fresh login.
                        with contextlib.suppress(Exception):
                            token_path.unlink(missing_ok=True)
                else:
                    if self.token_only and not self._token_account_matches(profile):
                        return False
                    self.client = client
                    self.is_connected = True
                    self.last_connect_error = None
                    _garmin_event("connect_token_loaded", subsystem="connect", detail="Connected via saved Garth session token")
                    _garmin_event("connect_success", subsystem="connect", detail="Connected to Garmin Connect")
                    return True

            if self.token_only:
                # No morning login for an athlete other than the owner: the athlete is
                # paused until `athletes relogin` (ADR-0067 D9.5, D9.6).
                self.token_expired = True
                self.last_connect_error = "Garmin token missing or expired; athletes relogin needed"
                _garmin_event(
                    "connect_relogin_required",
                    subsystem="connect",
                    athlete_id=self.athlete_id,
                    detail="No usable Garmin token; this athlete is paused until relogin",
                )
                return False

            # Full login — token missing or expired.
            # Retry up to 3 times with exponential backoff on GARMIN_RATE_LIMIT (429) only.
            client = None
            for _attempt in range(len(_LOGIN_RETRY_WAITS_S) + 1):
                try:
                    client = Garmin(self.email.get_secret_value(), self.password.get_secret_value())
                    client.login()
                    break
                except Exception as _login_err:
                    if (
                        _classify_failure(_login_err) != GARMIN_RATE_LIMIT
                        or _attempt >= len(_LOGIN_RETRY_WAITS_S)
                    ):
                        raise
                    # Delete the stale token before retrying.
                    with contextlib.suppress(Exception):
                        token_path.unlink(missing_ok=True)
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
                _write_private_file(token_path, _encrypt_token(client.client.dumps()))
                _garmin_event("connect_token_saved", subsystem="connect", detail="Session token saved")
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
            failure_class = _classify_failure(e)
            self.last_connect_error = f"{e.__class__.__name__}: {e}"
            _garmin_event("connect_failed", subsystem="connect", failure_class=failure_class, error_class=e.__class__.__name__, detail="Garmin connection failed. Please retry or re-run Garmin setup.", error_message=str(e))
            # C1 — authentication failure triggers garmin_api_degraded (ADR-0050 D1).
            if failure_class == GARMIN_AUTH_FAIL:
                _emit_garmin_api_degraded(
                    failure_class=failure_class,
                    sync_status="connect_failed",
                    error_class=e.__class__.__name__,
                    error_message=str(e),
                    last_successful_sync_at=self._last_successful_sync_at,
                    data_age_hours=0.0,
                    trust_level=DataTrustLevel.INVALID.value,
                    reasons=[GARMIN_AUTH_FAIL],
                    degraded_mode_expected=True,
                )
            self.is_connected = False
            return False
        else:
            return True

    def _ensure_connected(self) -> bool:
        if not self.is_connected or self.client is None:
            return self.connect()
        return True

    def _invalidate_session(self, error: BaseException | None = None) -> None:
        """Reset auth state and delete the stale token file.

        Called whenever a sync method receives a GARMIN_AUTH_FAIL response so
        that the next _ensure_connected() call attempts a fresh login instead
        of re-using a session that the Garmin server has already rejected.
        An athlete's token is kept when ``error`` is an outage, not a rejection
        (D-108); when it is deleted the athlete is marked for relogin.
        """
        self.is_connected = False
        self.client = None
        if self.token_only and error is not None and not _is_definite_token_rejection(error):
            _garmin_event(
                "session_reset_token_kept",
                subsystem="auth",
                athlete_id=self.athlete_id,
                error_class=error.__class__.__name__,
                detail="Sync failed with a network or Garmin error; session reset, token kept",
            )
            return
        with contextlib.suppress(Exception):
            self._get_token_path().unlink(missing_ok=True)
        if self.token_only:
            self.token_expired = True
        _garmin_event(
            "session_invalidated",
            subsystem="auth",
            detail="Auth failure detected during sync; session invalidated for re-auth",
        )

    # ------------------------------------------------------------------ #
    # ACTIVITIES
    # ------------------------------------------------------------------ #
    def sync_activities(self, days_back: int = 14, athlete_max_hr: int = 0) -> list[dict]:
        """Fetch running activities from Garmin for the past ``days_back`` days.

        Args:
            days_back: Number of days back to fetch.
            athlete_max_hr: Athlete's physiological HRmax from the athlete
                profile.  Used as the zone-boundary ceiling in Edwards TRIMP
                calculation.  Must be sourced from ``AthleteProfile.max_hr``,
                NOT from the session peak HR in the Garmin payload.
                When 0 (not supplied), TRIMP calculation returns None and
                ``estimated_training_load`` defaults to 0.0.

        An activity without a heart rate gets a middle-zone load estimate and
        ``load_estimated=True`` (F6, D-075).
        """
        if not self._ensure_connected():
            return []
        activities = []
        skipped_records = 0
        sync_succeeded = False
        try:
            start = (datetime.now(UTC) - timedelta(days=days_back)).strftime("%Y-%m-%d")
            end = datetime.now(UTC).strftime("%Y-%m-%d")
            raw = self.client.get_activities_by_date(start, end, "running")
            for a in raw:
                try:
                    dur_sec = int(a.get("duration", 0))
                    dist_m = float(a.get("distance", 0))
                    avg_hr = a.get("averageHR") or a.get("averageHeartRate", 0)
                    # session_max_hr is retained in the activity record for
                    # diagnostic value but is NOT used as the HRmax ceiling
                    # for zone boundaries — athlete_max_hr (physiological
                    # HRmax from the athlete profile) serves that role.
                    session_max_hr = a.get("maxHR") or a.get("maxHeartRate", 0)
                    pace_sec = int(dur_sec / (dist_m / 1000)) if dist_m > 0 else 0
                    trimp_val, _ = TRIMPEngine.calculate_edwards_trimp(
                        dur_sec / 60,
                        int(avg_hr) if avg_hr else 0,
                        athlete_max_hr,
                    )
                    estimated_load = round(trimp_val, 1) if trimp_val else 0.0
                    activities.append(
                        {
                            "date": _activity_day(a),
                            "activity_type": a.get("activityType", {}).get("typeKey", "running"),
                            "distance_km": round(dist_m / 1000, 2),
                            "duration_sec": dur_sec,
                            "avg_hr": int(avg_hr) if avg_hr else 0,
                            "max_hr": int(session_max_hr) if session_max_hr else 0,
                            "avg_pace_sec_per_km": pace_sec,
                            "calories": int(a.get("calories", 0)),
                            "elevation_gain_m": int(a.get("elevationGain", 0)),
                            "activity_id": a.get("activityId"),
                            # Garmin's primary benefit (e.g. TEMPO, VO2MAX); SV-11, D-089.
                            "training_effect_label": a.get("trainingEffectLabel"),
                            "estimated_training_load": estimated_load,
                            "load_estimated": bool(trimp_val) and not avg_hr,
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
            sync_succeeded = True
        except Exception as e:
            failure_class = _classify_failure(e)
            if failure_class == GARMIN_AUTH_FAIL:
                self._invalidate_session(e)
            _emit_failure("sync_activities", failure_class, e, days_back=days_back)
            _garmin_event("sync_activities_failed", subsystem="sync_activities", failure_class=failure_class, error_class=e.__class__.__name__, detail="Activity sync failed", error_message=str(e), days_back=days_back)
        # T5-67: success events gated on boolean flag — never emitted on exception-aborted sync.
        if sync_succeeded:
            _garmin_event("activities_synced", subsystem="sync_activities", count=len(activities), days_back=days_back, detail=f"Synced {len(activities)} activities")
            if skipped_records:
                _garmin_event("activity_skip_summary", subsystem="sync_activities", skipped_records=skipped_records, detail=f"Skipped {skipped_records} malformed activity record(s)")
            self._log_sync("activities", len(activities))
        return activities

    # ------------------------------------------------------------------ #
    # WEIGHT
    # ------------------------------------------------------------------ #
    def sync_weight(self, days_back: int = 30) -> list[dict]:
        if not self._ensure_connected():
            return []
        results = []
        sync_succeeded = False
        try:
            start = (datetime.now(UTC) - timedelta(days=days_back)).strftime("%Y-%m-%d")
            end = datetime.now(UTC).strftime("%Y-%m-%d")
            raw = self.client.get_weigh_ins(start, end)

            # Format A: garminconnect 0.3.2 — /weight/range/ returns dateWeightList
            entries = raw.get("dateWeightList", [])

            # Format B: legacy fallback for pre-0.3.2 API shape (offline mocks, older envs)
            if not entries:
                daily = raw.get("dailyWeightSummaries", [])
                for d in daily:
                    summaries = d.get("allDayWeightSummaries") or [{}]
                    summ = summaries[0]
                    w_g = summ.get("latestWeight", summ.get("minWeight", 0))
                    if w_g:
                        entries.append({
                            "calendarDate": d.get("calendarDate"),
                            "value": round(w_g / 1000, 2),
                            "unitKey": "kg",
                        })

            # Neither known key present — surface as WARNING for diagnosis
            if not entries and raw and "dateWeightList" not in raw and "dailyWeightSummaries" not in raw:
                _garmin_event(
                    "weight_sync_format_unknown",
                    severity="WARNING",
                    raw_keys=list(raw.keys())[:10],
                )

            for entry in entries:
                date_str = entry.get("calendarDate") or entry.get("date")
                unit = entry.get("unitKey", "kg")
                value = entry.get("value", 0)

                if not date_str or not value:
                    continue

                weight_kg = round(value * 0.453592, 2) if unit == "lbs" else round(float(value), 2)

                if weight_kg <= 0:
                    continue

                results.append({"date": date_str, "weight_kg": weight_kg})

            sync_succeeded = True
        except Exception as e:
            failure_class = _classify_failure(e)
            if failure_class == GARMIN_AUTH_FAIL:
                self._invalidate_session(e)
            _emit_failure("sync_weight", failure_class, e, days_back=days_back)
            _garmin_event("sync_weight_failed", subsystem="sync_weight", failure_class=failure_class, error_class=e.__class__.__name__, detail="Weight sync failed", error_message=str(e), days_back=days_back)
        # T5-67: success events gated on boolean flag — never emitted on exception-aborted sync.
        if sync_succeeded:
            _garmin_event("weight_synced", subsystem="sync_weight", count=len(results), days_back=days_back, detail=f"Synced {len(results)} weight entries")
            self._log_sync("weight", len(results))
        return results

    # ------------------------------------------------------------------ #
    # SLEEP
    # ------------------------------------------------------------------ #
    def _resting_hr_for_day(self, sleep_raw: dict, day: str, *, today: bool) -> int | None:
        """Resting HR for *day*: from the sleep response, else (today only) the daily stats.

        The daily summary (``get_stats``) carries ``restingHeartRate``; it costs one
        extra call, so it is fetched only for today, the one day the coach uses.
        """
        value = sleep_raw.get("restingHeartRate")
        if not value and today:
            try:
                value = (self.client.get_stats(day) or {}).get("restingHeartRate")
            except Exception as e:
                _garmin_event(
                    "resting_hr_unavailable",
                    subsystem="sync_sleep",
                    date=day,
                    error_class=e.__class__.__name__,
                    error_message=str(e),
                )
                return None
        try:
            return int(value) if value else None
        except (TypeError, ValueError):
            return None

    def sync_sleep(self, days_back: int = 14) -> list[dict]:
        if not self._ensure_connected():
            return []
        sessions = []
        skipped_days = 0
        sync_succeeded = False
        try:
            for i in range(days_back):
                d = (datetime.now(UTC) - timedelta(days=i)).strftime("%Y-%m-%d")
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
                                "resting_hr": self._resting_hr_for_day(raw, d, today=(i == 0)),
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
                        self._invalidate_session(e)
                        break
                    continue
            sync_succeeded = True
        except Exception as e:
            failure_class = _classify_failure(e)
            if failure_class == GARMIN_AUTH_FAIL:
                self._invalidate_session(e)
            _emit_failure("sync_sleep", failure_class, e, days_back=days_back)
            _garmin_event("sync_sleep_failed", subsystem="sync_sleep", failure_class=failure_class, error_class=e.__class__.__name__, detail="Sleep sync failed", error_message=str(e), days_back=days_back)
        # T5-67: success events gated on boolean flag — never emitted on exception-aborted sync.
        if sync_succeeded:
            _garmin_event("sleep_synced", subsystem="sync_sleep", count=len(sessions), days_back=days_back, detail=f"Synced {len(sessions)} sleep sessions")
            if skipped_days:
                _garmin_event("sleep_skip_summary", subsystem="sync_sleep", skipped_days=skipped_days, detail=f"Skipped {skipped_days} malformed sleep record(s)")
            self._log_sync("sleep", len(sessions))
        return sessions

    # ------------------------------------------------------------------ #
    # HRV
    # ------------------------------------------------------------------ #
    def sync_hrv(self, days_back: int = 14) -> list[dict]:
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
        sync_succeeded = False
        try:
            for i in range(days_back):
                d = (datetime.now(UTC) - timedelta(days=i)).strftime("%Y-%m-%d")
                try:
                    raw = self.client.get_hrv_data(d)
                    summary = raw.get("hrvSummary", {})
                    # SV-12 / D-056: the night's average RMSSD, the value Garmin shows as
                    # HRV. Not the best 5 minutes, and not the 7-night average.
                    rmssd = summary.get("lastNightAvg")
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
                        self._invalidate_session(e)
                        break
                    continue
            sync_succeeded = True
        except Exception as e:
            failure_class = _classify_failure(e)
            if failure_class == GARMIN_AUTH_FAIL:
                self._invalidate_session(e)
            _emit_failure("sync_hrv", failure_class, e, days_back=days_back)
            _garmin_event("sync_hrv_failed", subsystem="sync_hrv", failure_class=failure_class, error_class=e.__class__.__name__, detail="HRV sync failed", error_message=str(e), days_back=days_back)
        # T5-67: success events gated on boolean flag — never emitted on exception-aborted sync.
        if sync_succeeded:
            _garmin_event("hrv_synced", subsystem="sync_hrv", count=len(hrv_data), days_back=days_back, detail=f"Synced {len(hrv_data)} HRV measurements")
            if skipped_days:
                _garmin_event("hrv_skip_summary", subsystem="sync_hrv", skipped_days=skipped_days, detail=f"Skipped {skipped_days} malformed HRV record(s)")
            self._log_sync("hrv", len(hrv_data))
        self.last_hrv_sync_metrics = HRVSyncMetricsContract(
            days_back=days_back,
            synced_days=len(hrv_data),
            skipped_days=skipped_days,
        ).to_payload()
        _garmin_event("hrv_sync_metrics", **self.last_hrv_sync_metrics)
        return hrv_data

    # ------------------------------------------------------------------ #
    # FULL SYNC
    # ------------------------------------------------------------------ #
    def _sync_operation(self, days_back: int) -> GarminSyncResult:
        activities = self.sync_activities(days_back, athlete_max_hr=self.athlete_max_hr)
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
            data_age_hours=0.0,
        ).to_payload()
        return payload

    def sync_all(self, days_back: int = 14) -> GarminSyncResult:
        _garmin_event("sync_all_started", subsystem="sync_all", days_back=days_back, detail="Full Garmin sync starting")
        self.last_sync = datetime.now(UTC).isoformat()
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
            # C2 — timeout exit triggers garmin_api_degraded (ADR-0050 D1).
            self._consecutive_failures += 1
            _emit_garmin_api_degraded(
                failure_class=GARMIN_TIMEOUT,
                sync_status="timeout_cancelled",
                error_class="FuturesTimeoutError",
                error_message=f"Garmin sync timed out after {timeout_s}s",
                last_successful_sync_at=self._last_successful_sync_at,
                data_age_hours=self._compute_data_age_hours(),
                trust_level=DataTrustLevel.INVALID.value,
                reasons=["SYNC_TIMEOUT"],
                degraded_mode_expected=True,
            )
            hrv_metrics: HRVSyncMetrics = HRVSyncMetricsContract(
                days_back=int(self.last_hrv_sync_metrics.get("days_back", 0)),
                synced_days=int(self.last_hrv_sync_metrics.get("synced_days", 0)),
                skipped_days=int(self.last_hrv_sync_metrics.get("skipped_days", 0)),
            ).to_payload()
            _timeout_age = self._compute_data_age_hours()
            return GarminSyncResultContract(
                activities=[],
                weight=[],
                sleep=[],
                hrv=[],
                hrv_sync_metrics=hrv_metrics,
                status="timeout_cancelled",
                data_trust=evaluate_garmin_trust(
                    data_age_hours=_timeout_age,
                    sync_status="timeout_cancelled",
                ).to_payload(),
                data_age_hours=_timeout_age,
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

        # Track sync quality for C3/C4 degradation detection (ADR-0050 D1).
        total_records = (
            len(payload.get("activities", []))
            + len(payload.get("sleep", []))
            + len(payload.get("hrv", []))
            + len(payload.get("weight", []))
        )
        if total_records > 0:
            # Sync succeeded — reset failure streak and record timestamp.
            self._consecutive_failures = 0
            self._last_successful_sync_at = datetime.now(UTC).isoformat()
            payload["data_age_hours"] = 0.0
            from titan.observability.metrics import get_metrics
            get_metrics().counter("garmin_sync_success", labels={"athlete": self.athlete_id})
        else:
            # Sync completed without data — count as a failure for C3 tracking.
            self._consecutive_failures += 1
            data_age_hours = self._compute_data_age_hours()
            payload["data_age_hours"] = data_age_hours
            # C3 — consecutive failure threshold crossed (ADR-0050 D1 condition 3).
            if self._consecutive_failures >= GARMIN_DEGRADATION_FAILURE_THRESHOLD_COUNT:
                _emit_garmin_api_degraded(
                    failure_class=GARMIN_API_UNAVAILABLE,
                    sync_status="sync_failed",
                    error_class="EmptySync",
                    error_message="Garmin sync completed but returned no records",
                    last_successful_sync_at=self._last_successful_sync_at,
                    data_age_hours=data_age_hours,
                    trust_level=DataTrustLevel.INVALID.value,
                    reasons=["CONSECUTIVE_FAILURE_THRESHOLD_CROSSED"],
                    degraded_mode_expected=True,
                )
            else:
                # C4 — trust INVALID before threshold crossed (ADR-0050 D1 condition 4).
                trust_report = evaluate_garmin_trust(data_age_hours=data_age_hours)
                if trust_report.trust_level == DataTrustLevel.INVALID:
                    _emit_garmin_api_degraded(
                        failure_class=GARMIN_API_UNAVAILABLE,
                        sync_status="sync_failed",
                        error_class="TrustInvalid",
                        error_message="Garmin data trust level resolved to INVALID",
                        last_successful_sync_at=self._last_successful_sync_at,
                        data_age_hours=data_age_hours,
                        trust_level=DataTrustLevel.INVALID.value,
                        reasons=["TRUST_LEVEL_INVALID"],
                        degraded_mode_expected=True,
                    )

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
        self.sync_history.append((data_type, datetime.now(UTC).isoformat(), count))
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

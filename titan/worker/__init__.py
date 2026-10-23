"""titan.worker — background effect runner (ADR-0057).

Owns all write-heavy side effects: Garmin sync, sending Telegram messages, the
morning round of every ready athlete, backups. With TITAN_MULTI_ATHLETE=1 it also
listens for Telegram commands, so athletes can send /consent and /agree (D-103).
Enforces a single-instance advisory lock so docker restart never spawns a duplicate.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import signal as _signal
import sys
import threading
import time
from dataclasses import dataclass
from io import IOBase
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

from titan.config.settings import get_settings
from titan.utils.secrets import install_log_redaction

logger = logging.getLogger(__name__)

# Attributes every LogRecord has; anything else came from ``extra=``.
_RECORD_FIELDS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", None, None))) | {"message", "asctime"}


class _ExtraFormatter(logging.Formatter):
    """The plain worker line plus the ``extra`` fields, so an athlete's id is in the log (runbook, D-101)."""

    def format(self, record: logging.LogRecord) -> str:
        line = super().format(record)
        extra = {k: v for k, v in vars(record).items() if k not in _RECORD_FIELDS}
        if not extra:
            return line
        return line + " " + " ".join(f"{k}={v}" for k, v in sorted(extra.items()))


def _configure_logging() -> None:
    """INFO to stderr, as ``basicConfig`` did, with the ``extra`` fields on each line.

    Like ``basicConfig``, nothing changes when the root logger already has a handler.
    """
    handler = logging.StreamHandler()
    handler.setFormatter(_ExtraFormatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    # Every worker line passes the redaction filter, so no bot token reaches docker logs (D-108).
    install_log_redaction(handler)
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def _get_lock_file() -> Path:
    """Return the worker lock file path — lazy so tests can monkeypatch TITAN_DATA_DIR.

    P26-05 / A1-F3: was a module-level constant that froze TITAN_DATA_DIR at
    first import, bypassing the P15-ARCH5 autouse cache_clear fixture.
    """
    return Path(get_settings().TITAN_DATA_DIR) / "worker.lock"

_shutdown = threading.Event()


def _request_shutdown() -> None:
    logging.getLogger("titan.worker.signal").info("worker_shutdown_requested")
    _shutdown.set()


def _handle_sigterm(signum, frame):  # noqa: ANN001
    # The handler runs on the main thread between two bytecodes. If that thread
    # is inside _shutdown.wait() holding the event's internal lock, set() here
    # waits for that lock forever and SIGTERM is lost. Another thread can
    # take the lock once the main thread releases it.
    threading.Thread(target=_request_shutdown, name="titan-worker-sigterm", daemon=True).start()


HEARTBEAT_FILE = "worker.heartbeat"


def acquire_worker_lock() -> IOBase | None:
    """Return an open file handle holding an exclusive lock, or None if already locked.

    INV-23(4): the lock is a kernel ``flock``, released when the holding process
    dies, so a crashed worker never wedges the next start. The holder's PID is
    written into the file for diagnosis. The file is opened without truncation
    so a refused start does not erase the live holder's PID.
    """
    path = _get_lock_file()
    fh = open(path, "a+")  # noqa: SIM115
    fh.seek(0)
    try:
        import fcntl

        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:
        # Windows fallback
        import msvcrt

        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            _log_lock_held(fh)
            return None
    except OSError:
        _log_lock_held(fh)
        return None
    fh.seek(0)
    fh.truncate()
    fh.write(f"{os.getpid()}\n")
    fh.flush()
    return fh


def _log_lock_held(fh: IOBase) -> None:
    try:
        fh.seek(0)
        holder = fh.read().strip() or "unknown"
    except OSError:
        holder = "unknown"
    fh.close()
    logger.info("worker_lock_held", extra={"holder_pid": holder})


def _write_heartbeat(path: Path) -> None:
    """Record that the supervision loop is alive (INV-23(1)); never raises."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(_dt.datetime.now(_dt.UTC).isoformat(), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as exc:
        logging.getLogger("titan.worker.heartbeat").exception(
            "worker_heartbeat_write_failed", extra={"path": str(path), "error": str(exc)}
        )


def check_heartbeat(path: Path, max_age_s: float, now: float | None = None) -> tuple[bool, str]:
    """Healthcheck verdict: healthy only if the heartbeat exists and is fresh."""
    try:
        age = (time.time() if now is None else now) - path.stat().st_mtime
    except OSError:
        return False, f"no heartbeat at {path}"
    if age > max_age_s:
        return False, f"heartbeat is {age:.0f}s old (limit {max_age_s:.0f}s)"
    return True, f"heartbeat is {age:.0f}s old"


def _sleep_with_heartbeat(stop: threading.Event, total_s: float, interval_s: float, heartbeat: Path) -> bool:
    """Wait ``total_s`` writing a heartbeat every ``interval_s``. True if ``stop`` fired."""
    deadline = time.monotonic() + total_s
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        if stop.wait(timeout=min(interval_s, remaining)):
            return True
        _write_heartbeat(heartbeat)


def _run_backup(db: DatabaseManager) -> None:
    """Daily verified hot backup to TITAN_BACKUP_DIR with .env retention (AGENTS DR-01/DR-02)."""
    log = logging.getLogger("titan.worker.backup")
    settings = get_settings()
    backup_dir = Path(settings.TITAN_BACKUP_DIR) if settings.TITAN_BACKUP_DIR else None
    if backup_dir is None:
        log.warning(
            "backup_same_volume",
            extra={"detail": "TITAN_BACKUP_DIR is not set; backups are written next to the database"},
        )
    backed_up = db.backup_database(
        backup_dir=backup_dir,
        keep=settings.BACKUP_RETENTION_DAILY_DAYS,
        keep_weekly=settings.BACKUP_RETENTION_WEEKLY_COUNT,
    )
    if backed_up:
        log.info("backup_complete", extra={"path": str(backed_up)})


def _athlete_housekeeping(db: DatabaseManager, *, at_start: bool = False) -> None:
    """Re-apply recorded deletions at start (ADR-0067 D2.7), then delete athletes 30 days after /stop (D4.3).

    A failure is logged at CRITICAL and never stops the owner's routine.
    """
    from titan.core import athlete_lifecycle

    log = logging.getLogger("titan.worker.runner")
    try:
        if at_start:
            athlete_lifecycle.reapply_deletions(db)
        athlete_lifecycle.purge_expired_athletes(db, now=_utc_now())
    except Exception as exc:
        log.critical("worker_athlete_housekeeping_failed", extra={"error": str(exc)})


def _readiness_problem(db: DatabaseManager, athlete_id: str) -> str | None:
    """Why the athlete cannot be run today, or None (ADR-0067 D7.1).

    Consent first (D4.2), then profile, Garmin and Telegram. Only the database is read:
    nothing is called or written for an athlete who is not ready.
    """
    from titan.core.athlete import AthleteNotReady, load_athlete_profile

    try:
        _require_consent(db, athlete_id)
        load_athlete_profile(db, athlete_id)
        _require_garmin_ready(db, athlete_id)
        _require_telegram_ready(db, athlete_id)
    except AthleteNotReady as exc:
        return exc.reason
    return None


def _tell_zaf_not_ready(db: DatabaseManager, athlete_id: str, reason: str, now: _dt.datetime) -> None:
    """Tell Zaf once per UTC day that an athlete is not run, and why (ADR-0067 D7.1).

    The marker is the owner's row in ``worker_routine_executions`` with routine type
    ``not_ready:<athlete_id>``, so a restart does not tell again and nothing is written
    for the athlete. A failed send is tried again at most 3 times a day, each try at least
    ``ROUTINE_RETRY_DELAY_S`` after the previous one, so a short Telegram outage does not use
    up the day's tries in three polls (DW-08, D-111).
    """
    from titan.core.athlete_lifecycle import NOT_READY_NOTICE_PREFIX

    log = logging.getLogger("titan.worker.scheduler")
    day = now.date().isoformat()
    routine = f"{NOT_READY_NOTICE_PREFIX}{athlete_id}"
    try:
        state, _attempt = db.begin_routine_attempt(
            athlete_id="owner", execution_date=day, routine_type=routine,
            started_at=now, max_attempts=ROUTINE_MAX_ATTEMPTS,
            retry_gap=_dt.timedelta(seconds=ROUTINE_RETRY_DELAY_S),
        )
        if state != "run":
            return
        from titan.integrations.telegram_bot import TitanTelegramBot

        # Plain text: reasons name fields such as location_city.
        sent = TitanTelegramBot(db=db).send_message(f"⏸ {athlete_id} is not run today: {reason}.", parse_mode="")
        if sent:
            db.mark_routine_delivered(
                athlete_id="owner", execution_date=day, routine_type=routine, delivered_at=_utc_now(),
            )
    except Exception as exc:
        log.exception("scheduler_not_ready_notice_failed", extra={"athlete_id": athlete_id, "error": str(exc)})


def _seconds_until_next_run(hour: int = 7, minute: int = 0) -> float:
    """Return seconds until next HH:MM UTC. Always > 0."""
    now = _dt.datetime.now(_dt.UTC)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += _dt.timedelta(days=1)
    return (target - now).total_seconds()


ROUTINE_MORNING = "morning"
ROUTINE_HOUR_UTC = 7
# A day whose message was not delivered resumes, at most this many attempts (ADR-0067 D8.4).
ROUTINE_MAX_ATTEMPTS = 3
# The next attempt of the same day starts at least this long after the previous one: the
# owner loop sleeps it, the round counts it from the day's first attempt (D-109).
ROUTINE_RETRY_DELAY_S = 15 * 60
# This process in the "attempt in progress" mark (ADR-0069 §4β): a mark of the same runner
# with another token is from a process that is gone, so it does not hold.
_PROCESS_TOKEN = os.urandom(6).hex()
# With several athletes no day's first attempt starts after this hour UTC (D-109): a briefing
# that arrives in the afternoon or evening is no longer a morning briefing.
ROUTINE_LAST_START_HOUR_UTC = 12
# Recording a delivery that failed is tried again after these pauses (D-109).
_MARK_RETRY_DELAYS_S: tuple[float, ...] = (0.5, 2.0)
# Sessions at or below EASY: a resend that cannot be checked again keeps these (D-109).
_AT_MOST_EASY = frozenset({"REST", "RECOVERY", "EASY"})
_EASY_MAX_DURATION_MIN = 45

# Days of this process whose briefing reached Telegram but whose delivery could not be
# recorded, days already left, and days logged as too late; keyed by database file,
# athlete and date (D-109).
_UNRECORDED_SENDS: set[tuple[str, str, str]] = set()
_LEFT_DAYS: set[tuple[str, str, str]] = set()
_LATE_LOGGED: set[tuple[str, str, str]] = set()


def _day_key(db: DatabaseManager, athlete_id: str, execution_date: str) -> tuple[str, str, str]:
    return (str(getattr(db, "db_path", "")), athlete_id, execution_date)


@dataclass
class _MorningDay:
    """One claimed attempt of one athlete's day, as the routine sees it (D-109)."""

    execution_date: str
    attempt: int
    replace_decision: bool = False
    note: str | None = None
    decided: bool = False


def _utc_now() -> _dt.datetime:
    """Current UTC time; one seam so tests can pin the clock."""
    return _dt.datetime.now(_dt.UTC)


def _claim_routine(
    db: DatabaseManager, athlete_id: str, now: _dt.datetime, *, spaced: bool = False,
    last_start: bool | None = None, runner: str = "worker",
) -> int | bool | None:
    """Take the next attempt at today's morning (ADR-0060 D1, amended by ADR-0067 D8.4; INV-15).

    An int: the attempt number this worker now runs. False: nothing runs now, because the
    day was delivered or left (a day whose attempts are used up is left here), or, with
    ``spaced``, the next attempt is not due yet or the day would start after
    ``ROUTINE_LAST_START_HOUR_UTC`` (D-109). A day this process already sent is never claimed
    again, even when recording that delivery failed (D-109). None: the claim itself failed;
    the routine does not run this cycle (fail closed) and the caller retries on its next cycle.
    ``last_start`` turns the noon limit on or off on its own; by default it follows ``spaced``.
    ``runner`` (``"worker"`` or ``"console"``) marks the attempt as in progress; while another
    attempt of the day runs, within its time limit, nothing is claimed (P4-03, ADR-0069 §4β).
    """
    if last_start is None:
        last_start = spaced
    execution_date = now.date().isoformat()
    key = _day_key(db, athlete_id, execution_date)
    if key in _UNRECORDED_SENDS:
        _mark_delivered(db, athlete_id, execution_date)
        return False
    gap = _dt.timedelta(seconds=ROUTINE_RETRY_DELAY_S) if spaced else None
    start_by = (
        now.replace(hour=ROUTINE_LAST_START_HOUR_UTC, minute=0, second=0, microsecond=0) if last_start else None
    )
    try:
        state, attempt = db.begin_routine_attempt(
            athlete_id=athlete_id,
            execution_date=execution_date,
            routine_type=ROUTINE_MORNING,
            started_at=now,
            max_attempts=ROUTINE_MAX_ATTEMPTS,
            retry_gap=gap,
            start_by=start_by,
            runner=f"{runner}:{_PROCESS_TOKEN}",
            stale_after=_dt.timedelta(seconds=_routine_budget_s()),
        )
    except Exception as exc:
        logging.getLogger("titan.worker.runner").critical(
            "worker_routine_claim_failed",
            extra={"athlete_id": athlete_id, "error": str(exc)},
        )
        return None
    if state == "run":
        return attempt
    if state == "exhausted":  # the last attempt crashed before it could leave the day
        _leave_day(db, athlete_id, execution_date)
    elif state == "late" and key not in _LATE_LOGGED:
        _LATE_LOGGED.add(key)
        logging.getLogger("titan.worker.runner").warning(
            "worker_routine_too_late",
            extra={"athlete_id": athlete_id, "execution_date": execution_date,
                   "last_start_hour_utc": ROUTINE_LAST_START_HOUR_UTC},
        )
    return False


def _end_attempt(db: DatabaseManager, athlete_id: str, execution_date: str, *, attempt: int) -> None:
    """Clear attempt ``attempt``'s own "attempt in progress" mark (ADR-0069 §4β, M0-01).

    A later attempt's mark stays. A failure is logged; the mark then stops holding at the
    attempt's time limit.
    """
    try:
        db.end_routine_attempt(
            athlete_id=athlete_id, execution_date=execution_date, routine_type=ROUTINE_MORNING, attempt=attempt,
        )
    except Exception as exc:
        logging.getLogger("titan.worker.runner").exception(
            "worker_routine_end_failed",
            extra={"athlete_id": athlete_id, "execution_date": execution_date, "error": str(exc)},
        )


def _attempt_is_current(db: DatabaseManager, athlete_id: str, execution_date: str, attempt: int) -> bool:
    """True while this attempt still owns the open day; checked before a write or a send (M0-01).

    An attempt can outlive its time limit (the owner's thread is never abandoned) while a
    later attempt takes the day over. The attempt number is the fencing token. A failed
    check counts as not current: nothing is sent, and a later attempt runs the day.
    """
    try:
        current = db.routine_attempt_is_current(
            athlete_id=athlete_id, execution_date=execution_date, routine_type=ROUTINE_MORNING, attempt=attempt,
        )
    except Exception as exc:
        logging.getLogger("titan.worker.runner").exception(
            "worker_routine_fence_unreadable",
            extra={"athlete_id": athlete_id, "execution_date": execution_date, "error": str(exc)},
        )
        return False
    if not current:
        logging.getLogger("titan.worker.runner").warning(
            "worker_routine_superseded",
            extra={"athlete_id": athlete_id, "execution_date": execution_date, "attempt": attempt},
        )
    return current


def _complete_routine(db: DatabaseManager, athlete_id: str, execution_date: str) -> None:
    """Close a routine day that is left without a delivery (ADR-0060 D1 step 2, ADR-0067 D8.4)."""
    try:
        db.complete_routine_execution(
            athlete_id=athlete_id,
            execution_date=execution_date,
            routine_type=ROUTINE_MORNING,
            completed_at=_utc_now(),
        )
    except Exception as exc:
        # The day stays open with its attempts used up, so it is left again next cycle.
        logging.getLogger("titan.worker.runner").exception(
            "worker_routine_complete_failed",
            extra={"athlete_id": athlete_id, "execution_date": execution_date, "error": str(exc)},
        )


def _mark_delivered(db: DatabaseManager, athlete_id: str, execution_date: str) -> bool:
    """Record the day's delivery; a delivered day is never sent again (ADR-0067 D8.3).

    A failure (such as "database is locked") is tried again after short pauses. If it still
    fails, this process remembers that the day was sent, so it neither sends it again nor
    reports it as not delivered (D-109). False when the delivery is still unrecorded.
    """
    key = _day_key(db, athlete_id, execution_date)
    error = ""
    for delay in (0.0, *_MARK_RETRY_DELAYS_S):
        if delay:
            time.sleep(delay)
        try:
            db.mark_routine_delivered(
                athlete_id=athlete_id,
                execution_date=execution_date,
                routine_type=ROUTINE_MORNING,
                delivered_at=_utc_now(),
            )
        except Exception as exc:
            error = str(exc)
            continue
        _UNRECORDED_SENDS.discard(key)
        # Only now: a crash before the delivery is recorded keeps the mark, so no second briefing (MA-F5).
        _set_briefing_sending(db, athlete_id, execution_date, None)
        return True
    _UNRECORDED_SENDS.add(key)
    logging.getLogger("titan.worker.runner").critical(
        "worker_routine_delivery_unrecorded",
        extra={"athlete_id": athlete_id, "execution_date": execution_date, "error": error},
    )
    return False


def _leave_day(db: DatabaseManager, athlete_id: str, execution_date: str) -> None:
    """After the last attempt: CRITICAL, one message to Zaf, and the day is closed (ADR-0067 D8.4).

    When closing the day fails, the next poll closes it again without a second message (D-109).
    """
    log = logging.getLogger("titan.worker.runner")
    key = _day_key(db, athlete_id, execution_date)
    if key in _LEFT_DAYS:
        _complete_routine(db, athlete_id, execution_date)
        return
    _LEFT_DAYS.add(key)
    log.critical(
        "worker_routine_left",
        extra={"athlete_id": athlete_id, "execution_date": execution_date, "attempts": ROUTINE_MAX_ATTEMPTS},
    )
    try:
        from titan.integrations.telegram_bot import TitanTelegramBot

        # Zaf is the owner, so the owner's chat (TELEGRAM_CHAT_ID) gets it, never an athlete's.
        TitanTelegramBot(db=db).send_alert(
            title="Morning briefing not delivered",
            message=(
                f"The morning briefing of {athlete_id} for {execution_date} failed "
                f"{ROUTINE_MAX_ATTEMPTS} times and is left for today."
            ),
            level="critical",
        )
    except Exception as exc:
        log.exception("worker_routine_left_alert_failed", extra={"athlete_id": athlete_id, "error": str(exc)})
    _complete_routine(db, athlete_id, execution_date)


def _athlete_telegram(db: DatabaseManager, athlete_id: str):  # noqa: ANN202
    """The athlete's own Telegram: the owner's from .env, anyone else's private chat (ADR-0067 D10.1)."""
    from titan.integrations.telegram_bot import TitanTelegramBot

    chat = _require_telegram_ready(db, athlete_id)
    if chat is None:
        return TitanTelegramBot(db=db)
    return TitanTelegramBot(db=db, chat_id=chat, athlete_id=athlete_id)


_RESEND_NOTE = (
    "The morning briefing was interrupted; this is the decision TITAN made earlier today. "
    "If you already got this morning's message, this one repeats it."
)
_RECOMPUTED_NOTE = (
    "Your data changed after TITAN's first decision today, so today was computed again. "
    "If you already got a briefing today, follow this one."
)
_CAPPED_NOTE = (
    "Your data changed after TITAN's first decision today and today could not be computed "
    "again, so the session is at most EASY. If you already got a briefing today, follow this one."
)


# MA-F5 (ADR-0069 §8): a "sending" mark left by a crash means the briefing may have gone out.
# The next attempt does not send the session again; it sends this one line. Athletes have no
# /today (ADR-0067 D10.3), so theirs points to Zaf.
_CRASH_REMINDER_OWNER = "If this morning's briefing did not reach you, send /today."
_CRASH_REMINDER_ATHLETE = "If this morning's briefing did not reach you, let Zaf know."


def _crash_reminder_text(athlete_id: str) -> str:
    """The one line sent after a crash in the middle of the briefing's send (MA-F5)."""
    return _CRASH_REMINDER_OWNER if athlete_id == "owner" else _CRASH_REMINDER_ATHLETE


def _set_briefing_sending(db: DatabaseManager, athlete_id: str, execution_date: str, value: str | None) -> None:
    try:
        db.update_routine_resume(
            athlete_id=athlete_id, execution_date=execution_date, routine_type=ROUTINE_MORNING,
            fields={"sending": value},
        )
    except Exception as exc:  # the send goes ahead: a crash then resends, as before MA-F5
        logging.getLogger("titan.worker.runner").exception(
            "worker_routine_resume_unsaved", extra={"athlete_id": athlete_id, "error": str(exc)},
        )


def _mark_briefing_sending(db: DatabaseManager, athlete_id: str, execution_date: str) -> None:
    """Write "sending" before the briefing goes to Telegram (MA-F5, ADR-0069 §8)."""
    _set_briefing_sending(db, athlete_id, execution_date, _utc_now().isoformat())


def _send_crash_reminder(db: DatabaseManager, athlete_id: str) -> bool:
    """One line instead of a second briefing; True once Telegram took it (MA-F5)."""
    _require_consent(db, athlete_id)
    logging.getLogger("titan.worker.runner").warning(
        "worker_routine_crash_reminder", extra={"athlete_id": athlete_id},
    )
    return bool(_athlete_telegram(db, athlete_id).send_message(_crash_reminder_text(athlete_id), parse_mode=""))


def _session_caps(session: dict | None) -> dict:
    """The parts of a sent session a resend repeats: type, volume and its caps (D-109)."""
    keys = ("session_type", "distance_km", "duration_min", "max_duration_min", "max_zone")
    return {k: (session or {}).get(k) for k in keys if (session or {}).get(k) is not None}


def _caps_text(caps: dict | None) -> str | None:
    """'8 km · 45 min · at most 60 min · zone 2 at most', or None when there is nothing to say (D-109)."""
    caps = caps or {}
    if str(caps.get("session_type", "")).upper() == "REST":
        return None
    parts: list[str] = []
    for key, fmt in (("distance_km", "{:g} km"), ("duration_min", "{:g} min"),
                     ("max_duration_min", "at most {:g} min"), ("max_zone", "zone {:g} at most")):
        try:
            value = float(caps.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if value > 0 and not (key == "max_zone" and value >= 5):
            parts.append(fmt.format(value))
    return " · ".join(parts) or None


def _send_stored_decision(
    db: DatabaseManager, athlete_id: str, decision: dict, caps: dict | None = None, *, note: str = _RESEND_NOTE,
) -> bool:
    """Send the day's stored decision instead of computing it again (ADR-0067 D8.4).

    ``caps`` is the session computed with it, so the resend keeps its distance, duration
    and caps (D-109). The note says that it may repeat an earlier message (DW-06).
    """
    _require_consent(db, athlete_id)
    lines = [f"🌅 Today's session: {decision['session_post_governance']}"]
    volume = _caps_text(caps)
    if volume:
        lines.append(volume)
    if decision.get("locks_applied"):
        lines.append("Locks: " + ", ".join(str(lock) for lock in decision["locks_applied"]))
    lines.append(note)
    return bool(_athlete_telegram(db, athlete_id).send_message("\n".join(lines), parse_mode=""))


def _capped_at_easy(decision: dict) -> tuple[dict, dict]:
    """The stored decision, never above EASY, with EASY's 45-minute cap (D-109, INV-24)."""
    stored = str(decision.get("session_post_governance", "")).upper()
    session = stored if stored in _AT_MOST_EASY else "EASY"
    caps: dict = {"session_type": session}
    if session != "REST":
        caps["max_duration_min"] = _EASY_MAX_DURATION_MIN
    return {**decision, "session_post_governance": session}, caps


def _bind_day(coach, db: DatabaseManager, athlete_id: str, day: _MorningDay) -> None:  # noqa: ANN001
    """Give the coach the claimed day and the hooks of a resumable morning (D-109).

    The day, not the clock, dates the whole routine, so a run that crosses midnight still
    computes and records the day it was claimed for. Once the decision is recorded, the
    sent session and a hash of the inputs it was computed on are kept for a later attempt.
    The athlete is told of a system error at most once a day.
    """
    log = logging.getLogger("titan.worker.runner")
    where = {"athlete_id": athlete_id, "execution_date": day.execution_date, "routine_type": ROUTINE_MORNING}

    def _recorded(session: dict) -> None:
        day.decided = True
        try:
            db.update_routine_resume(**where, fields={
                "session": _session_caps(session),
                "inputs": db.routine_inputs_fingerprint(athlete_id, day.execution_date),
            })
        except Exception as exc:  # a retry then treats the inputs as changed and computes again
            log.exception("worker_routine_resume_unsaved", extra={"athlete_id": athlete_id, "error": str(exc)})

    def _alert_allowed() -> bool:
        try:
            if db.get_routine_resume(**where).get("athlete_alerted"):
                return False
            db.update_routine_resume(**where, fields={"athlete_alerted": _utc_now().isoformat()})
        except Exception as exc:  # unsure: telling twice is better than never
            log.exception("worker_routine_resume_unsaved", extra={"athlete_id": athlete_id, "error": str(exc)})
        return True

    coach.routine_date = day.execution_date
    # M0-01: a decision is recorded and a briefing sent only while this attempt owns the day.
    coach.attempt_is_current = lambda: _attempt_is_current(db, athlete_id, day.execution_date, day.attempt)
    coach.attempt_lost = False
    coach.replace_decision = day.replace_decision
    coach.briefing_note = day.note
    coach.on_decision_recorded = _recorded
    coach.before_system_error_alert = _alert_allowed
    # MA-F5: "sending" before the send; a refused send clears it, a crash leaves it.
    coach.before_briefing_send = lambda: _mark_briefing_sending(db, athlete_id, day.execution_date)
    coach.after_briefing_send = (
        lambda ok: None if ok else _set_briefing_sending(db, athlete_id, day.execution_date, None)
    )


def _resume_stored_day(db: DatabaseManager, athlete_id: str, stored: dict, day: _MorningDay) -> bool:
    """A later attempt of a day whose decision is stored; True once delivered (D-109).

    The stored decision is sent only while the athlete's inputs of that day are the ones it
    was computed on. Otherwise the day is computed again through the gated pipeline and the
    new decision replaces the stored one in place (one ``governance_outcomes`` row per day).
    If no new decision can be made, the stored one is sent at most EASY.
    """
    log = logging.getLogger("titan.worker.runner")
    resume = db.get_routine_resume(
        athlete_id=athlete_id, execution_date=day.execution_date, routine_type=ROUTINE_MORNING,
    )
    if db.routine_inputs_fingerprint(athlete_id, day.execution_date) == resume.get("inputs"):
        log.info("worker_routine_resend_stored", extra={"athlete_id": athlete_id, "attempt": day.attempt})
        if not _attempt_is_current(db, athlete_id, day.execution_date, day.attempt):
            return False
        return _send_stored_decision(db, athlete_id, stored, resume.get("session"))
    log.warning("worker_routine_inputs_changed", extra={"athlete_id": athlete_id, "attempt": day.attempt})
    day.replace_decision, day.note = True, _RECOMPUTED_NOTE
    try:
        delivered = _run_morning(db, athlete_id, day=day) is True
    except Exception as exc:
        log.exception("worker_routine_recompute_failed", extra={"athlete_id": athlete_id, "error": str(exc)})
        delivered = False
    if delivered or day.decided:
        return delivered
    if not _attempt_is_current(db, athlete_id, day.execution_date, day.attempt):
        return False
    capped, caps = _capped_at_easy(stored)
    log.warning(
        "worker_routine_resend_capped",
        extra={"athlete_id": athlete_id, "session": capped["session_post_governance"]},
    )
    return _send_stored_decision(db, athlete_id, capped, caps, note=_CAPPED_NOTE)


def _attempt_morning(db: DatabaseManager, athlete_id: str, execution_date: str, attempt: int) -> bool:
    """Run one claimed attempt of the day; True once the day's message is delivered (ADR-0067 D8.4).

    When the athlete's decision of that day is already stored, it is sent again only if the
    inputs did not change since; otherwise the day is computed again (D-109). Either way
    ``governance_outcomes`` keeps one row for one athlete and day. With nothing stored the
    routine runs. Not delivered after the last attempt: the day is left.
    """
    log = logging.getLogger("titan.worker.runner")
    delivered = False
    day = _MorningDay(execution_date=execution_date, attempt=attempt)
    try:
        resume = db.get_routine_resume(
            athlete_id=athlete_id, execution_date=execution_date, routine_type=ROUTINE_MORNING,
        )
        stored = db.get_governance_decision_on(athlete_id, execution_date)
        if not _attempt_is_current(db, athlete_id, execution_date, attempt):
            pass  # a later attempt took the day over, or it is closed (M0-01)
        elif resume.get("sending"):
            # An earlier attempt died while sending (MA-F5): the briefing may have arrived.
            delivered = _send_crash_reminder(db, athlete_id)
        elif stored is not None:
            delivered = _resume_stored_day(db, athlete_id, stored, day)
        else:
            delivered = _run_morning(db, athlete_id, day=day) is True
            log.info("morning_routine_complete", extra={"athlete_id": athlete_id, "delivered": delivered})
    except Exception as exc:
        log.exception("worker_cycle_error", extra={"athlete_id": athlete_id, "error": str(exc)})
        from titan.observability.metrics import get_metrics
        get_metrics().counter("worker_cycle_error")
    keep_mark = False
    if delivered:
        # Recorded before the mark is cleared (M0-18): a day with no mark and no delivery
        # could be claimed by the next attempt in between, which would send it again. When
        # the delivery cannot be recorded, the mark stays until its time limit, so another
        # process does not claim the sent day at once (M0-01 review).
        keep_mark = not _mark_delivered(db, athlete_id, execution_date)
    elif not _attempt_is_current(db, athlete_id, execution_date, attempt):
        pass  # superseded or closed: the day is the later attempt's, not this one's to leave
    elif attempt >= ROUTINE_MAX_ATTEMPTS:
        _leave_day(db, athlete_id, execution_date)
    else:
        log.warning(
            "worker_routine_not_delivered",
            extra={"athlete_id": athlete_id, "execution_date": execution_date, "attempt": attempt},
        )
    if not keep_mark:
        _end_attempt(db, athlete_id, execution_date, attempt=attempt)
    return delivered


def _warn_incomplete_routines(db: DatabaseManager, execution_date: str) -> None:
    """At startup, report routines claimed today that never returned (ADR-0060 D1 step 3)."""
    log = logging.getLogger("titan.worker.runner")
    try:
        rows = db.get_incomplete_routine_executions(execution_date)
    except Exception as exc:
        log.exception("worker_routine_state_unreadable", extra={"error": str(exc)})
        return
    for athlete_id, routine_type in rows:
        log.warning(
            "worker_routine_incomplete",
            extra={"athlete_id": athlete_id, "execution_date": execution_date, "routine_type": routine_type},
        )


def _require_consent(db: DatabaseManager, athlete_id: str) -> None:
    """Raise AthleteNotReady unless the athlete has a current consent (ADR-0067 D4.2).

    Checked first, so without consent nothing is called or written for the athlete.
    The owner is exempt (D4.5).
    """
    from titan.core.athlete import AthleteNotReady

    if not db.has_current_consent(athlete_id, now=_utc_now()):
        raise AthleteNotReady(athlete_id, "consent: none current")


def _require_garmin_ready(db: DatabaseManager, athlete_id: str) -> None:
    """Raise AthleteNotReady unless the athlete has a bound Garmin account with a usable token.

    The owner's Garmin login stays in .env and is not checked here (ADR-0067 D1.3). Any
    other athlete is paused while the token is missing or expired (D9.5).
    """
    from titan.core.athlete import OWNER_ATHLETE_ID, AthleteNotReady

    if athlete_id == OWNER_ATHLETE_ID:
        return
    account = db.get_athlete_account(athlete_id)
    if account is None or not account.get("garmin_user_id"):
        raise AthleteNotReady(athlete_id, "garmin: no account bound")
    if account["garmin_token_state"] != "ok":
        raise AthleteNotReady(athlete_id, f"garmin: token {account['garmin_token_state']}")
    # The state in the DB is not the token: without the encrypted file there is nothing to
    # sync with, so the athlete is not ready even when the state says 'ok' (MA-F2).
    from titan.integrations.garmin_sync import athlete_token_path

    if not athlete_token_path(athlete_id).exists():
        # Recorded as 'expired', as a sync that finds no token does (D9.5), so the operator
        # sees the relogin in `athletes.py list`; the athlete is refused either way.
        try:
            db.set_garmin_token_state(athlete_id, "expired")
        except Exception as exc:
            logging.getLogger("titan.worker.runner").exception(
                "athlete_token_state_unsaved", extra={"athlete_id": athlete_id, "error": str(exc)},
            )
        raise AthleteNotReady(athlete_id, "garmin: token file missing")


def _record_garmin_token_state(db: DatabaseManager, athlete_id: str, garmin) -> None:  # noqa: ANN001
    """After the morning, pause an athlete whose stored Garmin token was missing or rejected (D9.5)."""
    from titan.core.athlete import OWNER_ATHLETE_ID

    if athlete_id == OWNER_ATHLETE_ID or not getattr(garmin, "token_expired", False):
        return
    db.set_garmin_token_state(athlete_id, "expired")
    logging.getLogger("titan.worker.runner").warning(
        "athlete_garmin_token_expired", extra={"athlete_id": athlete_id},
    )


def _require_telegram_ready(db: DatabaseManager, athlete_id: str) -> str | None:
    """Return the athlete's private Telegram chat; raise AthleteNotReady when none is bound.

    The owner's chat stays TELEGRAM_CHAT_ID in .env (ADR-0067 D1.3), so None is returned
    for the owner. Any other athlete is never sent anything without their own chat (D7.1).
    """
    from titan.config.settings import get_settings
    from titan.core.athlete import OWNER_ATHLETE_ID, AthleteNotReady, canonical_chat_id

    if athlete_id == OWNER_ATHLETE_ID:
        return None
    account = db.get_athlete_account(athlete_id)
    if account is None or not account.get("telegram_chat_id"):
        raise AthleteNotReady(athlete_id, "telegram: no chat bound")
    stored = account["telegram_chat_id"]
    # Fail closed on a chat stored before D-107 in another form ("01001", "+1"): it is sent
    # to int(stored), which may be another athlete's or the owner's chat. Zaf is told and
    # binds it again with ``athletes.py chat``; nothing is sent to it meanwhile.
    if canonical_chat_id(stored) != stored:
        raise AthleteNotReady(athlete_id, "telegram: chat id not in canonical form, run athletes.py chat")
    if stored == canonical_chat_id(get_settings().TELEGRAM_CHAT_ID, allow_negative=True):
        raise AthleteNotReady(athlete_id, "telegram: chat is the owner's, run athletes.py chat")
    return stored


def sync_athlete_on_request(db: DatabaseManager, athlete_id: str) -> str:
    """/sync from an athlete's own chat: sync and store that athlete's Garmin data only (D10.3).

    The reply never carries error details or another athlete's data. Not for the owner,
    whose /sync stays the console callback in titan/main.py.
    """
    from titan.core.athlete import OWNER_ATHLETE_ID, AthleteNotReady, load_athlete_profile
    from titan.integrations.garmin_sync import GarminSync
    from titan.orchestration.garmin_persistence import persist_garmin_data

    log = logging.getLogger("titan.worker.runner")
    if athlete_id == OWNER_ATHLETE_ID:
        raise ValueError("the owner's /sync is the console callback, not this one")
    try:
        _require_consent(db, athlete_id)
        load_athlete_profile(db, athlete_id)
        _require_garmin_ready(db, athlete_id)
    except AthleteNotReady as exc:
        log.info("athlete_sync_not_ready", extra={"athlete_id": athlete_id, "reason": exc.reason})
        return "⏸ Your setup is not complete yet, so nothing was synced."
    garmin = GarminSync(athlete_id=athlete_id, expected_garmin_user_id=_bound_garmin_account(db, athlete_id))
    try:
        if not garmin.connect():
            return "⏸ Garmin is not connected for you, so nothing was synced."
        data = garmin.sync_all()
        persist_garmin_data(
            db, data, _utc_now().date().isoformat(), athlete_id=athlete_id,
            emit=lambda action, **fields: log.info(action, extra={"athlete_id": athlete_id, **fields}),
        )
    except Exception:
        log.exception("athlete_sync_failed", extra={"athlete_id": athlete_id})
        return "❌ Sync failed. Please try again later."
    finally:
        _record_garmin_token_state(db, athlete_id, garmin)
    return "✅ Sync complete."


def _bound_garmin_account(db: DatabaseManager, athlete_id: str) -> str | None:
    """The Garmin account bound to the athlete, or None (the owner's lives in .env)."""
    from titan.core.athlete import OWNER_ATHLETE_ID

    if athlete_id == OWNER_ATHLETE_ID:
        return None
    return (db.get_athlete_account(athlete_id) or {}).get("garmin_user_id")


def _build_daily_coach(db: DatabaseManager, athlete_id: str = "owner"):
    """Compose a DailyCoach for one athlete, mirroring the titan/main.py composition root.

    Every collaborator is built with the constructor signature it actually has;
    the worker loops used to pass keyword arguments these constructors do not
    accept, so each morning cycle failed with TypeError before any work ran.

    The profile is the athlete's own (ADR-0067 D5): the owner's from .env, any other
    athlete's from athlete_profiles. AthleteNotReady is raised before any collaborator
    is built when that athlete has no current consent (checked first) or no complete profile.
    """
    from titan.core.athlete import load_athlete_profile
    from titan.features.nutrition_optimizer import NutritionOptimizer
    from titan.features.optimal_time_calculator import OptimalTimeCalculator
    from titan.features.weekly_planner import WeeklyPlanGenerator
    from titan.integrations.garmin_sync import GarminSync
    from titan.integrations.weather_api import WeatherAPI
    from titan.orchestration.daily_coach import DailyCoach
    from titan.orchestration.engine_registry import EngineRegistry
    from titan.science.acwr_engine import ACWREngine
    from titan.science.glycogen_model import GlycogenModel

    _require_consent(db, athlete_id)
    profile = load_athlete_profile(db, athlete_id)
    _require_garmin_ready(db, athlete_id)
    _require_telegram_ready(db, athlete_id)
    # The owner keeps WEATHER_LOCATION; any other athlete's weather is for the location in
    # their own profile (ADR-0067 D5.1), so two cities give two ESIs.
    weather = (
        WeatherAPI(athlete_id="owner") if athlete_id == "owner"
        else WeatherAPI(location=f"{profile.location_city},{profile.location_country}", athlete_id=athlete_id)
    )
    engines = EngineRegistry.from_db(db=db, athlete_id=athlete_id)
    return DailyCoach(
        garmin_sync=GarminSync(athlete_id=athlete_id, expected_garmin_user_id=_bound_garmin_account(db, athlete_id)),
        weather_api=weather,
        # Another athlete's messages go to their own chat only, never the owner's (ADR-0067 D10.1).
        telegram_bot=_athlete_telegram(db, athlete_id),
        hrv_engine=engines.hrv,
        tsb_engine=engines.tsb,
        readiness_engine=engines.readiness,
        optimal_time_calc=OptimalTimeCalculator(weather),
        nutrition_optimizer=NutritionOptimizer(GlycogenModel()),
        weekly_planner=WeeklyPlanGenerator(engines.hrv, engines.tsb, ACWREngine(), db=db, athlete_id=athlete_id),
        db=db,
        athlete_id=athlete_id,
        engines=engines,
        # The owner's comes from .env as in the console (titan/main.py), so TRIMP uses one
        # max HR (T5-117); another athlete's from athlete_profiles (ADR-0067 D5).
        athlete_profile=profile,
    )


def _generate_weekly_plan(coach, db: DatabaseManager, athlete_id: str) -> dict:  # noqa: ANN001
    """Build next week's plan as the console does, store it and send it to Telegram (D-020)."""
    from titan.core.athlete import load_athlete_profile

    # The profile the coach was built with (D-033); stand-in coaches in tests have none.
    # Never the owner's .env for another athlete (ADR-0067 D7.1).
    profile = getattr(coach, "athlete_profile", None) or load_athlete_profile(db, athlete_id)
    plan = coach.weekly_planner.generate_weekly_plan(
        athlete_profile=profile.to_dict(), phase=profile.training_phase,
    )
    db.save_weekly_plan(athlete_id=athlete_id, week_start=plan["week_start"], plan=plan)
    logging.getLogger("titan.worker.runner").info(
        "worker_weekly_plan_saved", extra={"athlete_id": athlete_id, "week_start": plan["week_start"]},
    )
    coach.telegram.send_weekly_plan(plan)
    return plan


def _plan_covers(plan: dict | None, day: _dt.date) -> bool:
    """True when ``day`` falls inside the seven days that start at the plan's week_start."""
    try:
        start = _dt.date.fromisoformat(str((plan or {}).get("week_start"))[:10])
    except ValueError:
        return False
    return start <= day < start + _dt.timedelta(days=7)


def _prepare_weekly_plan(coach, db: DatabaseManager, athlete_id: str, today: _dt.date) -> None:  # noqa: ANN001
    """Before the morning routine, give the planner this week's stored plan (D-020).

    With no stored plan for this week (first start, or the worker was down on
    Sunday), one is built now, so the morning never falls back to the planner's
    default session. A failure here is logged and the routine still runs.
    """
    try:
        stored = db.get_latest_weekly_plan(athlete_id=athlete_id, on_or_before=today.isoformat())
        if _plan_covers(stored, today):
            coach.weekly_planner.last_plan = stored
            return
        # A plan built mid-week starts tomorrow (WeeklyPlanGenerator), so a retry the same
        # day finds it here and does not build and send a second one (MA-F4, D-126).
        tomorrow = (today + _dt.timedelta(days=1)).isoformat()
        upcoming = db.get_latest_weekly_plan(athlete_id=athlete_id, on_or_before=tomorrow)
        if upcoming is not None and str(upcoming.get("week_start"))[:10] == tomorrow:
            coach.weekly_planner.last_plan = upcoming
            return
        _generate_weekly_plan(coach, db, athlete_id)
    except Exception as exc:
        logging.getLogger("titan.worker.runner").exception(
            "worker_weekly_plan_failed", extra={"athlete_id": athlete_id, "error": str(exc)},
        )


def _plan_next_week_on_sunday(coach, db: DatabaseManager, athlete_id: str, today: _dt.date) -> None:  # noqa: ANN001
    """After Sunday's routine, build the plan of the week that starts tomorrow (D-020)."""
    if today.weekday() != 6:
        return
    tomorrow = (today + _dt.timedelta(days=1)).isoformat()
    try:
        stored = db.get_latest_weekly_plan(athlete_id=athlete_id, on_or_before=tomorrow)
        if stored is not None and str(stored.get("week_start"))[:10] == tomorrow:
            return
        _generate_weekly_plan(coach, db, athlete_id)
    except Exception as exc:
        logging.getLogger("titan.worker.runner").exception(
            "worker_weekly_plan_failed", extra={"athlete_id": athlete_id, "error": str(exc)},
        )


def _run_morning(db: DatabaseManager, athlete_id: str, *, day: _MorningDay | None = None) -> bool:
    """One worker morning: this week's plan, the routine, and on Sunday next week's plan.

    Returns what the routine returns: True when the decision was made and the day's
    message delivered. An athlete with no current consent, no complete profile, or without
    a bound Garmin account and a usable token, raises AthleteNotReady here, before the
    coach, Garmin, weather or Telegram is built or called (ADR-0067 D4.2, D7.1, D9.5).
    """
    coach = _build_daily_coach(db, athlete_id=athlete_id)
    if day is None:
        today = _utc_now().date()
    else:  # the claimed day, so a run that crosses midnight stays on it (D-109)
        today = _dt.date.fromisoformat(day.execution_date)
        _bind_day(coach, db, athlete_id, day)
    _prepare_weekly_plan(coach, db, athlete_id, today)
    try:
        delivered = coach.run_morning_routine()
    finally:
        _record_garmin_token_state(db, athlete_id, getattr(coach, "garmin", None))
    _plan_next_week_on_sunday(coach, db, athlete_id, today)
    return delivered is True


def run_forever(db_path: str, shutdown_event: threading.Event | None = None) -> None:
    """ADR-0057 worker entrypoint. Runs DailyCoach morning routine aligned to 07:00 UTC."""
    from titan.core.athlete import UniversalAthleteProfile
    from titan.core.database import DatabaseManager

    _stop = shutdown_event if shutdown_event is not None else threading.Event()
    log = logging.getLogger("titan.worker.runner")
    p = Path(db_path)
    db = DatabaseManager(db_name=p.name, db_dir=p.parent)

    log.info("worker_started", extra={"db": db_path})

    settings = get_settings()
    # A malformed ATHLETE_* value stops the worker at start (from_env exits),
    # not at the first 07:00 routine.
    UniversalAthleteProfile.from_env()
    heartbeat = p.parent / HEARTBEAT_FILE
    interval_s = settings.WORKER_HEARTBEAT_INTERVAL_S

    _warn_incomplete_routines(db, _utc_now().date().isoformat())
    _athlete_housekeeping(db, at_start=True)

    if settings.TITAN_MULTI_ATHLETE == "1":
        _run_with_scheduler(db, _stop, heartbeat=heartbeat, interval_s=interval_s)
        return

    while True:
        _write_heartbeat(heartbeat)
        # A backup that fails never stops the morning (DW-04, D-111), as in the round.
        try:
            _run_backup(db)
        except Exception as exc:
            log.exception("worker_backup_failed", extra={"error": str(exc)})
        _athlete_housekeeping(db)
        if _run_due_routine(db, _stop, heartbeat, interval_s, settings.WORKER_ROUTINE_BUDGET_S):
            log.info("worker_graceful_exit")
            return
        # Sleep until the next 07:00 UTC.
        # Timezone alignment is out of scope — worker uses UTC 07:00 throughout.
        wait_s = _seconds_until_next_run(7, 0)
        log.info("worker_sleeping", extra={"seconds": wait_s})
        if _sleep_with_heartbeat(_stop, wait_s, interval_s, heartbeat):
            log.info("worker_graceful_exit")
            return


def _run_due_routine(
    db: DatabaseManager, stop: threading.Event, heartbeat: Path, interval_s: float, budget_s: float
) -> bool:
    """Run the owner's morning routine if it is due today; True if ``stop`` fired.

    Due means at or after 07:00 UTC and today's message not yet delivered: the row in
    ``worker_routine_executions`` decides, so a restart never sends the day twice
    (ADR-0060 D1, INV-15). An attempt that did not deliver is followed by the next one
    after ``ROUTINE_RETRY_DELAY_S``, at most ``ROUTINE_MAX_ATTEMPTS`` a day (ADR-0067 D8.4).
    A failed claim is retried every ``interval_s`` until it succeeds or the stop event fires.
    """
    log = logging.getLogger("titan.worker.runner")
    while True:
        now = _utc_now()
        if now.hour < ROUTINE_HOUR_UTC:
            log.info("worker_routine_not_due", extra={"due_hour_utc": ROUTINE_HOUR_UTC})
            return False
        # Spaced like the console's claim, so an attempt the console just took is not taken
        # again at once; no noon limit for the owner (D-111, D-113).
        attempt = _claim_routine(db, "owner", now, spaced=True, last_start=False)
        if attempt is None:
            if _sleep_with_heartbeat(stop, interval_s, interval_s, heartbeat):
                return True
            continue
        if attempt is False:
            if _owner_day_open(db, now.date().isoformat()):
                # Another attempt (the console's) is not due again yet: wait for it (D-113).
                if _sleep_with_heartbeat(stop, interval_s, interval_s, heartbeat):
                    return True
                continue
            log.info("worker_routine_already_ran", extra={"execution_date": now.date().isoformat()})
            return False
        delivered = _run_routine_supervised(
            db, heartbeat, interval_s, budget_s, execution_date=now.date().isoformat(), attempt=attempt
        )
        if delivered or attempt >= ROUTINE_MAX_ATTEMPTS:
            return False
        if _sleep_with_heartbeat(stop, ROUTINE_RETRY_DELAY_S, interval_s, heartbeat):
            return True


def _owner_day_open(db: DatabaseManager, execution_date: str) -> bool:
    """True while the owner's morning of that day is neither delivered nor left (D-113).

    A failed read counts as closed: the worker then sleeps to the next day instead of
    polling a database it cannot read.
    """
    try:
        return ("owner", ROUTINE_MORNING) in db.get_incomplete_routine_executions(execution_date)
    except Exception as exc:
        logging.getLogger("titan.worker.runner").exception(
            "worker_routine_state_read_failed", extra={"error": str(exc)},
        )
        return False


def _run_routine_supervised(
    db: DatabaseManager,
    heartbeat: Path,
    interval_s: float,
    budget_s: float,
    *,
    execution_date: str | None = None,
    attempt: int = 1,
) -> bool:
    """Run one morning attempt of the owner in a watched thread (INV-23(1)); True if delivered.

    The heartbeat keeps beating while the routine runs within ``budget_s``. Past
    the budget it stops, with one CRITICAL event, so the healthcheck reports the
    hung routine. A routine is never abandoned: this waits for it to finish.
    When ``execution_date`` is given, the attempt follows the crash rule of that
    day (ADR-0067 D8.4): delivery recorded, or the day left after the last attempt.
    """
    log = logging.getLogger("titan.worker.runner")
    delivered: list[bool] = [False]

    def _cycle() -> None:
        if execution_date is not None:
            delivered[0] = _attempt_morning(db, "owner", execution_date, attempt)
            return
        try:
            delivered[0] = _run_morning(db, "owner") is True
            log.info("morning_routine_complete")
        except Exception as exc:
            log.exception(
                "worker_cycle_error",
                extra={"error": str(exc)},
            )
            from titan.observability.metrics import get_metrics
            get_metrics().counter("worker_cycle_error")

    thread = threading.Thread(target=_cycle, name="MorningRoutine", daemon=True)
    started = time.monotonic()
    thread.start()
    overrun = False
    while True:
        thread.join(timeout=interval_s)
        if not thread.is_alive():
            break
        elapsed = time.monotonic() - started
        if elapsed <= budget_s:
            _write_heartbeat(heartbeat)
        elif not overrun:
            overrun = True
            log.critical(
                "worker_routine_overrun",
                extra={"elapsed_s": round(elapsed), "budget_s": budget_s},
            )
            _tell_zaf_overrun(db, elapsed, budget_s)
    _write_heartbeat(heartbeat)
    return delivered[0]


def _tell_zaf_overrun(db: DatabaseManager, elapsed_s: float, budget_s: float) -> None:
    """Tell Zaf once that the owner's morning is still running past its budget (DW-05, D-111).

    The routine thread cannot be stopped from here, and the stopped heartbeat only reaches
    whoever reads the healthcheck, so the owner is told on Telegram too. A failed send is
    logged; the routine is still waited for.
    """
    try:
        from titan.integrations.telegram_bot import TitanTelegramBot

        TitanTelegramBot(db=db).send_message(
            f"⏳ The morning routine has been running for {round(elapsed_s / 60)} min "
            f"(budget {round(budget_s / 60)} min). The worker is waiting for it; today's "
            "briefing may be late or missing.",
            parse_mode="",
        )
    except Exception as exc:
        logging.getLogger("titan.worker.runner").exception(
            "worker_routine_overrun_alert_failed", extra={"error": str(exc)},
        )


def run_owner_morning_if_due(db: DatabaseManager) -> bool:
    """One check of the owner's morning for the console: run it when due; True if delivered.

    Due means at or after 07:00 UTC and the day neither delivered nor left nor waiting for
    its next attempt. The day is claimed in ``worker_routine_executions`` as the worker
    claims it, so a console and a worker on the same database send one morning, and a
    console that missed the 07:00 minute still runs that day (DW-02, DW-10, D-111). As in the
    owner loop there is no noon limit; attempts are ``ROUTINE_RETRY_DELAY_S`` apart.
    """
    now = _utc_now()
    if now.hour < ROUTINE_HOUR_UTC:
        return False
    attempt = _claim_routine(db, "owner", now, spaced=True, last_start=False, runner="console")
    if attempt is None or attempt is False:
        return False
    return _attempt_morning(db, "owner", now.date().isoformat(), attempt)


_TODAY_NOTE = "You asked with /today: this is the decision TITAN made earlier today."


def run_owner_today(db: DatabaseManager, lock: threading.Lock) -> str:
    """The console's ``/today``: one decision per day, as the scheduled morning (OW-F4, D-128).

    With today's decision stored, it is sent again and nothing is written. Without one, the
    audit row is written first (INV-22), then the day is claimed and run as the worker runs
    it, so ``governance_outcomes`` keeps one row for the owner's day (INV-15). ``lock`` is
    the coach's routine lock: a morning already running is never started twice.

    Returns what happened: ``"resent"``, ``"delivered"``, ``"send_failed"``, ``"busy"``,
    ``"audit_failed"``, ``"claim_failed"`` or ``"closed"`` (the day was left or is not due
    for another attempt yet, and no decision is stored).
    """
    if not lock.acquire(blocking=False):
        return "busy"
    try:
        now = _utc_now()
        execution_date = now.date().isoformat()
        stored = db.get_governance_decision_on("owner", execution_date)
        if stored is not None:
            resume = db.get_routine_resume(
                athlete_id="owner", execution_date=execution_date, routine_type=ROUTINE_MORNING,
            )
            sent = _send_stored_decision(db, "owner", stored, resume.get("session"), note=_TODAY_NOTE)
            return "resent" if sent else "send_failed"
        try:
            db.log_coach_action(
                coach_id="console:/today",
                action_type="TELEGRAM_TODAY",
                target_athlete_id="owner",
                action_detail=execution_date,
                resource="telegram",
            )
        except Exception as exc:
            logging.getLogger("titan.worker.runner").critical(
                "audit_write_failed",
                extra={"surface": "telegram", "action_type": "TELEGRAM_TODAY", "error": str(exc)},
            )
            from titan.observability.metrics import get_metrics

            get_metrics().counter("audit_write_failure", labels={"surface": "telegram"})
            return "audit_failed"
        attempt = _claim_routine(db, "owner", now, spaced=True, last_start=False, runner="console")
        if attempt is None:
            return "claim_failed"
        if attempt is False:
            return "closed"
        return "delivered" if _attempt_morning(db, "owner", execution_date, attempt) else "send_failed"
    finally:
        lock.release()


def _run_with_scheduler(
    db: DatabaseManager,
    stop_event: threading.Event,
    *,
    heartbeat: Path | None = None,
    interval_s: float = 60.0,
) -> None:
    """Multi-athlete coaching loop via CoachingScheduler (ADR-0046 / P26-03, ADR-0067 D8).

    Activated when TITAN_MULTI_ATHLETE=1. One callback, the round, runs every 60 s poll:
    every athlete in the fixed order, the owner first, each ready one in its own child
    process (D8.1, D8.5). The athletes are read from the database on every round, so a new
    athlete joins and a deleted one leaves without a restart.
    """
    from titan.orchestration.coaching_scheduler import CoachingScheduler

    log = logging.getLogger("titan.worker.scheduler")

    # Run interval: 60s poll; coaching fires once per athlete per day at or
    # after 07:00 UTC. The daily gate is the row in worker_routine_executions
    # (ADR-0060 D1, ADR-0067 D8.4), so it survives a restart.
    scheduler = CoachingScheduler(interval_seconds=60.0)
    backed_up_on: list[str] = []

    def _round() -> None:
        # The daily backup, as the owner loop takes it (DR-01); a restart may take one more.
        today = _utc_now().date().isoformat()
        if today not in backed_up_on:
            try:
                _run_backup(db)
            except Exception as exc:
                log.exception("worker_backup_failed", extra={"error": str(exc)})
            backed_up_on[:] = [today]
        _morning_round(db)

    scheduler.register_athlete("round", _round)

    listener = _start_command_listener(db)
    scheduler.start()
    log.info("coaching_scheduler_started", extra={"athletes": db.list_athletes_in_order()})

    # Supervise until the stop event fires (SIGTERM / main() shutdown).
    try:
        _supervise_scheduler(scheduler, stop_event, heartbeat=heartbeat, interval_s=interval_s)
    finally:
        scheduler.stop()
        if listener is not None:
            listener.stop_bot()
    log.info("coaching_scheduler_stopped")


def _command_bot(db: DatabaseManager):  # noqa: ANN202
    """The owner's bot with the athletes' /sync wired to this worker (D-103, finding К-1).

    It routes each athlete's own chat: /consent, /agree, /sync, /stop, /start, /help
    (ADR-0067 D10). Owner commands with no callback here answer "not ready".
    """
    from titan.integrations.telegram_bot import TitanTelegramBot

    bot = TitanTelegramBot(db=db)
    bot.register_athlete_command("sync", lambda athlete_id: sync_athlete_on_request(db, athlete_id))
    return bot


def _start_command_listener(db: DatabaseManager):  # noqa: ANN202
    """Listen for Telegram commands in multi-athlete mode, so an athlete can give consent
    in a Docker-only install (D-103). Without a bot token nothing listens and the round runs.
    """
    log = logging.getLogger("titan.worker.scheduler")
    bot = _command_bot(db)
    if bot.bot is None:
        log.warning("command_listener_not_started", extra={"reason": "no bot token or telebot"})
        return None
    bot.start_bot()
    log.info("command_listener_started")
    return bot


def _morning_round(db: DatabaseManager) -> None:
    """One scheduler poll: athletes past 30 days after /stop are deleted, then every athlete
    in the fixed order, the owner first (ADR-0067 D4.3, D8.1). One athlete's failure never
    stops the round for the others (INV-23(3)).
    """
    log = logging.getLogger("titan.worker.scheduler")
    if _utc_now().hour < ROUTINE_HOUR_UTC:
        return
    _athlete_housekeeping(db)
    for athlete_id in db.list_athletes_in_order():
        try:
            _scheduled_morning(db, athlete_id)
        except Exception as exc:
            log.exception("scheduler_athlete_cycle_error", extra={"athlete_id": athlete_id, "error": str(exc)})


def _scheduled_morning(db: DatabaseManager, athlete_id: str) -> None:
    """One poll for one athlete: when it is due and the athlete is ready, one attempt in a child process."""
    log = logging.getLogger("titan.worker.scheduler")
    now = _utc_now()
    if now.hour < ROUTINE_HOUR_UTC:
        return
    # Not ready: nothing is called or written for the athlete, not even the claim row, and
    # Zaf is told once that day (ADR-0067 D4.2, D7.1). After /stop the routine does not start.
    try:
        problem = _readiness_problem(db, athlete_id)
    except Exception as exc:
        log.exception("scheduler_readiness_check_failed", extra={"athlete_id": athlete_id, "error": str(exc)})
        return
    if problem is not None:
        log.info("scheduler_athlete_not_ready", extra={"athlete_id": athlete_id, "reason": problem})
        _tell_zaf_not_ready(db, athlete_id, problem, now)
        return
    # The attempt is counted before it runs, so a crash counts too and a day is tried at
    # most ROUTINE_MAX_ATTEMPTS times (ADR-0067 D8.4); a failed claim retries next poll.
    # Attempts are ROUTINE_RETRY_DELAY_S apart, and no day starts after
    # ROUTINE_LAST_START_HOUR_UTC (D-109).
    attempt = _claim_routine(db, athlete_id, now, spaced=True)
    if attempt is None or attempt is False:
        return
    _run_attempt(db, athlete_id, now.date().isoformat(), attempt)


# Exit codes of the child process: delivered, not delivered and already handled there, or
# delivered but the child could not record it, so the parent records it (D-109).
_CHILD_DELIVERED = 0
_CHILD_NOT_DELIVERED = 3
_CHILD_SENT_UNRECORDED = 4


def _child_morning(db_path: str, athlete_id: str, execution_date: str, attempt: int) -> None:
    """Child-process entry: one attempt of one athlete on its own connection (ADR-0067 D8.5)."""
    from titan.core.database import DatabaseManager

    _configure_logging()
    path = Path(db_path)
    db = DatabaseManager(db_name=path.name, db_dir=path.parent)
    try:
        delivered = _attempt_morning(db, athlete_id, execution_date, attempt)
        unrecorded = _day_key(db, athlete_id, execution_date) in _UNRECORDED_SENDS
    finally:
        db.close()
    if delivered and unrecorded:
        sys.exit(_CHILD_SENT_UNRECORDED)
    sys.exit(_CHILD_DELIVERED if delivered else _CHILD_NOT_DELIVERED)


# What the child process runs; a seam so tests can run a stand-in in a real child process.
_CHILD_ENTRY = _child_morning


def _routine_budget_s() -> float:
    """The time limit of one athlete's attempt (``WORKER_ROUTINE_BUDGET_S``, ADR-0067 D8.5)."""
    return float(get_settings().WORKER_ROUTINE_BUDGET_S)


def _run_attempt(db: DatabaseManager, athlete_id: str, execution_date: str, attempt: int) -> bool:
    """Run one claimed attempt in its own child process with a time limit; True if delivered.

    Past ``WORKER_ROUTINE_BUDGET_S`` the process is killed: SQLite rolls back its open
    transaction, the attempt stays counted, and the round moves on (ADR-0067 D8.5). A thread
    is not used because it cannot be stopped safely. A child that was killed or died before
    it could handle its own end leaves the day here when that was the last attempt.
    """
    import multiprocessing

    log = logging.getLogger("titan.worker.scheduler")
    budget_s = _routine_budget_s()
    process = multiprocessing.get_context("spawn").Process(
        target=_CHILD_ENTRY,
        args=(str(db.db_path), athlete_id, execution_date, attempt),
        name=f"morning-{athlete_id}",
        daemon=True,
    )
    process.start()
    process.join(timeout=budget_s)
    if process.is_alive():
        process.kill()
        process.join()
        log.critical(
            "worker_routine_killed",
            extra={"athlete_id": athlete_id, "attempt": attempt, "budget_s": budget_s},
        )
    recorded = True
    if process.exitcode == _CHILD_SENT_UNRECORDED:
        # The briefing reached Telegram: record it here, and never send it again (D-109).
        # Before the mark is cleared (M0-18); if it still cannot be recorded, the mark stays.
        recorded = _mark_delivered(db, athlete_id, execution_date)
    # A killed child cannot clear its own mark (ADR-0069 §4β).
    if recorded:
        _end_attempt(db, athlete_id, execution_date, attempt=attempt)
    if process.exitcode in (_CHILD_DELIVERED, _CHILD_SENT_UNRECORDED):
        return True
    if process.exitcode != _CHILD_NOT_DELIVERED:
        log.critical(
            "worker_routine_child_died",
            extra={"athlete_id": athlete_id, "attempt": attempt, "exitcode": process.exitcode},
        )
        if attempt >= ROUTINE_MAX_ATTEMPTS:
            _leave_day(db, athlete_id, execution_date)
    return False


def _supervise_scheduler(
    scheduler, stop_event: threading.Event, *, heartbeat: Path | None, interval_s: float  # noqa: ANN001
) -> None:
    """Watchdog for the CoachingScheduler thread (INV-23(2)).

    A dead thread is never silent: CRITICAL event, ``worker_thread_died_total``,
    then a restart. The heartbeat is written only while the thread is alive.
    """
    log = logging.getLogger("titan.worker.scheduler")
    if heartbeat is not None:
        _write_heartbeat(heartbeat)
    while not stop_event.wait(timeout=interval_s):
        if not scheduler.is_alive():
            log.critical("worker_thread_died", extra={"thread_name": "CoachingScheduler"})
            from titan.observability.metrics import get_metrics

            get_metrics().counter("worker_thread_died_total", labels={"thread": "CoachingScheduler"})
            scheduler.start()
            log.info("worker_thread_restarted", extra={"thread_name": "CoachingScheduler"})
        if heartbeat is not None and scheduler.is_alive():
            _write_heartbeat(heartbeat)


def main() -> None:
    _configure_logging()
    _signal.signal(_signal.SIGTERM, _handle_sigterm)
    lock = acquire_worker_lock()
    if lock is None:
        logger.info("Worker already running — exiting")
        sys.exit(0)
    db_path = str(Path(get_settings().TITAN_DATA_DIR) / "titan_core.db")
    try:
        run_forever(db_path, shutdown_event=_shutdown)
    finally:
        lock.close()
        logger.info("worker_stopped")


if __name__ == "__main__":
    main()

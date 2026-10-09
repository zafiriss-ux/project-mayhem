"""titan.worker — background effect runner (ADR-0057).

Owns all write-heavy side effects: Garmin sync, Telegram poller,
morning routine scheduler. Enforces a single-instance advisory lock so
docker restart never spawns a duplicate.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
import signal as _signal
import sys
import threading
import time
from io import IOBase
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

from titan.config.settings import get_settings

logger = logging.getLogger(__name__)

def _get_lock_file() -> Path:
    """Return the worker lock file path — lazy so tests can monkeypatch TITAN_DATA_DIR.

    P26-05 / A1-F3: was a module-level constant that froze TITAN_DATA_DIR at
    first import, bypassing the P15-ARCH5 autouse cache_clear fixture.
    """
    return Path(get_settings().TITAN_DATA_DIR) / "worker.lock"

_shutdown = threading.Event()


def _handle_sigterm(signum, frame):  # noqa: ANN001
    log = logging.getLogger("titan.worker.signal")
    log.info("worker_shutdown_requested")
    _shutdown.set()


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


def _seconds_until_next_run(hour: int = 7, minute: int = 0) -> float:
    """Return seconds until next HH:MM UTC. Always > 0."""
    now = _dt.datetime.now(_dt.UTC)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += _dt.timedelta(days=1)
    return (target - now).total_seconds()


ROUTINE_MORNING = "morning"
ROUTINE_HOUR_UTC = 7


def _utc_now() -> _dt.datetime:
    """Current UTC time; one seam so tests can pin the clock."""
    return _dt.datetime.now(_dt.UTC)


def _claim_routine(db: DatabaseManager, athlete_id: str, now: _dt.datetime) -> bool | None:
    """Claim today's morning routine in ``worker_routine_executions`` (ADR-0060 D1, INV-15).

    True: this worker claimed it and runs it. False: it already started today,
    so it is skipped. None: the claim itself failed; the routine does not run
    this cycle (fail closed) and the caller retries on its next cycle.
    """
    try:
        return db.claim_routine_execution(
            athlete_id=athlete_id,
            execution_date=now.date().isoformat(),
            routine_type=ROUTINE_MORNING,
            started_at=now,
        )
    except Exception as exc:
        logging.getLogger("titan.worker.runner").critical(
            "worker_routine_claim_failed",
            extra={"athlete_id": athlete_id, "error": str(exc)},
        )
        return None


def _complete_routine(db: DatabaseManager, athlete_id: str, execution_date: str) -> None:
    """Record that a claimed routine returned (ADR-0060 D1 step 2)."""
    try:
        db.complete_routine_execution(
            athlete_id=athlete_id,
            execution_date=execution_date,
            routine_type=ROUTINE_MORNING,
            completed_at=_utc_now(),
        )
    except Exception as exc:
        # The claim row stays, so the routine is still not repeated today.
        logging.getLogger("titan.worker.runner").exception(
            "worker_routine_complete_failed",
            extra={"athlete_id": athlete_id, "execution_date": execution_date, "error": str(exc)},
        )


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


def _build_daily_coach(db: DatabaseManager, athlete_id: str = "owner"):
    """Compose a DailyCoach for one athlete, mirroring the titan/main.py composition root.

    Every collaborator is built with the constructor signature it actually has;
    the worker loops used to pass keyword arguments these constructors do not
    accept, so each morning cycle failed with TypeError before any work ran.
    """
    from titan.core.athlete import UniversalAthleteProfile
    from titan.features.nutrition_optimizer import NutritionOptimizer
    from titan.features.optimal_time_calculator import OptimalTimeCalculator
    from titan.features.weekly_planner import WeeklyPlanGenerator
    from titan.integrations.garmin_sync import GarminSync
    from titan.integrations.telegram_bot import TitanTelegramBot
    from titan.integrations.weather_api import WeatherAPI
    from titan.orchestration.daily_coach import DailyCoach
    from titan.orchestration.engine_registry import EngineRegistry
    from titan.science.acwr_engine import ACWREngine
    from titan.science.glycogen_model import GlycogenModel

    weather = WeatherAPI()
    engines = EngineRegistry.from_db(db=db, athlete_id=athlete_id)
    return DailyCoach(
        garmin_sync=GarminSync(),
        weather_api=weather,
        telegram_bot=TitanTelegramBot(db=db),
        hrv_engine=engines.hrv,
        tsb_engine=engines.tsb,
        readiness_engine=engines.readiness,
        optimal_time_calc=OptimalTimeCalculator(weather),
        nutrition_optimizer=NutritionOptimizer(GlycogenModel()),
        weekly_planner=WeeklyPlanGenerator(engines.hrv, engines.tsb, ACWREngine()),
        db=db,
        athlete_id=athlete_id,
        engines=engines,
        # Same profile source as the console (titan/main.py), so TRIMP uses one max HR (T5-117).
        athlete_max_hr=UniversalAthleteProfile.from_env().max_hr or 0,
    )


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

    if settings.TITAN_MULTI_ATHLETE == "1":
        _run_with_scheduler(db, _stop, heartbeat=heartbeat, interval_s=interval_s)
        return

    while True:
        _write_heartbeat(heartbeat)
        _run_backup(db)
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

    Due means at or after 07:00 UTC and not yet claimed today: the claim row in
    ``worker_routine_executions`` decides, so a restart never runs the routine a
    second time on the same day (ADR-0060 D1, INV-15). A failed claim is retried
    every ``interval_s`` until it succeeds or the stop event fires.
    """
    log = logging.getLogger("titan.worker.runner")
    while True:
        now = _utc_now()
        if now.hour < ROUTINE_HOUR_UTC:
            log.info("worker_routine_not_due", extra={"due_hour_utc": ROUTINE_HOUR_UTC})
            return False
        claimed = _claim_routine(db, "owner", now)
        if claimed is None:
            if _sleep_with_heartbeat(stop, interval_s, interval_s, heartbeat):
                return True
            continue
        if not claimed:
            log.info("worker_routine_already_ran", extra={"execution_date": now.date().isoformat()})
            return False
        _run_routine_supervised(db, heartbeat, interval_s, budget_s, execution_date=now.date().isoformat())
        return False


def _run_routine_supervised(
    db: DatabaseManager,
    heartbeat: Path,
    interval_s: float,
    budget_s: float,
    *,
    execution_date: str | None = None,
) -> None:
    """Run one morning routine in a watched thread (INV-23(1)).

    The heartbeat keeps beating while the routine runs within ``budget_s``. Past
    the budget it stops, with one CRITICAL event, so the healthcheck reports the
    hung routine. A routine is never abandoned: this waits for it to finish.
    When ``execution_date`` is given, the claim row of that date is marked
    complete once the routine returns.
    """
    log = logging.getLogger("titan.worker.runner")

    def _cycle() -> None:
        try:
            coach = _build_daily_coach(db)
            coach.run_morning_routine()
            log.info("morning_routine_complete")
            if execution_date is not None:
                _complete_routine(db, "owner", execution_date)
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
    _write_heartbeat(heartbeat)


def _run_with_scheduler(
    db: DatabaseManager,
    stop_event: threading.Event,
    *,
    heartbeat: Path | None = None,
    interval_s: float = 60.0,
) -> None:
    """Multi-athlete coaching loop via CoachingScheduler (ADR-0046 / P26-03).

    Activated when TITAN_MULTI_ATHLETE=1. Registers the owner athlete
    and any additional athletes from the athletes table, then runs the
    scheduler until the stop event fires.
    """
    from collections.abc import Callable

    from titan.orchestration.coaching_scheduler import CoachingScheduler

    log = logging.getLogger("titan.worker.scheduler")

    # Run interval: 60s poll; coaching fires once per athlete per day at or
    # after 07:00 UTC. The daily gate is the claim row in
    # worker_routine_executions (ADR-0060 D1), so it survives a restart.
    scheduler = CoachingScheduler(interval_seconds=60.0)

    def _make_athlete_callback(athlete_id: str) -> Callable[[], None]:
        def _callback() -> None:
            now = _utc_now()
            if now.hour < ROUTINE_HOUR_UTC:
                return
            # The claim is taken before execution so a mid-routine crash does
            # not trigger a retry storm; a failed claim retries next poll.
            if not _claim_routine(db, athlete_id, now):
                return
            try:
                coach = _build_daily_coach(db, athlete_id=athlete_id)
                coach.run_morning_routine()
                _complete_routine(db, athlete_id, now.date().isoformat())
            except Exception as exc:
                log.exception(
                    "scheduler_athlete_cycle_error",
                    extra={"athlete_id": athlete_id, "error": str(exc)},
                )
        return _callback

    scheduler.register_athlete("owner", _make_athlete_callback("owner"))

    scheduler.start()
    log.info("coaching_scheduler_started", extra={"athletes": list(scheduler._athlete_callbacks)})

    # Supervise until the stop event fires (SIGTERM / main() shutdown).
    _supervise_scheduler(scheduler, stop_event, heartbeat=heartbeat, interval_s=interval_s)
    scheduler.stop()
    log.info("coaching_scheduler_stopped")


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
    logging.basicConfig(level=logging.INFO)
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

"""titan.worker — background effect runner (ADR-0057).

Owns all write-heavy side effects: Garmin sync, Telegram poller,
morning routine scheduler. Enforces a single-instance advisory lock so
docker restart never spawns a duplicate.
"""

from __future__ import annotations

import datetime as _dt
import logging
import signal as _signal
import sys
import threading
from io import IOBase
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

from titan.config.settings import get_settings

logger = logging.getLogger(__name__)

LOCK_FILE = Path(get_settings().TITAN_DATA_DIR) / "worker.lock"

_shutdown = threading.Event()


def _handle_sigterm(signum, frame):  # noqa: ANN001
    log = logging.getLogger("titan.worker.signal")
    log.info("worker_shutdown_requested")
    _shutdown.set()


def acquire_worker_lock() -> IOBase | None:
    """Return an open file handle holding an exclusive lock, or None if already locked."""
    fh = open(LOCK_FILE, "w")  # noqa: SIM115
    try:
        import fcntl

        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except ImportError:
        # Windows fallback
        import msvcrt

        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            fh.close()
            return None
    except OSError:
        fh.close()
        return None
    return fh


def _run_backup(db: DatabaseManager) -> None:
    """Daily hot backup via DatabaseManager.backup_database() (keep=7 days)."""
    log = logging.getLogger("titan.worker.backup")
    backed_up = db.backup_database(keep=7)
    if backed_up:
        log.info("backup_complete", extra={"path": str(backed_up)})


def _seconds_until_next_run(hour: int = 7, minute: int = 0) -> float:
    """Return seconds until next HH:MM UTC. Always > 0."""
    now = _dt.datetime.now(_dt.UTC)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += _dt.timedelta(days=1)
    return (target - now).total_seconds()


def run_forever(db_path: str, shutdown_event: threading.Event | None = None) -> None:
    """ADR-0057 worker entrypoint. Runs DailyCoach morning routine aligned to 07:00 UTC."""
    from titan.core.database import DatabaseManager
    from titan.orchestration.daily_coach import DailyCoach

    _stop = shutdown_event if shutdown_event is not None else threading.Event()
    log = logging.getLogger("titan.worker.runner")
    p = Path(db_path)
    db = DatabaseManager(db_name=p.name, db_dir=p.parent)

    log.info("worker_started", extra={"db": db_path})

    while True:
        _run_backup(db)
        try:
            from titan.features.nutrition_optimizer import NutritionOptimizer
            from titan.features.optimal_time_calculator import OptimalTimeCalculator
            from titan.features.weekly_planner import WeeklyPlanGenerator
            from titan.integrations.garmin_sync import GarminSync
            from titan.integrations.telegram_bot import TitanTelegramBot
            from titan.integrations.weather_api import WeatherAPI
            from titan.orchestration.engine_registry import EngineRegistry

            athlete_max_hr = int(str(get_settings().ATHLETE_MAX_HR))
            garmin = GarminSync(
                athlete_max_hr=athlete_max_hr
            )
            weather = WeatherAPI()
            telegram = TitanTelegramBot(db=db)
            engines = EngineRegistry.from_db(db=db)
            optimal = OptimalTimeCalculator()
            nutrition = NutritionOptimizer(db=db)
            planner = WeeklyPlanGenerator(db=db)

            coach = DailyCoach(
                garmin_sync=garmin,
                weather_api=weather,
                telegram_bot=telegram,
                # B2c (Phase 24 / ADR-0058): pass complete registry so
                # DailyCoach.__init__ takes the pure-consumer path.
                # Individual hrv_engine/tsb_engine/readiness_engine params
                # are omitted — registry owns all 10 engine instances.
                engines=engines,
                optimal_time_calc=optimal,
                nutrition_optimizer=nutrition,
                weekly_planner=planner,
                db=db,
            )
            coach.run_morning_routine()
            log.info("morning_routine_complete")
        except Exception as exc:
            log.exception(
                "worker_cycle_error",
                extra={"error": str(exc)},
            )
            from titan.observability.metrics import get_metrics
            get_metrics().counter("worker_cycle_error")
        # Sleep until 07:00 UTC next day.
        # Timezone alignment is out of scope — worker uses UTC 07:00 throughout.
        wait_s = _seconds_until_next_run(7, 0)
        log.info("worker_sleeping", extra={"seconds": wait_s})
        if _stop.wait(timeout=wait_s):
            log.info("worker_graceful_exit")
            return


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

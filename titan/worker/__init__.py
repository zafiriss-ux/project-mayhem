"""titan.worker — background effect runner (ADR-0057).

Owns all write-heavy side effects: Garmin sync, Telegram poller,
morning routine scheduler. Enforces a single-instance advisory lock so
docker restart never spawns a duplicate.
"""

from __future__ import annotations

import logging
import os
import sys
from io import IOBase
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

logger = logging.getLogger(__name__)

LOCK_FILE = Path(os.environ.get("TITAN_DATA_DIR", "/data")) / "worker.lock"


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


def run_forever(db_path: str) -> None:
    """ADR-0057 worker entrypoint. Runs DailyCoach morning routine on 24h schedule."""
    import threading
    from pathlib import Path

    from titan.core.database import DatabaseManager
    from titan.orchestration.daily_coach import DailyCoach

    log = logging.getLogger("titan.worker.runner")
    p = Path(db_path)
    db = DatabaseManager(db_name=p.name, db_dir=p.parent)

    log.info("worker_started", extra={"db": db_path})

    while True:
        _run_backup(db)
        try:
            coach = DailyCoach(db=db)
            coach.run_morning_routine()
            log.info("morning_routine_complete")
        except Exception as exc:
            log.exception("worker_cycle_error", extra={"error": str(exc)})
        stop = threading.Event()
        stop.wait(timeout=86400)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    lock = acquire_worker_lock()
    if lock is None:
        logger.info("Worker already running — exiting")
        sys.exit(0)
    db_path = str(Path(os.environ.get("TITAN_DATA_DIR", "/data")) / "titan_core.db")
    try:
        run_forever(db_path)
    finally:
        lock.close()


if __name__ == "__main__":
    main()

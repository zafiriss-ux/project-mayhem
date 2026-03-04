import sqlite3
import threading
import time
from datetime import date, timedelta

from titan.core.database import DatabaseManager

THREAD_COUNT = 5
ITERATIONS_PER_THREAD = 20


def test_database_manager_thread_safety_under_mixed_read_write_load(tmp_path):
    db = DatabaseManager(db_name="thread_safety.db", db_dir=tmp_path)
    exceptions: list[Exception] = []
    exceptions_lock = threading.Lock()

    def _worker(thread_index: int) -> None:
        for iteration in range(ITERATIONS_PER_THREAD):
            current_date = date(2026, 1, 1) + timedelta(
                days=(thread_index * ITERATIONS_PER_THREAD) + iteration
            )
            try:
                db.save_daily_metric(
                    date=current_date.isoformat(),
                    hrv=40.0 + thread_index,
                    rhr=50 + thread_index,
                    sleep_hours=7.0,
                )
                db.get_training_load_history(days=7)
            except Exception as exc:  # noqa: BLE001
                with exceptions_lock:
                    exceptions.append(exc)

    threads = [threading.Thread(target=_worker, args=(idx,)) for idx in range(THREAD_COUNT)]

    start = time.perf_counter()
    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=5)

    duration = time.perf_counter() - start

    try:
        assert all(not thread.is_alive() for thread in threads), (
            "All threads must complete and join within 5 seconds. "
            f"Duration: {duration:.3f}s"
        )

        programming_errors = [
            exc for exc in exceptions if isinstance(exc, sqlite3.ProgrammingError)
        ]
        operational_errors = [
            exc for exc in exceptions if isinstance(exc, sqlite3.OperationalError)
        ]

        assert not programming_errors
        assert not operational_errors
        assert not exceptions
    finally:
        db.close()

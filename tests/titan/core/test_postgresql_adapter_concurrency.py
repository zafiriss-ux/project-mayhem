import threading
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from titan.core.persistence import PostgreSQLAdapter

THREAD_COUNT = 5
ITERATIONS_PER_THREAD = 20


def _build_postgres_adapter_test_engine(tmp_path) -> tuple[Engine, PostgreSQLAdapter]:
    db_path = tmp_path / "postgres_adapter_concurrency.sqlite"
    engine = create_engine(
        f"sqlite+pysqlite:///{db_path}",
        future=True,
        connect_args={"check_same_thread": False, "timeout": 5},
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS daily_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    athlete_id TEXT NOT NULL DEFAULT 'default',
                    date TEXT UNIQUE NOT NULL,
                    weight_kg REAL,
                    hrv_rmssd REAL,
                    resting_hr INTEGER,
                    sleep_hours REAL,
                    sleep_quality INTEGER,
                    soreness INTEGER,
                    fatigue_level INTEGER,
                    mood INTEGER,
                    notes TEXT,
                    quality_flag TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS training_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    athlete_id TEXT NOT NULL DEFAULT 'default',
                    date TEXT NOT NULL,
                    session_type TEXT NOT NULL,
                    distance_km REAL NOT NULL,
                    duration_sec INTEGER NOT NULL,
                    avg_hr INTEGER,
                    max_hr INTEGER,
                    rpe INTEGER,
                    training_load REAL,
                    shoe_id INTEGER,
                    surface TEXT,
                    temperature_c REAL,
                    zone_distribution TEXT,
                    notes TEXT,
                    garmin_activity_id TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

    adapter = PostgreSQLAdapter(dsn="postgres://unused", engine=engine)
    return engine, adapter


def test_postgres_adapter_thread_safety_under_mixed_read_write_load(tmp_path) -> None:
    _engine, adapter = _build_postgres_adapter_test_engine(tmp_path)
    exceptions: list[Exception] = []
    exceptions_lock = threading.Lock()

    def _worker(thread_index: int) -> None:
        for iteration in range(ITERATIONS_PER_THREAD):
            current_date = datetime(2026, 1, 1, tzinfo=UTC).date() + timedelta(
                days=(thread_index * ITERATIONS_PER_THREAD) + iteration
            )
            date_iso = current_date.isoformat()
            try:
                adapter.save_daily_metric(date_iso, hrv=40.0 + thread_index, rhr=50 + thread_index)
                adapter.save_session(
                    date_iso,
                    "EASY",
                    distance_km=8.0,
                    duration_sec=2400,
                    rpe=4,
                    garmin_activity_id=f"activity-{thread_index}-{iteration}",
                )
                adapter.get_training_load_history(days=7)
                adapter.get_baseline_rhr(days=7)
            except Exception as exc:  # noqa: BLE001
                with exceptions_lock:
                    exceptions.append(exc)

    threads = [threading.Thread(target=_worker, args=(idx,)) for idx in range(THREAD_COUNT)]

    start = time.perf_counter()
    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join(timeout=8)

    duration = time.perf_counter() - start

    try:
        assert all(not thread.is_alive() for thread in threads), (
            "All threads must complete and join within 8 seconds. "
            f"Duration: {duration:.3f}s"
        )
        assert not exceptions

        sessions = adapter.get_training_load_history(days=3650)
        assert len(sessions) == THREAD_COUNT * ITERATIONS_PER_THREAD
    finally:
        adapter.close()


def test_postgres_adapter_concurrent_upserts_on_same_date_are_stable(tmp_path) -> None:
    _engine, adapter = _build_postgres_adapter_test_engine(tmp_path)
    exceptions: list[Exception] = []
    exceptions_lock = threading.Lock()
    same_date = "2026-04-01"

    def _worker(thread_index: int) -> None:
        try:
            adapter.save_daily_metric(same_date, hrv=45.0 + thread_index, rhr=55 + thread_index)
            adapter.get_baseline_rhr(days=7)
        except Exception as exc:  # noqa: BLE001
            with exceptions_lock:
                exceptions.append(exc)

    threads = [threading.Thread(target=_worker, args=(idx,)) for idx in range(THREAD_COUNT)]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=8)

    try:
        assert all(not thread.is_alive() for thread in threads)
        assert not exceptions

        hrv_history = adapter.get_hrv_history(days=7)
        assert len(hrv_history) == 1
        assert hrv_history[0][0] == same_date
    finally:
        adapter.close()

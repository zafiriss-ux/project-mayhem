import queue
import threading
from unittest.mock import MagicMock, patch

import pytest

from titan.core.database import DatabaseManager


def _days_ago(n: int) -> str:
    """A date inside the "last N days" window of the history reads (F5, D-072)."""
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(days=n)).strftime("%Y-%m-%d")


def _assert_write_method_uses_locked_guard(db, write_call):
    events = []
    state = {"in_lock": False}

    class TrackingLock:
        def __enter__(self):
            state["in_lock"] = True
            events.append("lock_enter")
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append("lock_exit")
            state["in_lock"] = False
            return False

    cursor = MagicMock()
    cursor.rowcount = 1
    conn = MagicMock()

    def _cursor_side_effect():
        assert state["in_lock"]
        events.append("cursor")
        return cursor

    conn.cursor.side_effect = _cursor_side_effect
    db.conn = conn
    db._lock = TrackingLock()

    def _ensure_side_effect():
        assert state["in_lock"]
        events.append("ensure")

    with patch.object(db, "_ensure_open_locked", side_effect=_ensure_side_effect):
        write_call()

    assert events.index("ensure") < events.index("cursor")
    conn.commit.assert_called_once()


@pytest.mark.integration
def test_get_active_shoes_returns_rows_when_database_open(tmp_path):
    db = DatabaseManager(db_name="happy_path.db", db_dir=tmp_path)

    shoe_id = db.add_shoe("Pegasus", "DAILY", 800)

    rows = db.get_active_shoes()

    assert rows
    assert rows[0][0] == shoe_id

    db.close()


@pytest.mark.integration
def test_get_active_shoes_raises_controlled_error_when_close_wins_lock_race(tmp_path):
    db = DatabaseManager(db_name="close_race.db", db_dir=tmp_path)

    # Use a re-entrant lock in test so main thread can hold the lock, call close(),
    # then release and let the reader proceed into the fast-fail closed check.
    db._lock = threading.RLock()

    entered_read = threading.Event()
    read_result: queue.Queue[Exception | list[tuple]] = queue.Queue()

    def _reader() -> None:
        entered_read.set()
        try:
            read_result.put(db.get_active_shoes())
        except Exception as exc:  # noqa: BLE001
            read_result.put(exc)

    with db._lock:
        reader = threading.Thread(target=_reader)
        reader.start()
        entered_read.wait(timeout=1)
        db.close()

    reader.join(timeout=2)
    assert not reader.is_alive()

    result = read_result.get(timeout=1)
    assert isinstance(result, RuntimeError)
    assert "closed" in str(result).lower()


@pytest.mark.integration
@pytest.mark.parametrize(
    "read_method",
    [
        lambda db: db.get_training_load_history(),
        lambda db: db.get_active_shoes(),
        lambda db: db.check_shoe_availability(1),
        lambda db: db.get_pr(5.0),
        lambda db: db.get_hrr_history(),
        lambda db: db.get_cs_performances(),
        lambda db: db.get_override_ratio(),
        lambda db: db.get_model_calibration_metadata("hrv_engine"),
        lambda db: db.get_governance_decisions(),
    ],
)
def test_read_methods_fail_fast_after_close(tmp_path, read_method):
    db = DatabaseManager(db_name="closed_reads.db", db_dir=tmp_path)
    db.close()

    with pytest.raises(RuntimeError, match="closed"):
        read_method(db)


@pytest.mark.integration
def test_save_daily_metric_cursor_inside_lock(tmp_path):
    db = DatabaseManager(db_name="save_daily_metric_guard.db", db_dir=tmp_path)

    _assert_write_method_uses_locked_guard(
        db,
        lambda: db.save_daily_metric(date="2026-03-05", weight=70.5),
    )


@pytest.mark.integration
def test_save_session_cursor_inside_lock(tmp_path):
    db = DatabaseManager(db_name="save_session_guard.db", db_dir=tmp_path)

    _assert_write_method_uses_locked_guard(
        db,
        lambda: db.save_session(
            date="2026-03-05",
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            rpe=4,
        ),
    )


@pytest.mark.integration
def test_save_session_ignores_duplicate_garmin_activity_id(tmp_path):
    db = DatabaseManager(db_name="garmin_duplicate_ignore.db", db_dir=tmp_path)

    try:
        db.save_session(
            date="2026-03-05",
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            rpe=5,
            garmin_activity_id="garmin-123",
        )
        db.save_session(
            date="2026-03-05",
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            rpe=5,
            garmin_activity_id="garmin-123",
        )

        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM training_log")
        assert cursor.fetchone()[0] == 1
    finally:
        db.close()


@pytest.mark.integration
def test_save_session_allows_multiple_manual_rows_with_null_garmin_activity_id(tmp_path):
    db = DatabaseManager(db_name="manual_null_garmin_id.db", db_dir=tmp_path)

    try:
        db.save_session(
            date="2026-03-05",
            session_type="EASY",
            distance_km=5.0,
            duration_sec=1800,
            rpe=3,
            garmin_activity_id=None,
        )
        db.save_session(
            date="2026-03-06",
            session_type="RECOVERY",
            distance_km=4.0,
            duration_sec=1600,
            rpe=2,
            garmin_activity_id=None,
        )

        cursor = db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM training_log")
        assert cursor.fetchone()[0] == 2
    finally:
        db.close()


@pytest.mark.integration
def test_save_hrr_cursor_inside_lock(tmp_path):
    db = DatabaseManager(db_name="save_hrr_guard.db", db_dir=tmp_path)

    _assert_write_method_uses_locked_guard(
        db,
        lambda: db.save_hrr(date="2026-03-05", hrr_60=30, hrr_120=45),
    )


@pytest.mark.integration
def test_update_shoe_mileage_cursor_inside_lock(tmp_path):
    db = DatabaseManager(db_name="update_shoe_guard.db", db_dir=tmp_path)

    _assert_write_method_uses_locked_guard(
        db,
        lambda: db.update_shoe_mileage(shoe_id=1, distance_km=12.5, date="2026-03-05"),
    )


@pytest.mark.integration
def test_add_shoe_cursor_inside_lock(tmp_path):
    db = DatabaseManager(db_name="add_shoe_guard.db", db_dir=tmp_path)

    _assert_write_method_uses_locked_guard(
        db,
        lambda: db.add_shoe(name="Pegasus", shoe_type="DAILY", max_km=800),
    )


@pytest.mark.integration
def test_save_personal_best_cursor_inside_lock(tmp_path):
    db = DatabaseManager(db_name="save_pb_guard.db", db_dir=tmp_path)

    _assert_write_method_uses_locked_guard(
        db,
        lambda: db.save_personal_best(
            distance_km=5.0,
            time_sec=1200,
            date="2026-03-05",
            race_name="Local 5K",
        ),
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("name", "write_call"),
    [
        (
            "update_glycogen_debt",
            lambda db: db.update_glycogen_debt(date="2026-03-05", debt_score=4.2),
        ),
        (
            "log_cs_performance",
            lambda db: db.log_cs_performance(
                date="2026-03-05",
                distance_m=5000.0,
                time_sec=1200.0,
                surface="ROAD",
                wind_adjusted=False,
            ),
        ),
        (
            "log_override",
            lambda db: db.log_override(
                date="2026-03-05",
                prescribed="REST",
                actual="EASY",
                reason="Felt good",
                athlete_id="owner",
            ),
        ),
        (
            "save_governance_decision",
            lambda db: db.save_governance_decision({
                "date": "2026-03-05",
                "session_planned": "EASY",
                "session_post_governance": "REST",
            }),
        ),
        (
            "update_governance_outcome",
            lambda db: db.update_governance_outcome(
                date="2026-03-05",
                rpe=5,
                completed=True,
                actual_session_type="EASY",
                notes="ok",
            ),
        ),
        (
            "upsert_model_calibration_metadata",
            lambda db: db.upsert_model_calibration_metadata(
                model_name="hrv_engine",
                calibrated_at="2026-03-09T10:00:00+00:00",
                baseline_hrv_ms=51.2,
            ),
        ),
    ],
    ids=lambda case: case,
)
def test_governance_and_science_write_methods_cursor_inside_lock(tmp_path, name, write_call):
    db = DatabaseManager(db_name=f"{name}_guard.db", db_dir=tmp_path)
    _assert_write_method_uses_locked_guard(db, lambda: write_call(db))


@pytest.mark.integration
def test_memory_db_with_db_dir_does_not_raise(tmp_path):
    """DatabaseManager(db_name=':memory:', db_dir=<path>) must not construct an invalid path."""
    db = DatabaseManager(db_name=":memory:", db_dir=tmp_path)
    try:
        # Confirm functional: can save and retrieve a metric
        db.save_daily_metric(date="2026-03-21", weight=70.0)
        with db._lock:
            db._ensure_open_locked()
            cursor = db.conn.cursor()
            cursor.execute("SELECT weight_kg FROM daily_metrics WHERE date = ?", ("2026-03-21",))
            assert cursor.fetchone()[0] == 70.0
    finally:
        db.close()


@pytest.mark.integration
def test_write_after_close_raises(tmp_path):
    db = DatabaseManager(db_name=":memory:", db_dir=tmp_path)
    db.close()

    with pytest.raises(RuntimeError, match="closed"):
        db.save_daily_metric(date="2026-03-05", weight=70.0)
    with pytest.raises(RuntimeError, match="closed"):
        db.upsert_model_calibration_metadata(
            model_name="hrv_engine",
            calibrated_at="2026-03-09T10:00:00+00:00",
            baseline_hrv_ms=52.0,
        )


@pytest.mark.integration
@pytest.mark.parametrize(
    "write_call",
    [
        lambda db: db.update_glycogen_debt(date="2026-03-05", debt_score=3.5),
        lambda db: db.log_cs_performance(date="2026-03-05", distance_m=3000.0, time_sec=700.0),
        lambda db: db.log_override(date="2026-03-05", prescribed="EASY", actual="REST", athlete_id="owner"),
        lambda db: db.save_governance_decision({"date": "2026-03-05"}),
        lambda db: db.update_governance_outcome(date="2026-03-05", rpe=4),
        lambda db: db.upsert_model_calibration_metadata(
            model_name="hrv_engine",
            calibrated_at="2026-03-09T10:00:00+00:00",
            baseline_hrv_ms=51.2,
        ),
    ],
)
def test_in_scope_write_methods_fail_fast_after_close(tmp_path, write_call):
    db = DatabaseManager(db_name="closed_writes_scope.db", db_dir=tmp_path)
    db.close()

    with pytest.raises(RuntimeError, match="closed"):
        write_call(db)


@pytest.mark.integration
@pytest.mark.parametrize(
    "write_call",
    [
        lambda db: db.update_glycogen_debt(date="2026-03-05", debt_score=3.5),
        lambda db: db.log_cs_performance(date="2026-03-05", distance_m=3000.0, time_sec=700.0),
        lambda db: db.log_override(date="2026-03-05", prescribed="EASY", actual="REST", athlete_id="owner"),
        lambda db: db.save_governance_decision({"date": "2026-03-05"}),
        lambda db: db.update_governance_outcome(date="2026-03-05", rpe=4),
        lambda db: db.upsert_model_calibration_metadata(
            model_name="hrv_engine",
            calibrated_at="2026-03-09T10:00:00+00:00",
            baseline_hrv_ms=51.2,
        ),
    ],
)
def test_in_scope_write_methods_no_cursor_on_close_race(tmp_path, write_call):
    db = DatabaseManager(db_name="closed_write_race_scope.db", db_dir=tmp_path)
    db._lock = threading.RLock()

    conn = MagicMock()
    conn.cursor.side_effect = AssertionError("cursor() must not be called on closed DB")
    db.conn = conn

    entered_write = threading.Event()
    write_result: queue.Queue[Exception | None] = queue.Queue()

    def _writer() -> None:
        entered_write.set()
        try:
            write_call(db)
            write_result.put(None)
        except Exception as exc:  # noqa: BLE001
            write_result.put(exc)

    with db._lock:
        writer = threading.Thread(target=_writer)
        writer.start()
        entered_write.wait(timeout=1)
        db.close()

    writer.join(timeout=2)
    assert not writer.is_alive()

    result = write_result.get(timeout=1)
    assert isinstance(result, RuntimeError)
    assert "closed" in str(result).lower()
    conn.cursor.assert_not_called()


@pytest.mark.integration
def test_concurrent_writes_no_race(tmp_path):
    db = DatabaseManager(db_name="concurrent_writes.db", db_dir=tmp_path)
    errors: queue.Queue[Exception] = queue.Queue()

    def _writer(weight: float) -> None:
        try:
            db.save_daily_metric(date="2026-03-05", weight=weight)
        except Exception as exc:  # noqa: BLE001
            errors.put(exc)

    t1 = threading.Thread(target=_writer, args=(70.0,))
    t2 = threading.Thread(target=_writer, args=(71.0,))
    t1.start()
    t2.start()
    t1.join(timeout=2)
    t2.join(timeout=2)

    assert errors.empty()

    with db._lock:
        db._ensure_open_locked()
        cursor = db.conn.cursor()
        cursor.execute("SELECT weight_kg FROM daily_metrics WHERE date = ?", ("2026-03-05",))
        row = cursor.fetchone()

    assert row is not None
    assert row[0] in {70.0, 71.0}

    db.close()


class _CommitSpyConnection:
    def __init__(self, conn):
        self._conn = conn
        self.commit_calls = 0

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def commit(self):
        self.commit_calls += 1
        return self._conn.commit()


@pytest.mark.integration
def test_standalone_write_methods_commit_and_persist(tmp_path):
    db = DatabaseManager(db_name="standalone_commit_methods.db", db_dir=tmp_path)
    db.conn = _CommitSpyConnection(db.conn)
    day = _days_ago(1)

    db.save_daily_metric(date=day, weight=70.2, hrv=30.0, rhr=50)
    assert db.conn.commit_calls == 1

    db.save_session(
        date=day,
        session_type="EASY",
        distance_km=8.0,
        duration_sec=2400,
        rpe=4,
    )
    assert db.conn.commit_calls == 2

    db.save_hrr(date=day, hrr_60=30, hrr_120=45)
    assert db.conn.commit_calls == 3

    shoe_id = db.add_shoe(name="Pegasus 40", shoe_type="DAILY", max_km=700)
    assert db.conn.commit_calls == 4

    db.update_shoe_mileage(shoe_id=shoe_id, distance_km=10.5, date=day)
    assert db.conn.commit_calls == 5

    db.save_personal_best(distance_km=5.0, time_sec=1200, date=day, race_name="City 5K")
    assert db.conn.commit_calls == 6

    db.upsert_model_calibration_metadata(
        model_name="hrv_engine",
        calibrated_at="2026-03-09T10:00:00+00:00",
        baseline_hrv_ms=55.0,
        baseline_vo2=56.0,
    )
    assert db.conn.commit_calls == 7

    cur = db.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM daily_metrics WHERE date = ?", (day,))
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT COUNT(*) FROM training_log WHERE date = ?", (day,))
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT hrr_60, hrr_120 FROM daily_metrics WHERE date = ?", (day,))
    assert cur.fetchone() == (30, 45)
    cur.execute("SELECT total_km FROM gear_usage WHERE id = ?", (shoe_id,))
    assert float(cur.fetchone()[0]) == 10.5
    cur.execute("SELECT COUNT(*) FROM personal_bests WHERE distance_km = ?", (5.0,))
    assert cur.fetchone()[0] == 1

    metadata = db.get_model_calibration_metadata("hrv_engine")
    assert metadata is not None
    assert metadata["baseline_hrv_ms"] == 55.0
    assert metadata["baseline_vo2"] == 56.0
    assert db.get_recent_hrv_mean(days=30) == 30.0

    db.close()


@pytest.mark.integration
def test_transaction_defers_commit_until_exit_and_nested_calls_single_commit(tmp_path):
    db = DatabaseManager(db_name="transaction_defer_commit.db", db_dir=tmp_path)
    db.conn = _CommitSpyConnection(db.conn)

    with db.transaction():
        db.save_daily_metric(date="2026-03-05", weight=71.0)
        db.save_session(
            date="2026-03-05",
            session_type="EASY",
            distance_km=5.0,
            duration_sec=1800,
            rpe=3,
        )
        with db.transaction():
            db.save_daily_metric(date="2026-03-06", weight=71.1)
        assert db.conn.commit_calls == 0

    assert db.conn.commit_calls == 1

    cur = db.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM daily_metrics WHERE date IN (?, ?)", ("2026-03-05", "2026-03-06"))
    assert cur.fetchone()[0] == 2
    cur.execute("SELECT COUNT(*) FROM training_log WHERE date = ?", ("2026-03-05",))
    assert cur.fetchone()[0] == 1

    db.close()


@pytest.mark.integration
def test_transaction_rollback_restores_state(tmp_path):
    db = DatabaseManager(db_name="transaction_rollback.db", db_dir=tmp_path)

    with pytest.raises(RuntimeError, match="force_rollback"), db.transaction():
        db.save_daily_metric(date="2026-03-05", weight=69.0)
        db.save_session(
            date="2026-03-05",
            session_type="EASY",
            distance_km=6.0,
            duration_sec=2100,
            rpe=4,
        )
        raise RuntimeError("force_rollback")

    cur = db.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM daily_metrics WHERE date = ?", ("2026-03-05",))
    assert cur.fetchone()[0] == 0
    cur.execute("SELECT COUNT(*) FROM training_log WHERE date = ?", ("2026-03-05",))
    assert cur.fetchone()[0] == 0

    db.close()


@pytest.mark.integration
def test_record_override_signal_persists_row(tmp_path):
    db = DatabaseManager(db_name="override_signal.db", db_dir=tmp_path)

    db.record_override_signal(
        decision_id="decision-1",
        athlete_id="ATH_1",
        override_source="telegram_bot",
        override_reason="Athlete felt stable",
        created_at="2026-03-07T09:00:00+00:00",
    )

    with db._lock:
        db._ensure_open_locked()
        row = db.conn.execute(
            """SELECT decision_id, athlete_id, override_source, override_reason
                   FROM override_signals"""
        ).fetchone()

    assert row == ("decision-1", "ATH_1", "telegram_bot", "Athlete felt stable")


@pytest.mark.integration
def test_record_override_signal_fails_fast_after_close(tmp_path):
    db = DatabaseManager(db_name="override_signal_closed.db", db_dir=tmp_path)
    db.close()

    with pytest.raises(RuntimeError, match="closed"):
        db.record_override_signal(
            decision_id="decision-1",
            athlete_id="ATH_1",
            override_source="telegram_bot",
            override_reason="x",
            created_at="2026-03-07T09:00:00+00:00",
        )


class _FakePostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query, params=None):
        import re

        sql = (
            query.replace("%s", "?")
            .replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
            .replace("DOUBLE PRECISION", "REAL")
        )
        # Strip PostgreSQL ON CONFLICT (col) DO NOTHING — SQLite uses OR IGNORE at
        # the INSERT level; the fake in-memory schema has no partial unique index.
        sql = re.sub(r"\s*ON CONFLICT\s*\(\w+\)\s*DO NOTHING", "", sql)
        if params is None:
            self._cursor.execute(sql)
        else:
            self._cursor.execute(sql, params)
        return self

    def fetchall(self):
        return self._cursor.fetchall()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self._cursor.close()


class _FakePostgresConnection:
    def __init__(self):
        import sqlite3

        self._conn = sqlite3.connect(":memory:")
        self.autocommit = False

    def cursor(self):
        return _FakePostgresCursor(self._conn.cursor())

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


class _FakePsycopg2:
    @staticmethod
    def connect(_dsn):
        return _FakePostgresConnection()


def _seed_training_rows(db):
    from datetime import UTC, datetime, timedelta

    start = datetime.now(UTC).date() - timedelta(days=2)
    loads = [40, 80, 60]
    for idx, load in enumerate(loads):
        db.save_session(
            date=(start + timedelta(days=idx)).isoformat(),
            session_type="EASY",
            distance_km=10.0,
            duration_sec=600,
            avg_hr=140,
            max_hr=160,
            rpe=int(load / 10),
            shoe_id=None,
            surface="ROAD",
            temperature_c=20.0,
            notes="seed",
        )


def _seed_governance_row(db):
    from datetime import UTC, datetime

    db.save_governance_decision(
        {
            "date": datetime.now(UTC).date().isoformat(),
            "session_planned": "THRESHOLD",
            "session_post_governance": "EASY",
            "locks_applied": ["RECOVERY_LOCK"],
            "governance_clean": False,
            "phase": "BASE",
            "vlg_color": "YELLOW",
            "apl_priority_vector": {"intensity": 0.2},
            "lock_thresholds_active": {"tsb": -10.0},
            "acwr": 1.1,
            "tsb_value": -8.2,
            "readiness_score": 68.5,
            "glycogen_debt": 14.0,
            "afi_value": 0.4,
            "algorithm_version_snapshot": {"governance": "5.8.0"},
        }
    )


@pytest.mark.integration
def test_get_database_manager_defaults_to_sqlite(tmp_path):
    from titan.core.database import get_database_manager

    db = get_database_manager(db_name="persist_sqlite.db", db_dir=tmp_path)

    assert isinstance(db, DatabaseManager)
    db.close()


@pytest.mark.integration
def test_get_database_manager_postgres_requires_dsn():
    # B3 (Opus 2026-05-22): postgres backend disabled until ADR-0044 parity
    from titan.core.database import get_database_manager

    with pytest.raises(NotImplementedError, match="ADR-0044"):
        get_database_manager(backend="postgres", postgres_dsn=None)


@pytest.mark.integration
def test_get_database_manager_respects_backend_environment(monkeypatch, tmp_path):
    # B3 (Opus 2026-05-22): TITAN_DB_BACKEND=postgres now raises NotImplementedError
    from titan.core.database import get_database_manager

    monkeypatch.setenv("TITAN_DB_BACKEND", "postgres")

    with pytest.raises(NotImplementedError, match="ADR-0044"):
        get_database_manager(db_name="unused.db", db_dir=tmp_path)


@pytest.mark.integration
def test_postgres_backend_raises():
    # TR-13 (Opus 2026-05-24): postgres adapter explicitly unmaintained until ADR-0044 parity
    from titan.core.database import get_database_manager

    with pytest.raises(NotImplementedError):
        get_database_manager(backend="postgres")


@pytest.mark.integration
def test_postgres_backend_matches_sqlite_ctl_atl_and_history(tmp_path, monkeypatch):
    from titan.core import database as db_module

    monkeypatch.setattr(db_module, "psycopg2", _FakePsycopg2())

    sqlite_db = DatabaseManager(db_name="sqlite_ref.db", db_dir=tmp_path)
    postgres_db = db_module.PostgreSQLDatabaseManager(dsn="postgres://fake")

    _seed_training_rows(sqlite_db)
    _seed_training_rows(postgres_db)

    assert postgres_db.get_training_load_history() == sqlite_db.get_training_load_history()
    assert postgres_db.get_ctl_atl_tsb() == sqlite_db.get_ctl_atl_tsb()

    sqlite_db.close()
    postgres_db.close()


@pytest.mark.integration
def test_postgres_backend_matches_sqlite_governance_persistence(tmp_path, monkeypatch):
    from titan.core import database as db_module

    monkeypatch.setattr(db_module, "psycopg2", _FakePsycopg2())

    sqlite_db = DatabaseManager(db_name="sqlite_gov.db", db_dir=tmp_path)
    postgres_db = db_module.PostgreSQLDatabaseManager(dsn="postgres://fake")

    _seed_governance_row(sqlite_db)
    _seed_governance_row(postgres_db)

    sqlite_row = sqlite_db.get_governance_decisions(limit=1)[0]
    postgres_row = postgres_db.get_governance_decisions(limit=1)[0]

    assert postgres_row["session_post_governance"] == sqlite_row["session_post_governance"]
    assert postgres_row["locks_applied"] == sqlite_row["locks_applied"]
    assert postgres_row["lock_thresholds_active"] == sqlite_row["lock_thresholds_active"]
    assert postgres_row["algorithm_version_snapshot"] == sqlite_row["algorithm_version_snapshot"]

    sqlite_db.close()
    postgres_db.close()


@pytest.mark.integration
def test_save_session_direct_training_load_overrides_rpe_calculation(tmp_path):
    """save_session(training_load=N) stores N directly, bypassing RPE computation."""
    db = DatabaseManager(db_name="direct_tl.db", db_dir=tmp_path)
    try:
        db.save_session(
            date="2026-03-21",
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            rpe=None,
            training_load=120,
        )
        cursor = db.conn.cursor()
        cursor.execute("SELECT training_load FROM training_log WHERE date = ?", ("2026-03-21",))
        assert cursor.fetchone()[0] == 120
    finally:
        db.close()


@pytest.mark.integration
def test_save_session_rpe_used_when_training_load_not_provided(tmp_path):
    """When training_load is not passed, sRPE formula is used as before."""
    db = DatabaseManager(db_name="sRPE_tl.db", db_dir=tmp_path)
    try:
        db.save_session(
            date="2026-03-21",
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,  # 60 min
            rpe=5,
        )
        cursor = db.conn.cursor()
        cursor.execute("SELECT training_load FROM training_log WHERE date = ?", ("2026-03-21",))
        assert cursor.fetchone()[0] == 5 * 60  # rpe × minutes
    finally:
        db.close()


# ---------------------------------------------------------------------------
# T5-71 — HD-08: WARNING event when rowcount=0 in save_hrr / update_glycogen_debt
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_save_hrr_emits_warning_when_no_row_updated(tmp_path, caplog):
    """save_hrr() must emit a WARNING structured event when the UPDATE matches 0 rows."""
    import json
    import logging

    db = DatabaseManager(db_name="hrr_warn.db", db_dir=tmp_path)
    try:
        with caplog.at_level(logging.WARNING, logger="titan.core.database"):
            # No daily_metrics row for this date — rowcount will be 0
            db.save_hrr("2026-04-04", hrr_60=28, hrr_120=35)

        warning_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_msgs, "Expected at least one WARNING log from save_hrr"
        payload = json.loads(warning_msgs[0])
        assert payload["action"] == "save_hrr_no_row_updated"
        assert payload["severity"] == "warning"
        assert payload["date"] == "2026-04-04"
    finally:
        db.close()


@pytest.mark.integration
def test_save_hrr_no_warning_when_row_updated(tmp_path, caplog):
    """save_hrr() must NOT emit a WARNING when the UPDATE matches an existing row."""
    import logging

    db = DatabaseManager(db_name="hrr_ok.db", db_dir=tmp_path)
    try:
        # Insert a daily_metrics row first so the UPDATE will match
        db.save_daily_metric(
            date="2026-04-04",
            rhr=55,
            hrv=45.0,
            sleep_quality=80,
            sleep_hours=7.5,
            weight=70.0,
        )
        with caplog.at_level(logging.WARNING, logger="titan.core.database"):
            db.save_hrr("2026-04-04", hrr_60=28, hrr_120=35)

        warning_msgs = [
            r.getMessage() for r in caplog.records
            if r.levelno == logging.WARNING and "save_hrr_no_row_updated" in r.getMessage()
        ]
        assert not warning_msgs, "save_hrr must NOT warn when a row is updated"
    finally:
        db.close()


@pytest.mark.integration
def test_update_glycogen_debt_emits_warning_when_no_row_updated(tmp_path, caplog):
    """update_glycogen_debt() must emit a WARNING structured event when the UPDATE matches 0 rows."""
    import json
    import logging

    db = DatabaseManager(db_name="glyco_warn.db", db_dir=tmp_path)
    try:
        with caplog.at_level(logging.WARNING, logger="titan.core.database"):
            # No daily_metrics row for this date — rowcount will be 0
            db.update_glycogen_debt("2026-04-04", debt_score=3.5)

        warning_msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
        assert warning_msgs, "Expected at least one WARNING log from update_glycogen_debt"
        payload = json.loads(warning_msgs[0])
        assert payload["action"] == "update_glycogen_debt_no_row_updated"
        assert payload["severity"] == "warning"
        assert payload["date"] == "2026-04-04"
    finally:
        db.close()


@pytest.mark.integration
def test_update_glycogen_debt_no_warning_when_row_updated(tmp_path, caplog):
    """update_glycogen_debt() must NOT emit a WARNING when the UPDATE matches an existing row."""
    import logging

    db = DatabaseManager(db_name="glyco_ok.db", db_dir=tmp_path)
    try:
        db.save_daily_metric(
            date="2026-04-04",
            rhr=55,
            hrv=45.0,
            sleep_quality=80,
            sleep_hours=7.5,
            weight=70.0,
        )
        with caplog.at_level(logging.WARNING, logger="titan.core.database"):
            db.update_glycogen_debt("2026-04-04", debt_score=3.5)

        warning_msgs = [
            r.getMessage() for r in caplog.records
            if r.levelno == logging.WARNING and "update_glycogen_debt_no_row_updated" in r.getMessage()
        ]
        assert not warning_msgs, "update_glycogen_debt must NOT warn when a row is updated"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# T5-74 — governance_outcomes athlete_id schema + INSERT
# ---------------------------------------------------------------------------

@pytest.mark.integration
def test_governance_outcomes_create_table_has_athlete_id_column(tmp_path):
    """governance_outcomes CREATE TABLE must include athlete_id (Fix A)."""
    db = DatabaseManager(db_name="gov_schema.db", db_dir=tmp_path)
    try:
        cursor = db.conn.cursor()
        columns = {row[1] for row in cursor.execute("PRAGMA table_info(governance_outcomes)").fetchall()}
        assert "athlete_id" in columns, "governance_outcomes must have athlete_id column"
    finally:
        db.close()


@pytest.mark.integration
def test_schema_version_is_11():
    """SCHEMA_VERSION must be 20 after biological_sex/menstrual_tracking migration."""
    from titan.core.database import SCHEMA_VERSION
    assert SCHEMA_VERSION == 31


@pytest.mark.integration
def test_save_governance_decision_persists_athlete_profile_id(tmp_path):
    """save_governance_decision() must write athlete_profile_id to athlete_id column (Fix B)."""
    db = DatabaseManager(db_name="gov_athlete_id.db", db_dir=tmp_path)
    try:
        db.save_governance_decision({
            "date": "2026-04-10",
            "session_planned": "EASY",
            "session_post_governance": "EASY",
            "athlete_profile_id": "ATH_42",
        })
        cursor = db.conn.cursor()
        row = cursor.execute(
            "SELECT athlete_id FROM governance_outcomes WHERE date = ?", ("2026-04-10",)
        ).fetchone()
        assert row is not None
        assert row[0] == "ATH_42"
    finally:
        db.close()


@pytest.mark.integration
def test_save_governance_decision_defaults_athlete_id_when_missing(tmp_path):
    """save_governance_decision() must default athlete_id to 'owner' when key absent (v13)."""
    db = DatabaseManager(db_name="gov_default_athlete.db", db_dir=tmp_path)
    try:
        db.save_governance_decision({
            "date": "2026-04-10",
            "session_planned": "REST",
            "session_post_governance": "REST",
        })
        cursor = db.conn.cursor()
        row = cursor.execute(
            "SELECT athlete_id FROM governance_outcomes WHERE date = ?", ("2026-04-10",)
        ).fetchone()
        assert row is not None
        assert row[0] == "owner"
    finally:
        db.close()


@pytest.mark.integration
def test_v11_migration_adds_athlete_id_to_existing_governance_outcomes(tmp_path):
    """v11 migration must add athlete_id to governance_outcomes in pre-existing databases."""
    import sqlite3

    db_path = tmp_path / "pre_v11.db"
    # Create a governance_outcomes table without athlete_id (simulates a pre-v11 database).
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE governance_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                session_planned TEXT NOT NULL,
                session_post_governance TEXT NOT NULL,
                locks_applied_json TEXT NOT NULL,
                governance_clean INTEGER NOT NULL,
                phase TEXT NOT NULL,
                vlg_color TEXT NOT NULL,
                apl_priority_vector_json TEXT NOT NULL,
                lock_thresholds_active_json TEXT NOT NULL,
                acwr REAL NOT NULL,
                tsb_value REAL NOT NULL,
                readiness_score REAL NOT NULL,
                glycogen_debt REAL NOT NULL,
                afi_value REAL
            )
        """)
        conn.execute("PRAGMA user_version = 10")

    # Open via DatabaseManager — v11 migration should add athlete_id.
    db = DatabaseManager(db_name=db_path.name, db_dir=tmp_path)
    try:
        cursor = db.conn.cursor()
        columns = {row[1] for row in cursor.execute("PRAGMA table_info(governance_outcomes)").fetchall()}
        assert "athlete_id" in columns, "v11 migration must add athlete_id to governance_outcomes"
        version = cursor.execute("PRAGMA user_version").fetchone()[0]
        assert version == 31  # SCHEMA_VERSION bumped to 31 by the worker crash rule (ADR-0067 D8.4, D-098)
    finally:
        db.close()


@pytest.mark.integration
def test_postgres_save_governance_decision_uses_athlete_profile_id(tmp_path, monkeypatch):
    """PostgreSQL save_governance_decision() must write athlete_profile_id to athlete_id column (Fix C)."""
    from titan.core import database as db_module

    monkeypatch.setattr(db_module, "psycopg2", _FakePsycopg2())

    db = db_module.PostgreSQLDatabaseManager(dsn="postgres://fake")
    try:
        db.save_governance_decision({
            "date": "2026-04-10",
            "session_planned": "EASY",
            "session_post_governance": "EASY",
            "athlete_profile_id": "ATH_PG",
        })
        with db._conn.cursor() as cursor:
            cursor.execute(
                "SELECT athlete_id FROM governance_outcomes WHERE date = ?", ("2026-04-10",)
            )
            rows = cursor.fetchall()
        assert rows, "Expected at least one governance_outcomes row"
        assert rows[0][0] == "ATH_PG"
    finally:
        db.close()


@pytest.mark.integration
def test_postgres_save_governance_decision_defaults_athlete_id_when_missing(tmp_path, monkeypatch):
    """PostgreSQL save_governance_decision() must default athlete_id to 'owner' when key absent (v13)."""
    from titan.core import database as db_module

    monkeypatch.setattr(db_module, "psycopg2", _FakePsycopg2())

    db = db_module.PostgreSQLDatabaseManager(dsn="postgres://fake")
    try:
        db.save_governance_decision({
            "date": "2026-04-11",
            "session_planned": "REST",
            "session_post_governance": "REST",
        })
        with db._conn.cursor() as cursor:
            cursor.execute(
                "SELECT athlete_id FROM governance_outcomes WHERE date = ?", ("2026-04-11",)
            )
            rows = cursor.fetchall()
        assert rows, "Expected at least one governance_outcomes row"
        assert rows[0][0] == "owner"
    finally:
        db.close()


@pytest.mark.integration
def test_postgres_save_session_sql_has_on_conflict_do_nothing():
    """T5-73: PostgreSQL save_session INSERT must contain ON CONFLICT (garmin_activity_id) DO NOTHING.

    Matches SQLite INSERT OR IGNORE semantics. Without this clause a duplicate
    garmin_activity_id from a re-sync raises IntegrityError.

    Source inspection is used because the _FakePsycopg2 adapter strips ON CONFLICT
    clauses to remain compatible with the in-memory SQLite backend.
    """
    import inspect

    from titan.core.database import PostgreSQLDatabaseManager

    source = inspect.getsource(PostgreSQLDatabaseManager.save_session)
    assert "ON CONFLICT (garmin_activity_id) DO NOTHING" in source, (
        "PostgreSQLDatabaseManager.save_session must include "
        "'ON CONFLICT (garmin_activity_id) DO NOTHING' to match SQLite OR IGNORE semantics"
    )

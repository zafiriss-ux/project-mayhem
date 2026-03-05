import queue
import threading
from unittest.mock import MagicMock, patch

import pytest

from titan.core.database import DatabaseManager


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


def test_get_active_shoes_returns_rows_when_database_open(tmp_path):
    db = DatabaseManager(db_name="happy_path.db", db_dir=tmp_path)

    shoe_id = db.add_shoe("Pegasus", "DAILY", 800)

    rows = db.get_active_shoes()

    assert rows
    assert rows[0][0] == shoe_id

    db.close()


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
        lambda db: db.get_override_log(),
        lambda db: db.get_governance_decisions(),
    ],
)
def test_read_methods_fail_fast_after_close(tmp_path, read_method):
    db = DatabaseManager(db_name="closed_reads.db", db_dir=tmp_path)
    db.close()

    with pytest.raises(RuntimeError, match="closed"):
        read_method(db)


def test_save_daily_metric_cursor_inside_lock(tmp_path):
    db = DatabaseManager(db_name="save_daily_metric_guard.db", db_dir=tmp_path)

    _assert_write_method_uses_locked_guard(
        db,
        lambda: db.save_daily_metric(date="2026-03-05", weight=70.5),
    )


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


def test_save_hrr_cursor_inside_lock(tmp_path):
    db = DatabaseManager(db_name="save_hrr_guard.db", db_dir=tmp_path)

    _assert_write_method_uses_locked_guard(
        db,
        lambda: db.save_hrr(date="2026-03-05", hrr_60=30, hrr_120=45),
    )


def test_update_shoe_mileage_cursor_inside_lock(tmp_path):
    db = DatabaseManager(db_name="update_shoe_guard.db", db_dir=tmp_path)

    _assert_write_method_uses_locked_guard(
        db,
        lambda: db.update_shoe_mileage(shoe_id=1, distance_km=12.5, date="2026-03-05"),
    )


def test_add_shoe_cursor_inside_lock(tmp_path):
    db = DatabaseManager(db_name="add_shoe_guard.db", db_dir=tmp_path)

    _assert_write_method_uses_locked_guard(
        db,
        lambda: db.add_shoe(name="Pegasus", shoe_type="DAILY", max_km=800),
    )


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


def test_write_after_close_raises(tmp_path):
    db = DatabaseManager(db_name=":memory:", db_dir=tmp_path)
    db.close()

    with pytest.raises(RuntimeError, match="closed"):
        db.save_daily_metric(date="2026-03-05", weight=70.0)


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


def test_standalone_write_methods_commit_and_persist(tmp_path):
    db = DatabaseManager(db_name="standalone_commit_methods.db", db_dir=tmp_path)
    db.conn = _CommitSpyConnection(db.conn)

    db.save_daily_metric(date="2026-03-05", weight=70.2, rhr=50)
    assert db.conn.commit_calls == 1

    db.save_session(
        date="2026-03-05",
        session_type="EASY",
        distance_km=8.0,
        duration_sec=2400,
        rpe=4,
    )
    assert db.conn.commit_calls == 2

    db.save_hrr(date="2026-03-05", hrr_60=30, hrr_120=45)
    assert db.conn.commit_calls == 3

    shoe_id = db.add_shoe(name="Pegasus 40", shoe_type="DAILY", max_km=700)
    assert db.conn.commit_calls == 4

    db.update_shoe_mileage(shoe_id=shoe_id, distance_km=10.5, date="2026-03-05")
    assert db.conn.commit_calls == 5

    db.save_personal_best(distance_km=5.0, time_sec=1200, date="2026-03-05", race_name="City 5K")
    assert db.conn.commit_calls == 6

    cur = db.conn.cursor()
    cur.execute("SELECT COUNT(*) FROM daily_metrics WHERE date = ?", ("2026-03-05",))
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT COUNT(*) FROM training_log WHERE date = ?", ("2026-03-05",))
    assert cur.fetchone()[0] == 1
    cur.execute("SELECT hrr_60, hrr_120 FROM daily_metrics WHERE date = ?", ("2026-03-05",))
    assert cur.fetchone() == (30, 45)
    cur.execute("SELECT total_km FROM gear_usage WHERE id = ?", (shoe_id,))
    assert float(cur.fetchone()[0]) == 10.5
    cur.execute("SELECT COUNT(*) FROM personal_bests WHERE distance_km = ?", (5.0,))
    assert cur.fetchone()[0] == 1

    db.close()


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

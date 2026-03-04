import queue
import threading

import pytest

from titan.core.database import DatabaseManager


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

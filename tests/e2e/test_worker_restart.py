"""T-PRA-29 / D-2 (plan task #19): the worker process killed and restarted on one SQLite file.

The worker runs as a real process through ``titan.worker.main()`` (lock, signal
handler, backup, supervised routine, heartbeat) on a real database file. Only
the outside world is stubbed: Garmin, Telegram and weather come from the e2e
stubs in tests/e2e/conftest.py.
"""

from __future__ import annotations

import os
import signal
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.slow,
    pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals and flock"),
]

_ROOT = Path(__file__).resolve().parents[2]

# Runs titan.worker.main() with the e2e stubs in place of Garmin/Telegram/weather.
_WORKER = """
import importlib.util, sys
from datetime import UTC, datetime
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root))
spec = importlib.util.spec_from_file_location("e2e_stubs", root / "tests" / "e2e" / "conftest.py")
stubs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stubs)

import titan.worker as worker
from titan.orchestration.daily_coach import DailyCoach


def build(db, athlete_id="owner"):
    return DailyCoach(
        garmin_sync=stubs.StubGarminSync(today=datetime.now().strftime("%Y-%m-%d")),
        weather_api=stubs.StubWeather(),
        telegram_bot=stubs.StubTelegram(),
        hrv_engine=stubs.StubSimpleEngine(),
        tsb_engine=stubs.StubTSB(),
        readiness_engine=stubs.StubReadiness(),
        optimal_time_calc=stubs.StubOptimalTime(),
        nutrition_optimizer=stubs.StubNutrition(),
        weekly_planner=stubs.StubWeeklyPlanner(),
        db=db,
        athlete_id=athlete_id,
        engines=stubs.stub_engine_registry(),
        glycogen_accum=stubs.StubGlycogen(),
        governance=stubs.StubGovernance(),
        volume_load_gauge=stubs.StubVLG(),
        outcome_tracker=stubs.StubOutcomeTracker(),
    )


_routine = DailyCoach.run_morning_routine


def announced(self, *args, **kwargs):
    ok = _routine(self, *args, **kwargs)
    print(f"routine_done {ok}", flush=True)
    return ok


_claim = worker._claim_routine
_delivered = worker._mark_delivered


def claim(*args, **kwargs):
    claimed = _claim(*args, **kwargs)
    print(f"claim {claimed}", flush=True)
    return claimed


def delivered(*args, **kwargs):
    _delivered(*args, **kwargs)
    print("delivered", flush=True)


worker._build_daily_coach = build
worker._claim_routine = claim
worker._mark_delivered = delivered
DailyCoach.run_morning_routine = announced
# 08:00 UTC today: the morning routine is due whenever the test runs.
worker._utc_now = lambda: datetime.now(UTC).replace(hour=8, minute=0, second=0, microsecond=0)
worker._seconds_until_next_run = lambda *a, **k: 3600.0  # park until signalled
worker.main()
"""


def _start(data_dir: Path) -> subprocess.Popen:
    env = {
        **os.environ,
        "TITAN_DATA_DIR": str(data_dir),
        "TITAN_BACKUP_DIR": str(data_dir / "backups"),
        "WORKER_HEARTBEAT_INTERVAL_S": "1",
        "TELEGRAM_BOT_TOKEN": "",
        "TITAN_MULTI_ATHLETE": "",
    }
    return subprocess.Popen(
        [sys.executable, "-c", _WORKER, str(_ROOT)],
        cwd=data_dir,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )


def _wait_for(proc: subprocess.Popen, prefix: str) -> str:
    for line in proc.stdout:
        if line.startswith(prefix):
            return line.strip()
    raise AssertionError(f"worker exited (code {proc.wait(timeout=5)}) before printing {prefix!r}")


def _counts(db_file: Path, today: str) -> tuple[str, int, int]:
    conn = sqlite3.connect(db_file)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        sessions = conn.execute("SELECT COUNT(*) FROM training_log WHERE date = ?", (today,)).fetchone()[0]
        metrics = conn.execute("SELECT COUNT(*) FROM daily_metrics WHERE date = ?", (today,)).fetchone()[0]
    finally:
        conn.close()
    return integrity, sessions, metrics


def test_killed_worker_restarts_on_the_same_database_without_loss_or_duplicates(tmp_path: Path) -> None:
    today = datetime.now().strftime("%Y-%m-%d")
    db_file = tmp_path / "titan_core.db"

    first = _start(tmp_path)
    try:
        assert _wait_for(first, "claim") == "claim 1"
        assert _wait_for(first, "routine_done") == "routine_done True"
        assert _wait_for(first, "delivered") == "delivered"
        first.send_signal(signal.SIGKILL)  # crash: no shutdown path runs
        first.wait(timeout=10)
    finally:
        if first.poll() is None:
            first.kill()
        first.stdout.close()

    assert _counts(db_file, today) == ("ok", 1, 1)
    assert list((tmp_path / "backups").glob("*.db")), "the cycle's backup was not written"

    second = _start(tmp_path)  # the kernel freed the dead worker's flock
    try:
        # ADR-0060 D1, ADR-0067 D8.3: today's delivered row survived the crash, so the
        # restart does not run or send the morning routine a second time.
        assert _wait_for(second, "claim") == "claim False"
        second.send_signal(signal.SIGTERM)  # graceful stop this time
        assert second.wait(timeout=10) == 0
    finally:
        if second.poll() is None:
            second.kill()
        second.stdout.close()

    # Same day, same Garmin activity: the restart adds no second session or metric row.
    assert _counts(db_file, today) == ("ok", 1, 1)
    assert (tmp_path / "worker.heartbeat").exists()
    conn = sqlite3.connect(db_file)
    try:
        claims = conn.execute("SELECT COUNT(*) FROM worker_routine_executions").fetchone()[0]
    finally:
        conn.close()
    assert claims == 1

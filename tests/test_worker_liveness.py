"""AGENTS §8.14 INV-23 (T-PRA-22): worker heartbeat, watchdog, callback isolation, lock recovery.

1  heartbeat + healthcheck: the worker's silence is the unhealthy condition
2  thread watchdog: a dead CoachingScheduler thread → CRITICAL + metric + restart
3  callback isolation: one athlete's failing callback does not stop the others
4  singleton lock: a dead holder never wedges the next start
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import titan.worker as worker_mod
from titan.orchestration.coaching_scheduler import CoachingScheduler

_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict | None]]:
    calls: list[tuple[str, dict | None]] = []
    monkeypatch.setattr(
        "titan.observability.metrics.get_metrics",
        lambda: SimpleNamespace(counter=lambda name, *a, labels=None, **k: calls.append((name, labels))),
    )
    return calls


# ── 1. heartbeat and healthcheck ────────────────────────────────────────────


def test_check_heartbeat_missing_stale_and_fresh(tmp_path: Path) -> None:
    hb = tmp_path / worker_mod.HEARTBEAT_FILE
    assert worker_mod.check_heartbeat(hb, max_age_s=120)[0] is False

    worker_mod._write_heartbeat(hb)
    mtime = hb.stat().st_mtime
    assert worker_mod.check_heartbeat(hb, max_age_s=120, now=mtime + 60)[0] is True
    assert worker_mod.check_heartbeat(hb, max_age_s=120, now=mtime + 121)[0] is False


def test_sleep_with_heartbeat_beats_each_tick_and_stops(tmp_path: Path) -> None:
    hb = tmp_path / worker_mod.HEARTBEAT_FILE
    stop = threading.Event()

    assert worker_mod._sleep_with_heartbeat(stop, total_s=0.1, interval_s=0.02, heartbeat=hb) is False
    assert hb.exists()

    stop.set()
    assert worker_mod._sleep_with_heartbeat(stop, total_s=60, interval_s=0.02, heartbeat=hb) is True


def test_routine_within_budget_keeps_heartbeat(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    hb = tmp_path / worker_mod.HEARTBEAT_FILE
    release = threading.Event()
    beats: list[float] = []
    real_write = worker_mod._write_heartbeat

    def _record(path: Path) -> None:
        beats.append(time.monotonic())
        real_write(path)

    def _routine() -> None:
        release.wait(timeout=5)

    monkeypatch.setattr(worker_mod, "_write_heartbeat", _record)
    monkeypatch.setattr(worker_mod, "_build_daily_coach", lambda db: SimpleNamespace(run_morning_routine=_routine))
    threading.Timer(0.15, release.set).start()

    worker_mod._run_routine_supervised(None, hb, interval_s=0.02, budget_s=10)

    assert len(beats) >= 3  # beats while the routine runs, plus one at the end
    assert hb.exists()


def test_routine_over_budget_stops_heartbeat_and_logs_critical(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog
) -> None:
    hb = tmp_path / worker_mod.HEARTBEAT_FILE
    release = threading.Event()
    beats: list[float] = []
    started = time.monotonic()

    def _routine() -> None:
        release.wait(timeout=5)

    monkeypatch.setattr(worker_mod, "_write_heartbeat", lambda path: beats.append(time.monotonic() - started))
    monkeypatch.setattr(worker_mod, "_build_daily_coach", lambda db: SimpleNamespace(run_morning_routine=_routine))
    threading.Timer(0.4, release.set).start()

    with caplog.at_level(logging.CRITICAL, logger="titan.worker.runner"):
        worker_mod._run_routine_supervised(None, hb, interval_s=0.02, budget_s=0.1)

    overruns = [r for r in caplog.records if "worker_routine_overrun" in r.getMessage()]
    assert len(overruns) == 1 and overruns[0].levelno == logging.CRITICAL
    # No heartbeat between the end of the budget and the routine's end (only the final one).
    during_overrun = [b for b in beats[:-1] if b > 0.15]
    assert during_overrun == []


def test_routine_exception_is_logged_and_cycle_returns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, counted, caplog
) -> None:
    def _boom() -> None:
        raise RuntimeError("garmin down")

    monkeypatch.setattr(worker_mod, "_build_daily_coach", lambda db: SimpleNamespace(run_morning_routine=_boom))

    with caplog.at_level(logging.ERROR, logger="titan.worker.runner"):
        worker_mod._run_routine_supervised(None, tmp_path / "hb", interval_s=0.02, budget_s=10)

    assert any("worker_cycle_error" in r.getMessage() for r in caplog.records)
    assert ("worker_cycle_error", None) in counted


def test_compose_worker_has_heartbeat_healthcheck_and_log_rotation() -> None:
    compose = (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    worker = compose.split("  titan-worker:")[1]
    assert 'test: ["CMD", "python", "scripts/worker_healthcheck.py"]' in worker
    assert 'max-size: "10m"' in worker


def test_healthcheck_script_exit_codes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from titan.config.settings import get_settings

    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    get_settings.cache_clear()
    script = _ROOT / "scripts" / "worker_healthcheck.py"
    env = {**os.environ, "TITAN_DATA_DIR": str(tmp_path)}

    missing = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, check=False)
    assert missing.returncode == 1, missing.stdout + missing.stderr

    worker_mod._write_heartbeat(tmp_path / worker_mod.HEARTBEAT_FILE)
    fresh = subprocess.run([sys.executable, str(script)], env=env, capture_output=True, text=True, check=False)
    assert fresh.returncode == 0, fresh.stdout + fresh.stderr


# ── 2. thread watchdog ──────────────────────────────────────────────────────


@pytest.mark.filterwarnings("ignore::pytest.PytestUnhandledThreadExceptionWarning")  # the death is the point
def test_watchdog_restarts_dead_scheduler_thread_with_event_and_metric(
    tmp_path: Path, counted, caplog
) -> None:
    hb = tmp_path / worker_mod.HEARTBEAT_FILE
    calls: list[int] = []
    restarted = threading.Event()
    stop = threading.Event()

    def _callback() -> None:
        calls.append(1)
        if len(calls) == 1:
            raise SystemExit  # not an Exception: escapes isolation and kills the thread
        restarted.set()

    scheduler = CoachingScheduler(interval_seconds=0.01)
    scheduler.register_athlete("owner", _callback)
    scheduler.start()
    threading.Thread(target=lambda: (restarted.wait(timeout=5), stop.set()), daemon=True).start()

    with caplog.at_level(logging.INFO, logger="titan.worker.scheduler"):
        worker_mod._supervise_scheduler(scheduler, stop, heartbeat=hb, interval_s=0.05)
    scheduler.stop()

    assert restarted.is_set()
    died = [r for r in caplog.records if "worker_thread_died" in r.getMessage()]
    assert died and died[0].levelno == logging.CRITICAL
    assert ("worker_thread_died_total", {"thread": "CoachingScheduler"}) in counted
    assert hb.exists()


def test_watchdog_writes_no_heartbeat_when_thread_cannot_restart(tmp_path: Path, counted) -> None:
    hb = tmp_path / worker_mod.HEARTBEAT_FILE
    stop = threading.Event()

    class _DeadScheduler:
        starts = 0

        def is_alive(self) -> bool:
            return False

        def start(self) -> None:
            _DeadScheduler.starts += 1
            if _DeadScheduler.starts >= 2:
                stop.set()

    worker_mod._supervise_scheduler(_DeadScheduler(), stop, heartbeat=None, interval_s=0.01)
    assert not hb.exists()
    assert counted.count(("worker_thread_died_total", {"thread": "CoachingScheduler"})) >= 1


# ── 3. callback isolation ───────────────────────────────────────────────────


def test_failing_callback_does_not_stop_other_athletes(counted, caplog) -> None:
    scheduler = CoachingScheduler(interval_seconds=0.01)
    healthy = threading.Event()

    def _bad() -> None:
        raise RuntimeError("athlete-1 broke")

    scheduler.register_athlete("athlete-1", _bad)
    scheduler.register_athlete("athlete-2", healthy.set)

    with caplog.at_level(logging.ERROR, logger="titan.orchestration.coaching_scheduler"):
        scheduler.start()
        assert healthy.wait(timeout=2)
        scheduler.stop()

    assert ("scheduler_callback_error_total", None) in counted
    assert any("scheduler_callback_failed" in r.getMessage() for r in caplog.records)


# ── 4. singleton lock recovery ──────────────────────────────────────────────


def test_lock_records_holder_pid_and_refusal_keeps_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "worker.lock"
    monkeypatch.setattr(worker_mod, "_get_lock_file", lambda: lock_path)

    fh = worker_mod.acquire_worker_lock()
    assert fh is not None
    try:
        assert lock_path.read_text().strip() == str(os.getpid())
        assert worker_mod.acquire_worker_lock() is None
        assert lock_path.read_text().strip() == str(os.getpid())
    finally:
        fh.close()


@pytest.mark.skipif(sys.platform == "win32", reason="fcntl lock recovery is POSIX-only")
def test_killed_lock_holder_does_not_wedge_next_start(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    lock_path = tmp_path / "worker.lock"
    monkeypatch.setattr(worker_mod, "_get_lock_file", lambda: lock_path)
    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl,sys,time\n"
            f"fh=open({str(lock_path)!r},'a+')\n"
            "fcntl.flock(fh,fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
            "print('locked',flush=True)\n"
            "time.sleep(60)\n",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert holder.stdout.readline().strip() == "locked"
        assert worker_mod.acquire_worker_lock() is None

        holder.send_signal(signal.SIGKILL)
        holder.wait(timeout=5)

        fh = worker_mod.acquire_worker_lock()
        assert fh is not None
        fh.close()
    finally:
        if holder.poll() is None:
            holder.kill()
        holder.stdout.close()


def test_sigterm_handler_does_not_block_while_the_event_lock_is_held(monkeypatch: pytest.MonkeyPatch) -> None:
    """SIGTERM lands on the main thread, possibly while it is inside _shutdown.wait()
    holding the event's internal lock. Setting the event from the handler then waited
    forever and the worker ignored SIGTERM (the e2e restart test hung about 1 run in 10)."""
    event = threading.Event()
    monkeypatch.setattr(worker_mod, "_shutdown", event)
    handler_done = threading.Event()

    def deliver() -> None:
        worker_mod._handle_sigterm(signal.SIGTERM, None)
        handler_done.set()

    with event._cond:  # the state the main thread is in inside wait()
        caller = threading.Thread(target=deliver, daemon=True)
        caller.start()
        assert handler_done.wait(timeout=2), "the SIGTERM handler blocked on the event lock"

    assert event.wait(timeout=2), "the shutdown request was lost"

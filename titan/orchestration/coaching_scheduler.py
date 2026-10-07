from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

_log = logging.getLogger(__name__)


class CoachingScheduler:
    def __init__(self, interval_seconds: float = 60.0) -> None:
        self._interval_seconds = interval_seconds
        self._athlete_callbacks: dict[str, Callable[[], Any]] = {}
        self._athlete_locks: dict[str, threading.Lock] = {}
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def register_athlete(self, athlete_id: str, callback: Callable[[], Any]) -> None:
        if athlete_id in self._athlete_callbacks:
            msg = f"Athlete already registered: {athlete_id}"
            raise ValueError(msg)
        self._athlete_callbacks[athlete_id] = callback
        self._athlete_locks[athlete_id] = threading.Lock()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="CoachingScheduler", daemon=True)
        self._thread.start()

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_seconds * 2))

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            for athlete_id, callback in self._athlete_callbacks.items():
                self._run_athlete_cycle(athlete_id, callback)
            self._stop_event.wait(self._interval_seconds)

    def _run_athlete_cycle(self, athlete_id: str, callback: Callable[[], Any]) -> None:
        lock = self._athlete_locks[athlete_id]
        if not lock.acquire(blocking=False):
            return
        try:
            callback()
        except Exception:
            # INV-23(3): one athlete's failure must not stop the loop for the others.
            _log.exception("scheduler_callback_failed", extra={"athlete_id": athlete_id})
            from titan.observability.metrics import get_metrics

            get_metrics().counter("scheduler_callback_error_total")
        finally:
            lock.release()

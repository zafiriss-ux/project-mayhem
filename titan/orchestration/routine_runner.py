"""Runs the morning routine in a background thread, one run at a time (ADR-0058 Phase C).

The thread lifecycle used to live in ``DailyCoach.run_morning_routine_async``.
It lives here so that ``DailyCoach`` stays a synchronous coaching object; the
composition root (``titan/main.py``) owns the runner and its thread (D-035).
"""
from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from time import monotonic
from typing import Any

from titan.core.structured_events import structured_event_payload

# Same logger and component as before the move, so the event stream is unchanged.
_log = logging.getLogger("titan.orchestration.daily_coach")

ROUTINE_THREAD_NAME = "DailyCoachRoutine"


def _routine_event(action: str, **fields: Any) -> None:
    _log.info(json.dumps(structured_event_payload("daily_coach", action, **fields), default=str))


class BackgroundRoutineRunner:
    """Starts ``routine`` in a daemon thread unless a run already holds ``lock``.

    ``lock`` is the coach's routine lock (``DailyCoach.routine_lock``), which the
    coach also holds while it hydrates its engines, so a run never overlaps that.
    """

    def __init__(self, routine: Callable[[], Any], lock: threading.Lock) -> None:
        self._routine = routine
        self.lock = lock
        self.thread: threading.Thread | None = None
        self.started_monotonic: float | None = None

    def start(self, trigger_source: str = "async_call") -> bool:
        """Start a run. False if one is already running, True if the thread started."""
        acquired = self.lock.acquire(blocking=False)
        if not acquired:
            _routine_event(
                "morning_routine_skipped",
                trigger_source=trigger_source,
                reason="already_running",
            )
            return False

        def _run_and_release() -> None:
            try:
                self._routine()
            finally:
                self.lock.release()

        t = threading.Thread(
            target=_run_and_release,
            name=ROUTINE_THREAD_NAME,
            daemon=True,
        )
        self.thread = t
        self.started_monotonic = monotonic()
        t.start()
        return True

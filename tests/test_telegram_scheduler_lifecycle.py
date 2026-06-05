import threading

import pytest

from titan.integrations.telegram_bot import TitanTelegramBot


@pytest.mark.unit
def test_telegram_scheduler_worker_lifecycle(monkeypatch):
    bot = TitanTelegramBot(bot_token="dummy-token", chat_id="123")
    execution_count = {"count": 0}
    callback_ran = threading.Event()

    def _callback():
        execution_count["count"] += 1
        callback_ran.set()

    bot.schedule_task("unit-test-task", "07:00", _callback, days=["Monday"])

    def _fast_scheduler_worker():
        with bot._tasks_lock:
            tasks = list(bot.scheduled_tasks)
        for task in tasks:
            task["callback"]()
        bot._stop_event.wait(timeout=0.01)

    monkeypatch.setattr(bot, "_scheduler_worker", _fast_scheduler_worker)
    monkeypatch.setattr(bot, "_poll_worker", lambda: None)

    bot.start_bot()
    first_thread = bot._sched_thread

    bot.start_bot()

    assert callback_ran.wait(timeout=2), "Scheduled callback did not execute within 2 seconds"

    bot.stop_bot()
    assert bot._sched_thread is not None
    bot._sched_thread.join(timeout=5)

    assert first_thread is bot._sched_thread
    assert not bot._sched_thread.is_alive()
    assert execution_count["count"] == 1

"""
Telegram Bot - Real polling listener + scheduler

Uses pyTelegramBotAPI for real polling (not mock).
"""

import contextlib
import json
import logging
import os
import time
import threading
from datetime import datetime
from typing import Dict, List, Optional, Callable


from titan.utils.constants import _Secret


_log = logging.getLogger(__name__)


def _telegram_event(action: str, **fields) -> None:
    """Emit a structured Telegram delivery event as a single JSON log line."""
    _log.info(json.dumps({"flow": "telegram", "action": action, **fields}, default=str))


try:
    import telebot
    TELEBOT_AVAILABLE = True
except ImportError:
    TELEBOT_AVAILABLE = False


class TitanTelegramBot:
    """
    Full-featured Telegram bot with:
    - Real polling listener (hears /today, /sync, /stats, etc.)
    - Scheduled notifications (morning 07:00, weekly plan Sunday 20:00)
    - Rich markdown messages
    """

    def __init__(self, bot_token: str = None, chat_id=None):
        self.bot_token = _Secret(bot_token or os.getenv("TELEGRAM_BOT_TOKEN", ""))
        raw_id = chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        try:
            self.chat_id = int(raw_id)
        except (ValueError, TypeError):
            self.chat_id = raw_id  # keep as str until set

        self.bot = None
        self.is_running = False
        self._poll_thread: Optional[threading.Thread] = None
        self._sched_thread: Optional[threading.Thread] = None
        self._stop = False
        self._stop_event = threading.Event()
        self.scheduled_tasks: List[Dict] = []
        self.message_history: List[Dict] = []

        # Callbacks for commands – set by orchestration layer
        self.cmd_callbacks: Dict[str, Callable] = {}

        bot_token_value = self.bot_token
        if TELEBOT_AVAILABLE and bot_token_value:
            try:
                self.bot = telebot.TeleBot(bot_token_value, parse_mode="Markdown")
                self._register_handlers()
            except Exception as e:
                _telegram_event(
                    "failure",
                    failure_class="CALLBACK_ERROR",
                    subsystem="init",
                    error_class=e.__class__.__name__,
                    error_message=str(e),
                )
                print(f"⚠️  Telegram init warning: {e}")

    # ------------------------------------------------------------------ #
    # COMMAND HANDLERS
    # ------------------------------------------------------------------ #
    def _register_handlers(self):
        if not self.bot:
            return

        @self.bot.message_handler(commands=["start", "help"])
        def cmd_help(message):
            self.chat_id = message.chat.id  # auto-capture chat id
            text = (
                "🎯 *TITAN AI Coach* – Available Commands\n\n"
                "/today – Today's workout & optimal time\n"
                "/week – This week's training plan\n"
                "/stats – Performance summary\n"
                "/recovery – Recovery status (HRV, sleep, TSB)\n"
                "/nutrition – Today's full nutrition plan\n"
                "/sync – Force Garmin data sync\n"
                "/activities – Recent runs\n"
                "/drift – Cardiac drift analysis\n"
                "/shoes – Shoe recommendation for today\n"
                "/calibration – Governance calibration summary\n"
            )
            self.bot.reply_to(message, text)

        @self.bot.message_handler(commands=["today"])
        def cmd_today(message):
            if "today" in self.cmd_callbacks:
                result = self.cmd_callbacks["today"]()
                self.bot.reply_to(message, result or "⏳ Calculating...")
            else:
                self.bot.reply_to(message, "⏳ Daily coach not ready yet.")

        @self.bot.message_handler(commands=["week"])
        def cmd_week(message):
            if "week" in self.cmd_callbacks:
                result = self.cmd_callbacks["week"]()
                self.bot.reply_to(message, result or "⏳ Generating plan...")
            else:
                self.bot.reply_to(message, "⏳ Weekly planner not ready yet.")

        @self.bot.message_handler(commands=["stats"])
        def cmd_stats(message):
            if "stats" in self.cmd_callbacks:
                result = self.cmd_callbacks["stats"]()
                self.bot.reply_to(message, result or "⏳ Loading stats...")
            else:
                self.bot.reply_to(message, "⏳ Stats not ready yet.")

        @self.bot.message_handler(commands=["recovery"])
        def cmd_recovery(message):
            if "recovery" in self.cmd_callbacks:
                result = self.cmd_callbacks["recovery"]()
                self.bot.reply_to(message, result or "⏳ Checking recovery...")
            else:
                self.bot.reply_to(message, "⏳ Recovery engine not ready.")

        @self.bot.message_handler(commands=["nutrition"])
        def cmd_nutrition(message):
            if "nutrition" in self.cmd_callbacks:
                result = self.cmd_callbacks["nutrition"]()
                self.bot.reply_to(message, result or "⏳ Building nutrition plan...")
            else:
                self.bot.reply_to(message, "⏳ Nutrition optimizer not ready.")

        @self.bot.message_handler(commands=["sync"])
        def cmd_sync(message):
            self.bot.reply_to(message, "🔄 Starting Garmin sync...")
            if "sync" in self.cmd_callbacks:
                result = self.cmd_callbacks["sync"]()
                self.bot.reply_to(message, result or "✅ Sync complete.")
            else:
                self.bot.reply_to(message, "⏳ Sync not available yet.")

        @self.bot.message_handler(commands=["activities"])
        def cmd_activities(message):
            if "activities" in self.cmd_callbacks:
                result = self.cmd_callbacks["activities"]()
                self.bot.reply_to(message, result or "No activities found.")
            else:
                self.bot.reply_to(message, "⏳ Activity data not ready.")

        @self.bot.message_handler(commands=["drift"])
        def cmd_drift(message):
            if "drift" in self.cmd_callbacks:
                result = self.cmd_callbacks["drift"]()
                self.bot.reply_to(message, result or "No drift data yet.")
            else:
                self.bot.reply_to(message, "⏳ Drift analysis not ready.")

        @self.bot.message_handler(commands=["shoes"])
        def cmd_shoes(message):
            if "shoes" in self.cmd_callbacks:
                result = self.cmd_callbacks["shoes"]()
                self.bot.reply_to(message, result or "No shoe data configured.")
            else:
                self.bot.reply_to(message, "⏳ Equipment manager not ready.")

        @self.bot.message_handler(commands=["calibration"])
        def cmd_calibration(message):
            if "calibration" in self.cmd_callbacks:
                result = self.cmd_callbacks["calibration"]()
                self.bot.reply_to(message, result or "⏳ No calibration data yet.")
            else:
                self.bot.reply_to(message, "⏳ Outcome tracker not ready.")

    def register_command(self, command: str, callback: Callable):
        """Register a callback for a slash command."""
        self.cmd_callbacks[command] = callback

    # ------------------------------------------------------------------ #
    # SEND MESSAGES
    # ------------------------------------------------------------------ #
    def send_message(self, text: str, parse_mode: str = "Markdown") -> bool:
        if not self.chat_id:
            _telegram_event("slo_alert", slo_key="telegram_delivery_missing_chat_id", cause="INTEGRATION_CONFIG")
            _telegram_event(
                "failure",
                failure_class="SEND_FAIL",
                subsystem="send_message",
                reason="missing_chat_id",
            )
            print("⚠️  No chat_id – message not sent")
            return False
        if self.bot and TELEBOT_AVAILABLE:
            try:
                self.bot.send_message(int(self.chat_id), text, parse_mode=parse_mode)
                self.message_history.append({"ts": datetime.now().isoformat(), "text": text[:80]})
                return True
            except Exception as e:
                _telegram_event("slo_alert", slo_key="telegram_delivery_failed", cause="INTEGRATION_DELIVERY", error=str(e))
                _telegram_event(
                    "failure",
                    failure_class="SEND_FAIL",
                    subsystem="send_message",
                    error_class=e.__class__.__name__,
                    error_message=str(e),
                )
                print(f"❌ Telegram send error: {e}")
                return False
        else:
            # Fallback: log only
            print(f"📱 [Telegram] {text[:200]}")
            return True

    def send_weekly_plan(self, plan: Dict) -> bool:
        lines = [
            "🎯 *WEEKLY TRAINING PLAN*",
            f"Week of: {plan.get('week_start', 'N/A')}  |  Phase: {plan.get('phase', 'N/A')}",
            "",
            "📊 *Summary:*",
            f"• Volume: {plan.get('total_km', 0)} km",
            f"• Quality sessions: {plan.get('quality_count', 0)}",
            f"• Easy days: {plan.get('easy_count', 0)}  |  Rest: {plan.get('rest_count', 0)}",
            "",
            "💡 *Key Status:*",
            f"• Lactate threshold: {plan.get('lactate_threshold', 'N/A')} bpm",
            f"• HRV baseline: {plan.get('hrv_baseline', 'N/A')}",
            f"• TSB: {plan.get('tsb_status', 'N/A')}",
            "",
            "📅 *Daily Breakdown:*",
        ]
        for d in plan.get("daily_sessions", []):
            lines.append(
                f"*{d['day']}* – {d['session_type']} "
                f"({d.get('distance_km', 0)} km)"
            )
            lines.append(f"  └ {d.get('details', '')}")
            if d.get("optimal_time"):
                lines.append(f"  └ ⏰ Best time: {d['optimal_time']}")
        lines += ["", f"💪 {plan.get('motivation', 'Train smart!')}"]
        return self.send_message("\n".join(lines))

    def send_daily_coaching(self, data: Dict) -> bool:
        text = (
            f"🌅 *GOOD MORNING!*\n"
            f"{datetime.now().strftime('%A, %B %d, %Y')}\n\n"
            f"🏃 *Today:* {data.get('session_type', 'REST')} – {data.get('duration', 'N/A')}\n\n"
            f"⏰ *Optimal Run Time:* {data.get('optimal_time', 'N/A')}\n"
            f"  └ Dew point: {data.get('dew_point', 'N/A')}°C  |  {data.get('conditions', '')}\n\n"
            f"💊 *Recovery:*\n"
            f"  • HRV: {data.get('hrv_status', 'N/A')}\n"
            f"  • Sleep: {data.get('sleep_quality', 'N/A')}/100\n"
            f"  • Readiness: {data.get('readiness_score', 'N/A')}/100\n\n"
            f"🍽 *Nutrition:* {data.get('nutrition_plan', 'See /nutrition')}\n\n"
            f"👟 *Shoe:* {data.get('shoe', 'See /shoes')}\n"
        )
        if data.get("special_note"):
            text += f"\n⚠️ {data['special_note']}"
        return self.send_message(text)

    def send_post_run_analysis(self, data: Dict) -> bool:
        text = (
            f"✅ *RUN ANALYSIS*\n\n"
            f"📊 *Stats:*\n"
            f"  • Distance: {data.get('distance_km', 0)} km\n"
            f"  • Duration: {data.get('duration', 'N/A')}\n"
            f"  • Avg pace: {data.get('avg_pace', 'N/A')} /km\n"
            f"  • Avg HR: {data.get('avg_hr', 'N/A')} bpm\n\n"
            f"🔬 *Analysis:*\n"
            f"  • HR drift: {data.get('hr_drift', 'N/A')}%\n"
            f"  • Efficiency: {data.get('efficiency', 'N/A')}\n"
            f"  • Training load: {data.get('training_load', 'N/A')}\n\n"
            f"📈 *Next steps:*\n{data.get('next_steps', 'Recover and refuel')}\n"
        )
        return self.send_message(text)

    def send_alert(self, title: str, message: str, level: str = "warning") -> bool:
        emoji = {"critical": "🛑", "warning": "⚠️", "info": "ℹ️", "ok": "✅"}.get(level, "ℹ️")
        return self.send_message(f"{emoji} *{title}*\n\n{message}")

    # ------------------------------------------------------------------ #
    # SCHEDULER
    # ------------------------------------------------------------------ #
    def schedule_task(
        self,
        name: str,
        time_str: str,
        callback: Callable,
        days: List[str] = None
    ):
        all_days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
        self.scheduled_tasks.append({
            "name": name, "time": time_str,
            "callback": callback,
            "days": days or all_days,
        })
        print(f"📅 Scheduled: {name} at {time_str}")

    # ------------------------------------------------------------------ #
    # START / STOP
    # ------------------------------------------------------------------ #
    def start_bot(self):
        if self.is_running:
            return
        self.is_running = True
        self._stop = False
        self._stop_event.clear()

        # Scheduler thread
        self._sched_thread = threading.Thread(
            target=self._scheduler_worker, daemon=True, name="TelegramScheduler"
        )
        self._sched_thread.start()

        # Polling thread (real listener)
        if self.bot and TELEBOT_AVAILABLE:
            self._poll_thread = threading.Thread(
                target=self._poll_worker, daemon=True, name="TelegramPoller"
            )
            self._poll_thread.start()
            print("✅ Telegram bot started (polling + scheduler)")
        else:
            print("✅ Telegram scheduler started (no polling – token missing or library unavailable)")

    def stop_bot(self):
        self._stop = True
        self._stop_event.set()
        self.is_running = False
        if self.bot and TELEBOT_AVAILABLE:
            with contextlib.suppress(Exception):
                self.bot.stop_polling()
        if self._sched_thread and self._sched_thread.is_alive():
            self._sched_thread.join(timeout=5)
        if self._poll_thread and self._poll_thread.is_alive():
            self._poll_thread.join(timeout=5)

    def _poll_worker(self):
        """Real polling loop – listens for user commands."""
        while not self._stop_event.is_set():
            try:
                self.bot.infinity_polling(timeout=10, long_polling_timeout=5)
            except Exception as e:
                if not self._stop_event.is_set():
                    _telegram_event(
                        "failure",
                        failure_class="POLL_FAIL",
                        subsystem="poll_worker",
                        error_class=e.__class__.__name__,
                        error_message=str(e),
                    )
                    print(f"⚠️  Polling error (retrying): {e}")
                    self._stop_event.wait(timeout=5)

    def _scheduler_worker(self):
        """Fires scheduled tasks at the right time."""
        expected_wakeup: Optional[float] = None
        while not self._stop_event.is_set():
            now_ts = time.time()
            if expected_wakeup is not None:
                drift_seconds = now_ts - expected_wakeup
                if drift_seconds > 1:
                    _telegram_event(
                        "failure",
                        failure_class="SCHEDULER_DRIFT",
                        subsystem="scheduler_worker",
                        drift_seconds=round(drift_seconds, 3),
                    )

            now = datetime.now()
            cur_time = now.strftime("%H:%M")
            cur_day  = now.strftime("%A")
            for task in self.scheduled_tasks:
                if task["time"] == cur_time and cur_day in task["days"]:
                    try:
                        task["callback"]()
                    except Exception as e:
                        _telegram_event(
                            "failure",
                            failure_class="CALLBACK_ERROR",
                            subsystem="scheduler_worker",
                            task_name=task["name"],
                            error_class=e.__class__.__name__,
                            error_message=str(e),
                        )
                        print(f"❌ Task '{task['name']}' error: {e}")
            # Sleep until next full minute
            sleep_seconds = max(1, 60 - now.second)
            expected_wakeup = now_ts + sleep_seconds
            self._stop_event.wait(timeout=sleep_seconds)

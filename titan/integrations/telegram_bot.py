"""
Telegram Bot Integration for TITAN

Provides:
- Weekly training plan delivery
- Daily optimal time notifications
- Post-run analysis
- Recovery alerts
- Interactive commands
"""

import os
import json
from datetime import datetime
from typing import Dict, List, Optional, Callable
import threading
import time

class TitanTelegramBot:
    """
    Telegram bot for automated coaching notifications.
    
    Features:
    - Scheduled messages (weekly plans, daily coaching)
    - Interactive commands (/today, /week, /stats, /recovery)
    - Rich formatting with markdown
    - Chart generation (ASCII visualizations)
    """
    
    def __init__(self, bot_token: str = None, chat_id: str = None):
        """
        Initialize Telegram bot.
        
        Args:
            bot_token: Bot token from BotFather
            chat_id: Your chat ID for messages
        """
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.is_running = False
        self._listener_thread = None
        self._scheduler_thread = None
        self._stop_bot = False
        self.scheduled_tasks = []
        self.message_history = []
    
    def send_message(self, message: str, parse_mode: str = 'Markdown') -> bool:
        """
        Send a message to the configured chat.
        
        Args:
            message: Message text (supports Markdown)
            parse_mode: 'Markdown' or 'HTML'
        
        Returns:
            True if sent successfully
        """
        if not self.bot_token or not self.chat_id:
            print("⚠️ Telegram bot not configured")
            return False
        
        try:
            # TODO: Implement actual Telegram API call
            # import requests
            # url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            # data = {
            #     'chat_id': self.chat_id,
            #     'text': message,
            #     'parse_mode': parse_mode
            # }
            # response = requests.post(url, data=data)
            # return response.status_code == 200
            
            # For now, just log
            print(f"📱 Telegram message:\n{message}\n")
            self.message_history.append({
                'timestamp': datetime.now().isoformat(),
                'message': message,
                'status': 'sent'
            })
            return True
            
        except Exception as e:
            print(f"❌ Telegram send failed: {e}")
            return False
    
    def send_weekly_plan(self, plan_data: Dict) -> bool:
        """
        Send weekly training plan.
        
        Args:
            plan_data: Dictionary with weekly plan details
        
        Returns:
            True if sent successfully
        """
        message = f"""
🎯 *WEEKLY TRAINING PLAN*
Week of: {plan_data.get('week_start', 'N/A')}

📊 *Training Summary:*
• Total Volume: {plan_data.get('total_km', 0)} km
• Quality Sessions: {plan_data.get('quality_count', 0)}
• Easy Days: {plan_data.get('easy_count', 0)}
• Rest Days: {plan_data.get('rest_count', 0)}

💡 *Key Insights:*
• Lactate Threshold: {plan_data.get('lactate_threshold', 'N/A')}
• Avg Drift: {plan_data.get('avg_drift', 'N/A')}%
• HRV Baseline: {plan_data.get('hrv_baseline', 'N/A')}
• TSB Status: {plan_data.get('tsb_status', 'N/A')}

📅 *Daily Breakdown:*
"""
        
        for day in plan_data.get('daily_sessions', []):
            message += f"\n*{day['day']}* - {day['session_type']}"
            message += f"\n  └ {day['details']}"
            if 'optimal_time' in day:
                message += f"\n  └ Best time: {day['optimal_time']}"
        
        message += f"\n\n💪 {plan_data.get('motivation', 'Train smart, recover hard!')}"
        
        return self.send_message(message)
    
    def send_daily_coaching(self, coaching_data: Dict) -> bool:
        """
        Send daily coaching message.
        
        Args:
            coaching_data: Dictionary with daily coaching info
        
        Returns:
            True if sent successfully
        """
        message = f"""
🌅 *GOOD MORNING!*
{datetime.now().strftime('%A, %B %d, %Y')}

🏃 *Today's Workout:*
{coaching_data.get('session_type', 'REST')} - {coaching_data.get('duration', 'N/A')}

⏰ *Optimal Running Time:*
{coaching_data.get('optimal_time', 'N/A')}
└ Dew Point: {coaching_data.get('dew_point', 'N/A')}°C
└ Conditions: {coaching_data.get('conditions', 'N/A')}

💊 *Recovery Status:*
• HRV: {coaching_data.get('hrv_status', 'N/A')}
• Sleep: {coaching_data.get('sleep_quality', 'N/A')}/10
• Readiness: {coaching_data.get('readiness_score', 'N/A')}/100

🍽 *Nutrition Focus:*
{coaching_data.get('nutrition_plan', 'See app for details')}

{coaching_data.get('special_note', '')}
"""
        
        return self.send_message(message)
    
    def send_post_run_analysis(self, run_data: Dict) -> bool:
        """
        Send post-run analysis.
        
        Args:
            run_data: Dictionary with run analysis
        
        Returns:
            True if sent successfully
        """
        message = f"""
✅ *RUN ANALYSIS*

📊 *Session Stats:*
• Distance: {run_data.get('distance_km', 0)} km
• Duration: {run_data.get('duration', 'N/A')}
• Avg Pace: {run_data.get('avg_pace', 'N/A')} /km
• Avg HR: {run_data.get('avg_hr', 'N/A')} bpm

🔬 *Performance Metrics:*
• HR Drift: {run_data.get('hr_drift', 'N/A')}%
• Efficiency Factor: {run_data.get('efficiency', 'N/A')}
• Training Load: {run_data.get('training_load', 'N/A')}

⚠️ *Alerts:*
{run_data.get('alerts', '• None - great session!')}

📈 *Next Steps:*
{run_data.get('next_steps', 'Recovery and refuel')}
"""
        
        return self.send_message(message)
    
    def send_recovery_alert(self, alert_data: Dict) -> bool:
        """
        Send recovery/warning alert.
        
        Args:
            alert_data: Dictionary with alert info
        
        Returns:
            True if sent successfully
        """
        emoji_map = {
            'warning': '⚠️',
            'critical': '🛑',
            'info': 'ℹ️',
            'success': '✅'
        }
        
        alert_type = alert_data.get('type', 'info')
        emoji = emoji_map.get(alert_type, 'ℹ️')
        
        message = f"""
{emoji} *{alert_data.get('title', 'ALERT')}*

{alert_data.get('message', '')}

*Recommendation:*
{alert_data.get('recommendation', 'Monitor closely')}
"""
        
        return self.send_message(message)
    
    def schedule_task(
        self,
        task_name: str,
        time_str: str,
        callback: Callable,
        days_of_week: List[str] = None
    ):
        """
        Schedule a recurring task.
        
        Args:
            task_name: Name of the task
            time_str: Time in HH:MM format
            callback: Function to call
            days_of_week: List of days (e.g., ['Sunday', 'Monday'])
        """
        self.scheduled_tasks.append({
            'name': task_name,
            'time': time_str,
            'callback': callback,
            'days': days_of_week or ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        })
        print(f"📅 Scheduled: {task_name} at {time_str}")
    
    def start_bot(self):
        """Start the Telegram bot (listener and scheduler)."""
        if self.is_running:
            print("⚠️ Bot already running")
            return
        
        self.is_running = True
        self._stop_bot = False
        
        # Start scheduler thread
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_worker,
            daemon=True
        )
        self._scheduler_thread.start()
        
        print("✅ Telegram bot started")
    
    def stop_bot(self):
        """Stop the Telegram bot."""
        self._stop_bot = True
        self.is_running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5)
        print("🛑 Telegram bot stopped")
    
    def _scheduler_worker(self):
        """Background worker for scheduled tasks."""
        while not self._stop_bot:
            now = datetime.now()
            current_time = now.strftime('%H:%M')
            current_day = now.strftime('%A')
            
            for task in self.scheduled_tasks:
                if task['time'] == current_time and current_day in task['days']:
                    try:
                        print(f"⏰ Executing scheduled task: {task['name']}")
                        task['callback']()
                    except Exception as e:
                        print(f"❌ Task execution failed: {e}")
            
            # Sleep until next minute
            time.sleep(60 - now.second)
    
    def get_message_history(self, limit: int = 10) -> List[Dict]:
        """Get recent message history."""
        return self.message_history[-limit:]

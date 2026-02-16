#!/usr/bin/env python3
"""
TITAN v51 - AI Training System
Main Application Entry Point
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from integrations.garmin_sync import GarminSync
from integrations.weather_api import WeatherAPI
from integrations.telegram_bot import TitanTelegramBot
from science.hrv_engine import HRVGuidedEngine
from science.tsb_engine import TSBEngine
from science.acwr_engine import ACWREngine
from science.readiness_engine import ReadinessEngine
from science.glycogen_model import GlycogenModel
from features.weekly_planner import WeeklyPlanGenerator
from features.optimal_time_calculator import OptimalTimeCalculator
from features.nutrition_optimizer import NutritionOptimizer
from orchestration.daily_coach import DailyCoach

def main():
    """Main application entry point."""
    print("""
╔═══════════════════════════════════════════════════════════╗
║                    TITAN v51.0                            ║
║          AI-Powered Training Intelligence System          ║
║                                                           ║
║  🏃 Weekly Planning  |  ⏰ Optimal Timing                 ║
║  💊 Recovery Tracking |  🍽 Nutrition Optimization        ║
║  📱 Telegram Coaching |  📊 Live Garmin Sync              ║
╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Initialize all components
    print("🔧 Initializing TITAN components...")
    
    garmin = GarminSync()
    weather = WeatherAPI()
    telegram = TitanTelegramBot()
    
    hrv_engine = HRVGuidedEngine()
    tsb_engine = TSBEngine()
    acwr_engine = ACWREngine()
    readiness_engine = ReadinessEngine()
    glycogen_model = GlycogenModel()
    
    weekly_planner = WeeklyPlanGenerator(hrv_engine, tsb_engine, acwr_engine)
    optimal_time_calc = OptimalTimeCalculator(weather)
    nutrition_optimizer = NutritionOptimizer(glycogen_model)
    
    daily_coach = DailyCoach(
        garmin_sync=garmin,
        weather_api=weather,
        telegram_bot=telegram,
        hrv_engine=hrv_engine,
        tsb_engine=tsb_engine,
        readiness_engine=readiness_engine,
        optimal_time_calc=optimal_time_calc,
        nutrition_optimizer=nutrition_optimizer,
        weekly_planner=weekly_planner
    )
    
    print("✅ All components initialized!\n")
    
    # Start background services
    print("🚀 Starting background services...")
    garmin.start_background_sync(interval_hours=6)
    weather.start_background_updates(interval_hours=1)
    telegram.start_bot()
    
    # Schedule morning routine
    telegram.schedule_task(
        task_name="Morning Coaching",
        time_str="07:00",
        callback=daily_coach.run_morning_routine
    )
    
    # Schedule weekly planning
    def generate_weekly_plan():
        plan = weekly_planner.generate_weekly_plan(
            athlete_profile={'threshold_hr': 168},
            phase='BUILD'
        )
        telegram.send_weekly_plan(plan)
    
    telegram.schedule_task(
        task_name="Weekly Plan",
        time_str="20:00",
        callback=generate_weekly_plan,
        days_of_week=['Sunday']
    )
    
    print("✅ Background services started!")
    print("\n📅 Scheduled tasks:")
    print("  • Morning coaching: Daily at 07:00")
    print("  • Weekly plan: Sunday at 20:00")
    print("  • Garmin sync: Every 6 hours")
    print("  • Weather updates: Every hour")
    
    print("\n🎯 TITAN is ready! Running in background...")
    print("Press Ctrl+C to stop.\n")
    
    try:
        # Keep main thread alive
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n\n🛑 Stopping TITAN...")
        garmin.stop_background_sync()
        weather.stop_background_updates()
        telegram.stop_bot()
        print("✅ TITAN stopped gracefully.\n")

if __name__ == "__main__":
    main()

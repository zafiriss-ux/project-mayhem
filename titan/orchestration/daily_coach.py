"""
Daily Coach - Main Orchestrator

Runs every morning to:
1. Sync Garmin data
2. Check recovery status
3. Calculate optimal running time
4. Generate nutrition plan
5. Send morning message via Telegram
"""

from datetime import datetime
from typing import Dict

class DailyCoach:
    """Daily coaching orchestrator."""
    
    def __init__(
        self,
        garmin_sync,
        weather_api,
        telegram_bot,
        hrv_engine,
        tsb_engine,
        readiness_engine,
        optimal_time_calc,
        nutrition_optimizer,
        weekly_planner
    ):
        """Initialize with all required components."""
        self.garmin = garmin_sync
        self.weather = weather_api
        self.telegram = telegram_bot
        self.hrv = hrv_engine
        self.tsb = tsb_engine
        self.readiness = readiness_engine
        self.optimal_time = optimal_time_calc
        self.nutrition = nutrition_optimizer
        self.weekly_planner = weekly_planner
    
    def run_morning_routine(self) -> bool:
        """Execute complete morning coaching routine."""
        print(f"\n🌅 Running morning routine: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        
        # Step 1: Sync Garmin data
        print("📥 Syncing Garmin data...")
        garmin_data = self.garmin.sync_all()
        
        # Process weight data
        if garmin_data.get('weight'):
            for entry in garmin_data['weight']:
                self.nutrition.add_weight_entry(entry['date'], entry['weight_kg'])
        
        # Process HRV data
        if garmin_data.get('hrv'):
            for entry in garmin_data['hrv']:
                self.hrv.add_hrv_measurement(entry['date'], entry['rmssd'])
        
        # Step 2: Calculate recovery status
        print("💊 Analyzing recovery status...")
        hrv_summary = self.hrv.get_hrv_summary()
        tsb_value, tsb_status = self.tsb.calculate_tsb()
        
        latest_hrv = hrv_summary.get('latest_hrv', 0)
        baseline_hrv = hrv_summary.get('baseline', 50)
        
        readiness = self.readiness.analyze_readiness(
            today_hrv=latest_hrv,
            baseline_hrv=baseline_hrv,
            today_rhr=50,  # Would come from Garmin
            baseline_rhr=48,
            sleep_score=8,
            soreness=3
        )
        
        # Step 3: Get today's planned session
        print("📋 Checking weekly plan...")
        # This would come from the weekly planner's stored plan
        today_session = {
            'session_type': 'TEMPO',
            'distance_km': 12,
            'duration_min': 60,
            'details': 'Tempo run with LT work'
        }
        
        # Step 4: Calculate optimal running time
        print("⏰ Calculating optimal running time...")
        optimal_time = self.optimal_time.calculate_optimal_time(
            session_type=today_session['session_type'],
            duration_hours=today_session['duration_min'] / 60,
            day_offset=0,
            tsb_value=tsb_value
        )
        
        # Step 5: Calculate nutrition plan
        print("🍽 Generating nutrition plan...")
        weight_trend = self.nutrition.analyze_weight_trend()
        current_weight = weight_trend.get('current_weight', 75.0)
        
        nutrition_plan = self.nutrition.calculate_daily_nutrition(
            weight_kg=current_weight,
            today_session=today_session
        )
        
        # Step 6: Package coaching message
        print("📱 Sending coaching message...")
        coaching_data = {
            'session_type': today_session['session_type'],
            'duration': f"{today_session['distance_km']} km",
            'optimal_time': optimal_time['recommended_time'],
            'dew_point': optimal_time['dew_point'],
            'conditions': optimal_time['quality'],
            'hrv_status': hrv_summary.get('trend', 'N/A'),
            'sleep_quality': 8,
            'readiness_score': readiness['score'],
            'nutrition_plan': f"{nutrition_plan['carbs_g']}g carbs, {nutrition_plan['protein_g']}g protein"
        }
        
        # Send via Telegram
        success = self.telegram.send_daily_coaching(coaching_data)
        
        print(f"\n{'✅' if success else '❌'} Morning routine completed\n")
        return success

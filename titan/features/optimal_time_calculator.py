"""
Optimal Running Time Calculator

Determines best time to run each day based on:
- Dew point throughout the day
- Temperature patterns
- Training stress balance (avoid running when fatigued)
- Session type requirements
"""

from datetime import datetime
from typing import Dict, List

class OptimalTimeCalculator:
    """
    Calculate optimal running times based on environmental and physiological factors.
    """

    def __init__(self, weather_api):
        """
        Initialize calculator.
        
        Args:
            weather_api: WeatherAPI instance for forecast data
        """
        self.weather_api = weather_api

    def calculate_optimal_time(
        self,
        session_type: str,
        duration_hours: float = 1.0,
        day_offset: int = 0,
        tsb_value: float = None,
        athlete_preferences: Dict = None
    ) -> Dict:
        """
        Calculate optimal running time for a session.
        
        Args:
            session_type: Type of session (INTERVALS, TEMPO, EASY, LONG_RUN)
            duration_hours: Expected session duration
            day_offset: Days from now (0 = today, 1 = tomorrow)
            tsb_value: Current Training Stress Balance
            athlete_preferences: Dict with circadian_preference, etc.
        
        Returns:
            Dictionary with optimal time window and reasoning
        """
        # Get weather forecast
        windows = self.weather_api.find_optimal_training_windows(
            day_offset=day_offset,
            duration_hours=duration_hours
        )

        if not windows:
            return {
                'recommended_time': 'No data available',
                'quality': 'UNKNOWN',
                'reasoning': []
            }

        # Apply session-type specific adjustments
        windows = self._apply_session_type_preferences(windows, session_type)

        # Apply TSB adjustments
        if tsb_value:
            windows = self._apply_tsb_adjustments(windows, tsb_value)

        # Apply athlete preferences
        if athlete_preferences:
            windows = self._apply_athlete_preferences(windows, athlete_preferences)

        # Re-sort after adjustments
        windows.sort(key=lambda x: x['score'])

        best_window = windows[0]

        return {
            'recommended_time': datetime.fromisoformat(best_window['start_time']).strftime('%H:%M'),
            'recommended_hour': best_window['start_hour'],
            'dew_point': best_window['avg_dew_point'],
            'temperature': best_window['avg_temp'],
            'quality': best_window['quality'],
            'reasoning': self._generate_reasoning(best_window, session_type, tsb_value),
            'alternatives': windows[1:3] if len(windows) > 1 else []
        }

    def _apply_session_type_preferences(
        self,
        windows: List[Dict],
        session_type: str
    ) -> List[Dict]:
        """
        Adjust window scores based on session type.
        
        Different session types benefit from different times of day:
        - INTERVALS: Late morning (9-11 AM) - body temperature peaked
        - TEMPO: Early morning (6-8 AM) or evening (5-7 PM)
        - LONG_RUN: Very early morning (5-7 AM) - cooler conditions
        - EASY: Flexible, but avoid heat
        """
        for window in windows:
            hour = window['start_hour']

            if session_type == 'INTERVALS':
                # Prefer late morning
                if 9 <= hour <= 11:
                    window['score'] -= 15  # Bonus
                elif hour < 7 or hour > 17:
                    window['score'] += 10  # Penalty

            elif session_type == 'LONG_RUN':
                # Prefer early morning
                if 5 <= hour <= 7:
                    window['score'] -= 20  # Big bonus
                elif hour > 10:
                    window['score'] += 15  # Penalty (heat risk)

            elif session_type == 'TEMPO':
                # Prefer early morning or evening
                if (6 <= hour <= 8) or (17 <= hour <= 19):
                    window['score'] -= 10
                elif 11 <= hour <= 15:
                    window['score'] += 15  # Midday penalty

            # EASY sessions are flexible - no adjustments needed

        return windows

    def _apply_tsb_adjustments(
        self,
        windows: List[Dict],
        tsb_value: float
    ) -> List[Dict]:
        """
        Adjust based on training stress balance.
        
        If fatigued (TSB < -20), prefer later in day when body is more warmed up.
        If fresh (TSB > 0), can run earlier.
        """
        for window in windows:
            hour = window['start_hour']

            if tsb_value < -20:  # Fatigued
                # Prefer later in day (muscles need more warm-up)
                if hour < 8:
                    window['score'] += 10  # Penalty for early
                elif 9 <= hour <= 11:
                    window['score'] -= 5  # Bonus for mid-morning

            elif tsb_value > 5:  # Fresh
                # Can handle early morning well
                if 5 <= hour <= 7:
                    window['score'] -= 5  # Slight bonus

        return windows

    def _apply_athlete_preferences(
        self,
        windows: List[Dict],
        preferences: Dict
    ) -> List[Dict]:
        """
        Apply athlete's circadian preferences.
        
        Args:
            preferences: Dict with 'circadian_preference' ('morning', 'evening', 'flexible')
        """
        circadian = preferences.get('circadian_preference', 'flexible')

        if circadian == 'morning':
            for window in windows:
                if window['start_hour'] < 9:
                    window['score'] -= 10  # Morning person bonus
                elif window['start_hour'] > 16:
                    window['score'] += 10  # Evening penalty

        elif circadian == 'evening':
            for window in windows:
                if window['start_hour'] >= 16:
                    window['score'] -= 10  # Evening person bonus
                elif window['start_hour'] < 9:
                    window['score'] += 10  # Morning penalty

        return windows

    def _generate_reasoning(
        self,
        window: Dict,
        session_type: str,
        tsb_value: float
    ) -> List[str]:
        """Generate human-readable reasoning for the recommendation."""
        reasons = []

        # Dew point reasoning
        dew = window['avg_dew_point']
        if dew < 12:
            reasons.append(f"✅ Low dew point ({dew}°C) - excellent conditions")
        elif dew < 15:
            reasons.append(f"👍 Comfortable dew point ({dew}°C)")
        elif dew < 18:
            reasons.append(f"⚠️ Moderate dew point ({dew}°C) - stay hydrated")
        else:
            reasons.append(f"🔥 High dew point ({dew}°C) - challenging conditions")

        # Temperature reasoning
        temp = window['avg_temp']
        if 12 <= temp <= 18:
            reasons.append(f"🌡 Ideal temperature ({temp}°C)")
        elif temp < 10:
            reasons.append(f"❄️ Cool ({temp}°C) - extra warm-up needed")
        elif temp > 20:
            reasons.append(f"☀️ Warm ({temp}°C) - pace conservatively")

        # Time of day reasoning
        hour = window['start_hour']
        if 5 <= hour <= 7:
            reasons.append("🌅 Early morning - quiet roads, cooler temps")
        elif 9 <= hour <= 11:
            reasons.append("☀️ Late morning - body temperature peaked")
        elif 17 <= hour <= 19:
            reasons.append("🌆 Evening - good for tempo work")

        # Session-type specific
        if session_type == 'LONG_RUN' and hour <= 7:
            reasons.append("🏃 Perfect for long run - beat the heat")
        elif session_type == 'INTERVALS' and 9 <= hour <= 11:
            reasons.append("⚡ Optimal for intervals - neuromuscular readiness peaked")

        # TSB-based reasoning
        if tsb_value:
            if tsb_value < -20 and hour > 8:
                reasons.append("💪 Later start recommended due to accumulated fatigue")
            elif tsb_value > 5 and hour < 8:
                reasons.append("✅ Early run OK - you're well-recovered")

        return reasons

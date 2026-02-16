"""
Weather API Integration with Optimal Time Analysis

Provides hourly weather forecasts with dew point calculation.
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import threading
import time

class WeatherAPI:
    """
    Weather API integration with intelligent caching.
    
    Features:
    - Hourly forecast (next 48 hours)
    - Dew point calculation
    - Heat stress index
    - Training condition recommendations
    - Automatic refresh in background thread
    """
    
    def __init__(self, api_key: str = None, location: str = None):
        """
        Initialize Weather API.
        
        Args:
            api_key: OpenWeatherMap API key (or load from env)
            location: Location string (e.g., "Athens,GR")
        """
        self.api_key = api_key or os.getenv('WEATHER_API_KEY')
        self.location = location or os.getenv('WEATHER_LOCATION', 'Athens,GR')
        self.cache = {}
        self.cache_timestamp = None
        self.cache_duration_hours = 1
        self._update_thread = None
        self._stop_update = False
    
    @staticmethod
    def calculate_dew_point(temp_c: float, humidity: int) -> float:
        """
        Calculate dew point from temperature and humidity.
        
        Magnus-Tetens formula.
        
        Args:
            temp_c: Temperature in Celsius
            humidity: Relative humidity (0-100)
        
        Returns:
            Dew point in Celsius
        """
        a, b = 17.27, 237.7
        alpha = ((a * temp_c) / (b + temp_c)) + (humidity / 100.0)
        dew_point = (b * alpha) / (a - alpha)
        return round(dew_point, 1)
    
    @staticmethod
    def classify_heat_stress(dew_point: float) -> Tuple[str, str]:
        """
        Classify training conditions based on dew point.
        
        Args:
            dew_point: Dew point in Celsius
        
        Returns:
            Tuple of (status, recommendation)
        """
        if dew_point > 24:
            return "🔥 EXTREME", "Avoid training - dangerous conditions"
        elif dew_point > 21:
            return "🟥 OPPRESSIVE", "Reduce intensity 20-30%, increase hydration"
        elif dew_point > 18:
            return "🟧 UNCOMFORTABLE", "Reduce pace 10-15 sec/km, monitor closely"
        elif dew_point > 15:
            return "🟨 STICKY", "Slight pace reduction, extra hydration"
        elif dew_point > 12:
            return "🟩 COMFORTABLE", "Normal training possible"
        elif dew_point > 8:
            return "🟦 PLEASANT", "Ideal conditions"
        else:
            return "🟪 DRY/COLD", "Good for fast running"
    
    def get_current_conditions(self) -> Dict:
        """
        Get current weather conditions.
        
        Returns:
            Dictionary with current conditions
        """
        # Check cache first
        if self.cache and self.cache_timestamp:
            age = (datetime.now() - self.cache_timestamp).total_seconds() / 3600
            if age < self.cache_duration_hours:
                return self.cache.get('current', {})
        
        # TODO: Implement actual API call
        # In production, use OpenWeatherMap or similar
        # For now, return simulated data
        
        current = {
            'timestamp': datetime.now().isoformat(),
            'temp_c': 18.5,
            'humidity': 65,
            'wind_speed': 10,
            'conditions': 'Clear',
            'dew_point': self.calculate_dew_point(18.5, 65)
        }
        
        heat_status, heat_rec = self.classify_heat_stress(current['dew_point'])
        current['heat_stress'] = heat_status
        current['recommendation'] = heat_rec
        
        # Update cache
        self.cache['current'] = current
        self.cache_timestamp = datetime.now()
        
        return current
    
    def get_hourly_forecast(self, hours: int = 48) -> List[Dict]:
        """
        Get hourly weather forecast.
        
        Args:
            hours: Number of hours to forecast
        
        Returns:
            List of hourly forecast dictionaries
        """
        # Check cache
        if self.cache and 'hourly' in self.cache:
            age = (datetime.now() - self.cache_timestamp).total_seconds() / 3600
            if age < self.cache_duration_hours:
                return self.cache['hourly'][:hours]
        
        # TODO: Implement actual API call
        # For now, generate simulated hourly data
        
        forecast = []
        base_temp = 15.0
        base_humidity = 60
        
        for i in range(hours):
            hour_time = datetime.now() + timedelta(hours=i)
            
            # Simulate temperature variation (cooler at night)
            hour_of_day = hour_time.hour
            temp_variation = 5 * (1 - abs(hour_of_day - 14) / 12)  # Peak at 2 PM
            temp = base_temp + temp_variation + (i * 0.1 if i < 24 else -i * 0.05)
            
            # Humidity inversely correlates with temperature
            humidity = max(40, min(90, base_humidity + (20 - temp_variation)))
            
            dew_point = self.calculate_dew_point(temp, humidity)
            heat_status, heat_rec = self.classify_heat_stress(dew_point)
            
            forecast.append({
                'timestamp': hour_time.isoformat(),
                'hour': hour_time.hour,
                'temp_c': round(temp, 1),
                'humidity': int(humidity),
                'dew_point': dew_point,
                'wind_speed': 8 + (i % 5),
                'conditions': 'Clear' if i % 3 != 0 else 'Partly Cloudy',
                'heat_stress': heat_status,
                'recommendation': heat_rec
            })
        
        # Update cache
        self.cache['hourly'] = forecast
        self.cache_timestamp = datetime.now()
        
        return forecast
    
    def find_optimal_training_windows(
        self,
        day_offset: int = 0,
        duration_hours: float = 1.0
    ) -> List[Dict]:
        """
        Find optimal training time windows based on weather.
        
        Args:
            day_offset: Days from now (0 = today, 1 = tomorrow)
            duration_hours: Training duration
        
        Returns:
            List of optimal time windows sorted by favorability
        """
        forecast = self.get_hourly_forecast(48)
        
        # Filter to target day
        target_date = (datetime.now() + timedelta(days=day_offset)).date()
        day_forecast = [f for f in forecast 
                       if datetime.fromisoformat(f['timestamp']).date() == target_date]
        
        # Score each potential window
        windows = []
        for i, hour_data in enumerate(day_forecast):
            if i + duration_hours > len(day_forecast):
                break
            
            # Calculate average conditions for window
            window_forecast = day_forecast[i:i+int(duration_hours)+1]
            avg_dew = sum(h['dew_point'] for h in window_forecast) / len(window_forecast)
            avg_temp = sum(h['temp_c'] for h in window_forecast) / len(window_forecast)
            
            # Score (lower is better)
            score = 0
            
            # Dew point scoring (prefer < 15°C)
            if avg_dew > 21:
                score += 50
            elif avg_dew > 18:
                score += 30
            elif avg_dew > 15:
                score += 15
            elif avg_dew < 12:
                score -= 10  # Bonus for good conditions
            
            # Temperature scoring (prefer 12-18°C)
            temp_diff = abs(avg_temp - 15)
            score += temp_diff * 2
            
            # Time of day preference (prefer early morning or evening)
            hour = hour_data['hour']
            if 5 <= hour <= 7:  # Early morning - best
                score -= 15
            elif 17 <= hour <= 19:  # Evening - good
                score -= 10
            elif 11 <= hour <= 15:  # Midday - worst
                score += 20
            
            windows.append({
                'start_time': hour_data['timestamp'],
                'start_hour': hour,
                'avg_dew_point': round(avg_dew, 1),
                'avg_temp': round(avg_temp, 1),
                'score': score,
                'quality': '🟩 EXCELLENT' if score < 10 else 
                          '🟨 GOOD' if score < 25 else 
                          '🟧 FAIR' if score < 40 else '🟥 POOR'
            })
        
        # Sort by score (best first)
        windows.sort(key=lambda x: x['score'])
        
        return windows
    
    def start_background_updates(self, interval_hours: int = 1):
        """Start background weather update thread."""
        if self._update_thread and self._update_thread.is_alive():
            return
        
        self._stop_update = False
        self._update_thread = threading.Thread(
            target=self._background_update_worker,
            args=(interval_hours,),
            daemon=True
        )
        self._update_thread.start()
        print(f"✅ Weather updates started (every {interval_hours}h)")
    
    def stop_background_updates(self):
        """Stop background updates."""
        self._stop_update = True
        if self._update_thread:
            self._update_thread.join(timeout=5)
    
    def _background_update_worker(self, interval_hours: int):
        """Background worker for weather updates."""
        while not self._stop_update:
            try:
                self.get_current_conditions()
                self.get_hourly_forecast()
            except Exception as e:
                print(f"❌ Weather update error: {e}")
            
            for _ in range(interval_hours * 3600):
                if self._stop_update:
                    break
                time.sleep(1)

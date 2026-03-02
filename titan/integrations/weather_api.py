"""
Weather API Integration with Optimal Time Analysis

Provides hourly weather forecasts with dew point calculation.
"""

import os
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import threading
import time

import requests


REQUESTS_VERIFY_SSL = True

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
        self._coords: Tuple[float, float] | None = None  # cached geocoding result

    @staticmethod
    def calculate_dew_point(temp_c: float, humidity: float) -> float:
        """
        Calculate dew point using the correct Magnus-Tetens formula.

        Formula (August-Roche-Magnus approximation):
            γ(T, RH) = (a·T)/(b+T) + ln(RH/100)
            Td = b·γ / (a − γ)

        where a = 17.27, b = 237.7 °C

        Reference: Lawrence, M.G. (2005). BAMS 86(2), 225-234.

        Known-value check (from literature):
            T=20°C, RH=50% → Td ≈ 9.3°C
            T=25°C, RH=80% → Td ≈ 21.4°C

        Args:
            temp_c:   Air temperature in °C
            humidity: Relative humidity in % (clamped to 1–100)

        Returns:
            Dew point in °C, rounded to 1 decimal place.
        """
        # Validate inputs
        humidity = max(1.0, min(100.0, float(humidity)))
        temp_c = float(temp_c)

        a, b = 17.27, 237.7
        gamma = (a * temp_c) / (b + temp_c) + math.log(humidity / 100.0)
        dew_point = (b * gamma) / (a - gamma)
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

    def _parse_location(self) -> Tuple[str, str]:
        """Split location into city/country components."""
        if "," in self.location:
            city, country = self.location.split(",", 1)
            return city.strip(), country.strip()
        return self.location.strip(), ""

    def _resolve_coordinates(self) -> Tuple[float, float]:
        """Resolve city location to coordinates via Open-Meteo geocoding API (cached)."""
        if self._coords is not None:
            return self._coords

        city, country = self._parse_location()
        params = {"name": city, "count": 1, "language": "en", "format": "json"}
        if country:
            params["country"] = country

        response = requests.get(
            "https://geocoding-api.open-meteo.com/v1/search",
            params=params,
            timeout=8,
            verify=REQUESTS_VERIFY_SSL,
        )
        response.raise_for_status()
        payload = response.json() or {}
        results = payload.get("results") or []
        if not results:
            raise ValueError(f"Location not found: {self.location}")

        self._coords = float(results[0]["latitude"]), float(results[0]["longitude"])
        return self._coords

    def _fetch_open_meteo(self) -> Tuple[Dict, List[Dict]]:
        """Fetch current conditions and hourly forecast from Open-Meteo."""
        lat, lon = self._resolve_coordinates()
        params = {
            "latitude": lat,
            "longitude": lon,
            "forecast_hours": 48,
            "hourly": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        }

        response = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params=params,
            timeout=10,
            verify=REQUESTS_VERIFY_SSL,
        )
        response.raise_for_status()
        payload = response.json() or {}

        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        temps = hourly.get("temperature_2m") or []
        humidity_vals = hourly.get("relative_humidity_2m") or []
        codes = hourly.get("weather_code") or []
        winds = hourly.get("wind_speed_10m") or []

        length = min(len(times), len(temps), len(humidity_vals), len(codes), len(winds), 48)
        forecast = []
        for i in range(length):
            dew_point = self.calculate_dew_point(temps[i], humidity_vals[i])
            heat_status, heat_rec = self.classify_heat_stress(dew_point)
            timestamp = datetime.fromisoformat(times[i]).isoformat()
            forecast.append({
                "timestamp": timestamp,
                "hour": datetime.fromisoformat(times[i]).hour,
                "temp_c": round(float(temps[i]), 1),
                "humidity": int(humidity_vals[i]),
                "dew_point": dew_point,
                "wind_speed": round(float(winds[i]), 1),
                "conditions": self._weather_code_to_text(int(codes[i])),
                "heat_stress": heat_status,
                "recommendation": heat_rec,
            })

        current_payload = payload.get("current") or {}
        temp_c = float(current_payload.get("temperature_2m", temps[0] if temps else 18.5))
        humidity = float(current_payload.get("relative_humidity_2m", humidity_vals[0] if humidity_vals else 65))
        wind_speed = float(current_payload.get("wind_speed_10m", winds[0] if winds else 10))
        weather_code = int(current_payload.get("weather_code", codes[0] if codes else 0))

        dew_point = self.calculate_dew_point(temp_c, humidity)
        heat_status, heat_rec = self.classify_heat_stress(dew_point)
        current = {
            "timestamp": datetime.now().isoformat(),
            "temp_c": round(temp_c, 1),
            "humidity": int(humidity),
            "wind_speed": round(wind_speed, 1),
            "conditions": self._weather_code_to_text(weather_code),
            "dew_point": dew_point,
            "heat_stress": heat_status,
            "recommendation": heat_rec,
        }
        return current, forecast

    @staticmethod
    def _weather_code_to_text(code: int) -> str:
        """Map Open-Meteo weather code to a concise description."""
        code_map = {
            0: "Clear",
            1: "Mainly Clear",
            2: "Partly Cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Rime Fog",
            51: "Light Drizzle",
            53: "Drizzle",
            55: "Dense Drizzle",
            61: "Light Rain",
            63: "Rain",
            65: "Heavy Rain",
            71: "Light Snow",
            73: "Snow",
            75: "Heavy Snow",
            80: "Rain Showers",
            81: "Rain Showers",
            82: "Heavy Showers",
            95: "Thunderstorm",
        }
        return code_map.get(code, "Unknown")

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

        try:
            current, forecast = self._fetch_open_meteo()
            self.cache['current'] = current
            self.cache['hourly'] = forecast
            self.cache_timestamp = datetime.now()
            return current
        except Exception:
            # Fallback when API/network is unavailable — data is synthetic
            print("⚠️  Weather API unavailable – using fallback conditions")
            dew_point = self.calculate_dew_point(18.5, 65)
            heat_status, heat_rec = self.classify_heat_stress(dew_point)
            current = {
                'timestamp': datetime.now().isoformat(),
                'temp_c': 18.5,
                'humidity': 65,
                'wind_speed': 10,
                'conditions': 'Clear',
                'dew_point': dew_point,
                'heat_stress': heat_status,
                'recommendation': heat_rec,
                'is_fallback': True,
            }
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

        try:
            current, forecast = self._fetch_open_meteo()
            self.cache['current'] = current
            self.cache['hourly'] = forecast
            self.cache_timestamp = datetime.now()
            return forecast[:hours]
        except Exception:
            # Fallback to deterministic simulated data
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
            duration_hours: Training duration in hours (supports fractional values)

        Returns:
            List of optimal time windows sorted by favorability

        Notes:
            required_slots = ceil(duration_hours) hourly buckets are consumed per
            window.  This ensures a 1.5-hour run occupies 2 slots (hours i and i+1)
            rather than the previous off-by-one that used int()+1 regardless of the
            fractional part.
        """
        if duration_hours <= 0:
            return []

        forecast = self.get_hourly_forecast(48)

        # Number of hourly buckets needed to cover the requested duration
        required_slots = max(1, math.ceil(duration_hours))

        # Filter to target day
        target_date = (datetime.now() + timedelta(days=day_offset)).date()
        day_forecast = [f for f in forecast
                       if datetime.fromisoformat(f['timestamp']).date() == target_date]

        # Score each potential window
        windows = []
        for i, hour_data in enumerate(day_forecast):
            if i + required_slots > len(day_forecast):
                break

            # Calculate average conditions for window
            window_forecast = day_forecast[i:i+required_slots]
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

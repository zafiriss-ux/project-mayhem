"""
Weather Integration — Open-Meteo (free, no API key required)

Provides 48-hour hourly forecasts, current conditions, dew-point calculation,
heat-stress classification, and optimal training window scoring.

Provider: https://open-meteo.com
  - Geocoding:  https://geocoding-api.open-meteo.com/v1/search
  - Forecast:   https://api.open-meteo.com/v1/forecast

No authentication needed.  WEATHER_API_KEY env var is accepted for
backward-compatibility but is not used.
"""

import copy
import importlib
import importlib.util
import json
import logging
import math
import os
import ssl
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Literal

from titan.science.data_trust import evaluate_weather_trust

WeatherDataQuality = Literal["live", "cached", "synthetic"]

_log = logging.getLogger(__name__)


def _weather_event(action: str, level: int = logging.INFO, **fields) -> None:
    """Emit a structured weather event as a single JSON log line."""
    payload = {"flow": "weather_api", "action": action, **fields}
    _log.log(level, json.dumps(payload, default=str))


REQUESTS_VERIFY_SSL = True
_HAS_REQUESTS = importlib.util.find_spec("requests") is not None
requests = importlib.import_module("requests") if _HAS_REQUESTS else None


class _UrllibResponse:
    """Tiny response adapter for urllib to match the subset we use from requests."""

    def __init__(self, body: bytes, status_code: int):
        self._body = body
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP error status: {self.status_code}")

    def json(self) -> dict[str, Any]:
        if not self._body:
            return {}
        return json.loads(self._body.decode("utf-8"))


def _http_get(url: str, *, params: dict[str, Any], timeout: int, verify: bool):
    """Issue HTTP GET via requests when installed, otherwise urllib fallback."""
    if _HAS_REQUESTS:
        return requests.get(url, params=params, timeout=timeout, verify=verify)

    query = urllib.parse.urlencode(params)
    full_url = f"{url}?{query}" if query else url
    context = ssl.create_default_context() if verify else ssl._create_unverified_context()

    with urllib.request.urlopen(full_url, timeout=timeout, context=context) as resp:
        body = resp.read()
        status_code = getattr(resp, "status", 200)
    return _UrllibResponse(body=body, status_code=status_code)


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
        Initialize WeatherAPI.

        Args:
            api_key: Ignored — Open-Meteo requires no authentication.
                     Accepted for backward-compatibility only.
            location: Location string (e.g., "Athens,GR")
        """
        self.api_key = api_key or os.getenv("WEATHER_API_KEY")  # unused; kept for compat
        self.location = location or os.getenv("WEATHER_LOCATION", "Athens,GR")
        self.cache = {}
        self.cache_timestamp = None
        self.cache_duration_hours = 1
        self._update_thread = None
        self._stop_event = threading.Event()
        self._coords: tuple[float, float] | None = None  # cached geocoding result

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
    def classify_heat_stress(dew_point: float) -> tuple[str, str]:
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

    def _parse_location(self) -> tuple[str, str]:
        """Split location into city/country components."""
        if "," in self.location:
            city, country = self.location.split(",", 1)
            return city.strip(), country.strip()
        return self.location.strip(), ""

    def _resolve_coordinates(self) -> tuple[float, float]:
        """Resolve city location to coordinates via Open-Meteo geocoding API (cached)."""
        if self._coords is not None:
            return self._coords

        city, country = self._parse_location()
        params = {"name": city, "count": 1, "language": "en", "format": "json"}
        if country:
            params["country"] = country

        response = _http_get(
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

    def _fetch_open_meteo(self) -> tuple[dict, list[dict]]:
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

        response = _http_get(
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
            forecast.append(
                {
                    "timestamp": timestamp,
                    "hour": datetime.fromisoformat(times[i]).hour,
                    "temp_c": round(float(temps[i]), 1),
                    "humidity": int(humidity_vals[i]),
                    "dew_point": dew_point,
                    "wind_speed": round(float(winds[i]), 1),
                    "conditions": self._weather_code_to_text(int(codes[i])),
                    "heat_stress": heat_status,
                    "recommendation": heat_rec,
                }
            )

        current_payload = payload.get("current") or {}
        temp_c = float(current_payload.get("temperature_2m", temps[0] if temps else 18.5))
        humidity = float(
            current_payload.get("relative_humidity_2m", humidity_vals[0] if humidity_vals else 65)
        )
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

    def get_current_conditions(self) -> dict:
        """
        Get current weather conditions.

        Returns:
            Dictionary with current conditions
        """
        # Check cache first
        if self.cache and self.cache_timestamp:
            age = (datetime.now() - self.cache_timestamp).total_seconds() / 3600
            if age < self.cache_duration_hours:
                current = copy.deepcopy(self.cache.get("current", {}))
                current["data_quality"] = "cached"
                current["data_trust"] = evaluate_weather_trust(data_quality="cached", data_age_hours=age).to_payload()
                return current

        try:
            current, forecast = self._fetch_open_meteo()
            current["data_quality"] = "live"
            for entry in forecast:
                entry["data_quality"] = "live"
            self.cache["current"] = current
            self.cache["hourly"] = forecast
            self.cache_timestamp = datetime.now()
            payload = copy.deepcopy(current)
            payload["data_trust"] = evaluate_weather_trust(data_quality="live", data_age_hours=0.0).to_payload()
            return payload
        except Exception as exc:
            # Fallback when API/network is unavailable — data is synthetic
            _weather_event(
                "weather_degraded_mode_active",
                level=logging.WARNING,
                source="get_current_conditions",
                error_class=type(exc).__name__,
                detail=str(exc),
            )
            dew_point = self.calculate_dew_point(18.5, 65)
            heat_status, heat_rec = self.classify_heat_stress(dew_point)
            current = {
                "timestamp": datetime.now().isoformat(),
                "temp_c": 18.5,
                "humidity": 65,
                "wind_speed": 10,
                "conditions": "Clear",
                "dew_point": dew_point,
                "heat_stress": heat_status,
                "recommendation": heat_rec,
                "is_fallback": True,
                "data_quality": "synthetic",
            }
            self.cache["current"] = current
            self.cache_timestamp = datetime.now()
            current["data_trust"] = evaluate_weather_trust(data_quality="synthetic", data_age_hours=0.0).to_payload()
            return current

    def get_hourly_forecast(self, hours: int = 48) -> list[dict]:
        """
        Get hourly weather forecast.

        Args:
            hours: Number of hours to forecast

        Returns:
            List of hourly forecast dictionaries
        """
        # Check cache
        if self.cache and "hourly" in self.cache:
            age = (datetime.now() - self.cache_timestamp).total_seconds() / 3600
            if age < self.cache_duration_hours:
                forecast = copy.deepcopy(self.cache["hourly"][:hours])
                for entry in forecast:
                    entry["data_quality"] = "cached"
                return forecast

        try:
            current, forecast = self._fetch_open_meteo()
            current["data_quality"] = "live"
            for entry in forecast:
                entry["data_quality"] = "live"
            self.cache["current"] = current
            self.cache["hourly"] = forecast
            self.cache_timestamp = datetime.now()
            return copy.deepcopy(forecast[:hours])
        except Exception as exc:
            # Fallback to deterministic simulated data when API is unavailable
            _weather_event(
                "weather_degraded_mode_active",
                level=logging.WARNING,
                source="get_hourly_forecast",
                error_class=type(exc).__name__,
                detail=str(exc),
            )
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

                forecast.append(
                    {
                        "timestamp": hour_time.isoformat(),
                        "hour": hour_time.hour,
                        "temp_c": round(temp, 1),
                        "humidity": int(humidity),
                        "dew_point": dew_point,
                        "wind_speed": 8 + (i % 5),
                        "conditions": "Clear" if i % 3 != 0 else "Partly Cloudy",
                        "heat_stress": heat_status,
                        "recommendation": heat_rec,
                        "is_fallback": True,
                        "data_quality": "synthetic",
                    }
                )

            # Update cache
            self.cache["hourly"] = forecast
            self.cache_timestamp = datetime.now()

            return forecast

    def find_optimal_training_windows(
        self, day_offset: int = 0, duration_hours: float = 1.0
    ) -> list[dict]:
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
        day_forecast = [
            f for f in forecast if datetime.fromisoformat(f["timestamp"]).date() == target_date
        ]

        # Score each potential window
        windows = []
        for i, hour_data in enumerate(day_forecast):
            if i + required_slots > len(day_forecast):
                break

            # Calculate average conditions for window
            window_forecast = day_forecast[i : i + required_slots]
            avg_dew = sum(h["dew_point"] for h in window_forecast) / len(window_forecast)
            avg_temp = sum(h["temp_c"] for h in window_forecast) / len(window_forecast)

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
            hour = hour_data["hour"]
            if 5 <= hour <= 7:  # Early morning - best
                score -= 15
            elif 17 <= hour <= 19:  # Evening - good
                score -= 10
            elif 11 <= hour <= 15:  # Midday - worst
                score += 20

            windows.append(
                {
                    "start_time": hour_data["timestamp"],
                    "start_hour": hour,
                    "avg_dew_point": round(avg_dew, 1),
                    "avg_temp": round(avg_temp, 1),
                    "score": score,
                    "quality": "🟩 EXCELLENT"
                    if score < 10
                    else "🟨 GOOD"
                    if score < 25
                    else "🟧 FAIR"
                    if score < 40
                    else "🟥 POOR",
                }
            )

        # Sort by score (best first)
        windows.sort(key=lambda x: x["score"])

        return windows

    def start_background_updates(self, interval_hours: int = 1):
        """Start background weather update thread."""
        if self._update_thread and self._update_thread.is_alive():
            return

        self._stop_event.clear()
        self._update_thread = threading.Thread(
            target=self._background_update_worker, args=(interval_hours,), daemon=True
        )
        self._update_thread.start()
        _weather_event("weather_background_updates_started", interval_hours=interval_hours)

    def stop_background_updates(self):
        """Stop background updates."""
        self._stop_event.set()
        if self._update_thread:
            self._update_thread.join(timeout=5)
        if self._update_thread and self._update_thread.is_alive():
            _weather_event(
                "worker_shutdown_timeout",
                level=logging.ERROR,
                worker_name="WeatherUpdater",
                timeout_seconds=5,
                still_alive=True,
            )

    def _background_update_worker(self, interval_hours: int):
        """Background worker for weather updates."""
        interval_seconds = interval_hours * 3600
        while not self._stop_event.is_set():
            try:
                self.get_current_conditions()
                self.get_hourly_forecast()
            except Exception as e:
                _weather_event(
                    "weather_background_update_error",
                    level=logging.ERROR,
                    error_class=type(e).__name__,
                    detail=str(e),
                )
            self._stop_event.wait(timeout=interval_seconds)

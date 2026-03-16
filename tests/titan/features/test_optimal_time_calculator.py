from titan.features.optimal_time_calculator import OptimalTimeCalculator


class StubWeatherAPI:
    def __init__(self, data_quality: str, weather_confidence: str | None = None):
        self.data_quality = data_quality
        self.weather_confidence = weather_confidence

    def get_current_conditions(self):
        payload = {"data_quality": self.data_quality}
        if self.weather_confidence is not None:
            payload["weather_confidence"] = self.weather_confidence
        return payload

    def find_optimal_training_windows(self, day_offset: int, duration_hours: float):
        return [
            {
                "start_time": "2026-03-04T06:00:00",
                "start_hour": 6,
                "avg_dew_point": 11.0,
                "avg_temp": 14.0,
                "score": 1,
                "quality": "🟩 EXCELLENT",
            }
        ]


def test_calculate_optimal_time_live_weather_includes_window():
    calculator = OptimalTimeCalculator(StubWeatherAPI(data_quality="live", weather_confidence="LIVE"))

    result = calculator.calculate_optimal_time(session_type="EASY")

    assert result["weather_data_quality"] == "live"
    assert result["weather_confidence"] == "LIVE"
    assert result["recommended_time"] == "06:00"
    assert result["quality"] == "🟩 EXCELLENT"


def test_calculate_optimal_time_synthetic_weather_returns_safe_window():
    calculator = OptimalTimeCalculator(
        StubWeatherAPI(data_quality="synthetic", weather_confidence="SYNTHETIC")
    )

    result = calculator.calculate_optimal_time(session_type="EASY")

    assert result["weather_data_quality"] == "synthetic"
    assert result["weather_confidence"] == "SYNTHETIC"
    assert result["weather_window_omitted"] is False
    assert result["recommended_time"] == "06:00-09:00"
    assert result["quality"] == "SAFE_FALLBACK"
    assert "dew_point" not in result


def test_calculate_optimal_time_defaults_to_synthetic_confidence_when_quality_is_synthetic():
    calculator = OptimalTimeCalculator(StubWeatherAPI(data_quality="synthetic"))

    result = calculator.calculate_optimal_time(session_type="EASY")

    assert result["weather_confidence"] == "SYNTHETIC"
    assert result["recommended_time"] == "06:00-09:00"


def test_calculate_optimal_time_propagates_esi_adjustment_fields():
    calculator = OptimalTimeCalculator(StubWeatherAPI(data_quality="live", weather_confidence="LIVE"))

    result = calculator.calculate_optimal_time(
        session_type="EASY",
        esi_level="HIGH",
        esi_pace_adjustment_sec_per_km=12,
    )

    assert result["esi_level"] == "HIGH"
    assert result["esi_pace_adjustment_sec_per_km"] == 12

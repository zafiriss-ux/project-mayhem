from titan.features.optimal_time_calculator import OptimalTimeCalculator


class StubWeatherAPI:
    def __init__(self, data_quality: str):
        self.data_quality = data_quality

    def get_current_conditions(self):
        return {"data_quality": self.data_quality}

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
    calculator = OptimalTimeCalculator(StubWeatherAPI(data_quality="live"))

    result = calculator.calculate_optimal_time(session_type="EASY")

    assert result["weather_data_quality"] == "live"
    assert result["recommended_time"] == "06:00"
    assert result["quality"] == "🟩 EXCELLENT"


def test_calculate_optimal_time_synthetic_weather_omits_window():
    calculator = OptimalTimeCalculator(StubWeatherAPI(data_quality="synthetic"))

    result = calculator.calculate_optimal_time(session_type="EASY")

    assert result["weather_data_quality"] == "synthetic"
    assert result["weather_window_omitted"] is True
    assert result["recommended_time"] == "N/A"
    assert "dew_point" not in result

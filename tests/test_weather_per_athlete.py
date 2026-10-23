"""Phase 4 step 6: weather per athlete (ADR-0067 D5.1; D-095).

- The owner keeps WEATHER_LOCATION from .env.
- Any other athlete's weather is for the location in their own profile, never the owner's,
  so two cities give two ESIs.
- An athlete without a location is not run and calls nothing.
"""

from __future__ import annotations

import pytest

from titan.core.athlete import AthleteNotReady
from titan.core.database import DatabaseManager
from titan.integrations import weather_api
from titan.integrations.weather_api import WeatherAPI
from titan.orchestration.daily_coach import _compute_esi

_A, _B = "a-0000000a", "a-0000000b"
# Hot and humid on the coast, cool inland; the latitude picks the conditions below.
_CITIES = {"Thessaloniki": (40.64, 22.94), "Florina": (40.78, 21.41), "Athens": (37.98, 23.73)}
_CONDITIONS = {40.64: (33.0, 70), 40.78: (12.0, 55), 37.98: (25.0, 50)}


def _profile(city: str, country: str = "GR") -> dict:
    return {
        "birth_date": "1988-07-02", "sex": "M", "weight_kg": 70.0, "height_cm": 178,
        "max_hr": 188, "threshold_hr": 168, "training_phase": "BUILD", "training_goal": "10K",
        "location_city": city, "location_country": country,
    }


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


@pytest.fixture
def open_meteo(monkeypatch) -> list[str]:
    """A fake Open-Meteo: geocoding by city name, conditions by latitude; records each city asked."""
    asked: list[str] = []

    def _get(url, params=None, **_kwargs):  # noqa: ANN001, ANN202
        if "geocoding" in url:
            asked.append(params["name"])
            lat, lon = _CITIES[params["name"]]
            return _Response({"results": [{"latitude": lat, "longitude": lon}]})
        temp, humidity = _CONDITIONS[params["latitude"]]
        return _Response({"current": {
            "temperature_2m": temp, "relative_humidity_2m": humidity, "weather_code": 0, "wind_speed_10m": 5,
        }})

    monkeypatch.setattr(weather_api, "_http_get", _get)
    return asked


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setenv("TITAN_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setenv("WEATHER_LOCATION", "Athens,GR")
    from titan.config.settings import get_settings

    get_settings.cache_clear()
    manager = DatabaseManager(db_dir=tmp_path)
    for index, (athlete, city) in enumerate(((_A, "Thessaloniki"), (_B, "Florina")), start=1):
        manager.conn.execute(
            "INSERT INTO athletes (athlete_id, display_name, created_at) VALUES (?, ?, 'now')",
            (athlete, athlete),
        )
        manager.save_athlete_profile(athlete, _profile(city))
        manager.bind_garmin_account(athlete, f"garmin-{athlete}")
        manager.set_garmin_token_state(athlete, "ok")
        from titan.integrations.garmin_sync import (
            athlete_token_path,  # a ready athlete has the token file (MA-F2)
        )
        athlete_token_path(athlete).parent.mkdir(parents=True, exist_ok=True)
        athlete_token_path(athlete).write_bytes(b"synthetic-token")
        manager.bind_telegram_chat(athlete, 7000 + index)
        manager.grant_consent(athlete, "v1")
    manager.conn.commit()
    yield manager
    manager.close()
    get_settings.cache_clear()


def _esi(weather: WeatherAPI) -> str:
    current = weather.get_current_conditions()
    level, _pace = _compute_esi(temperature_c=current["temp_c"], dew_point_c=current["dew_point"])
    return level


@pytest.mark.integration
def test_two_cities_give_two_esis(db, open_meteo) -> None:
    from titan import worker

    coach_a = worker._build_daily_coach(db, athlete_id=_A)
    coach_b = worker._build_daily_coach(db, athlete_id=_B)

    assert coach_a.weather.location == "Thessaloniki,GR"
    assert coach_b.weather.location == "Florina,GR"
    assert coach_a.optimal_time.weather_api is coach_a.weather
    esi_a, esi_b = _esi(coach_a.weather), _esi(coach_b.weather)
    assert esi_a != esi_b
    assert sorted(open_meteo) == ["Florina", "Thessaloniki"]


@pytest.mark.integration
def test_the_owner_keeps_weather_location(db, open_meteo) -> None:
    from titan import worker

    coach = worker._build_daily_coach(db)

    assert coach.weather.location == "Athens,GR"
    assert coach.weather.athlete_id == "owner"
    coach.weather.get_current_conditions()
    assert open_meteo == ["Athens"]


@pytest.mark.unit
@pytest.mark.parametrize("location", [None, "", " , "])
def test_an_athlete_never_gets_the_owners_location(location, monkeypatch) -> None:
    monkeypatch.setenv("WEATHER_LOCATION", "Athens,GR")

    with pytest.raises(ValueError, match="their own weather location"):
        WeatherAPI(location=location, athlete_id=_A)


@pytest.mark.integration
def test_an_athlete_without_a_location_is_not_run(db, open_meteo, monkeypatch) -> None:
    from titan import worker

    # A row written around save_athlete_profile, with the location emptied.
    db.conn.execute("UPDATE athlete_profiles SET location_city = '' WHERE athlete_id = ?", (_A,))
    db.conn.commit()
    monkeypatch.setattr(WeatherAPI, "__init__", lambda *a, **k: pytest.fail("weather built for an incomplete athlete"))

    with pytest.raises(AthleteNotReady):
        worker._build_daily_coach(db, athlete_id=_A)
    assert open_meteo == []

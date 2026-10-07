"""Centralised environment-variable configuration (P15-ARCH5)."""

import functools

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings


class TitanSettings(BaseSettings):
    TITAN_DATA_DIR: str = "/data"
    # AGENTS DR-01/DR-02: backups off the DB volume, retention via .env.
    TITAN_BACKUP_DIR: str = ""
    BACKUP_RETENTION_DAILY_DAYS: int = 7
    BACKUP_RETENTION_WEEKLY_COUNT: int = 4
    GARMIN_EMAIL: SecretStr = SecretStr("")
    GARMIN_PASSWORD: SecretStr = SecretStr("")
    TELEGRAM_BOT_TOKEN: SecretStr = SecretStr("")
    TELEGRAM_CHAT_ID: str = ""
    TITAN_JWT_PRIVATE_KEY: SecretStr = SecretStr("")
    TITAN_JWT_PUBLIC_KEY: str = ""
    TITAN_DB_BACKEND: str = "sqlite"
    TITAN_POSTGRES_DSN: str | None = None
    ATHLETE_MAX_HR: int = 160
    GARMIN_SYNC_TIMEOUT_S: int = 90
    WEATHER_LOCATION: str = "Athens,GR"
    TITAN_ML_KILL_SWITCH: str = "1"
    TITAN_ENV: str = ""
    TITAN_LOG_PATH: str = "titan.log"
    TITAN_ENABLE_API: str = ""
    TITAN_MULTI_ATHLETE: str = ""

    @model_validator(mode="after")
    def _postgres_dsn_required(self) -> "TitanSettings":
        if self.TITAN_DB_BACKEND == "postgres" and self.TITAN_POSTGRES_DSN is None:
            raise ValueError("TITAN_POSTGRES_DSN is required when TITAN_DB_BACKEND=postgres")
        return self


@functools.lru_cache(maxsize=1)
def get_settings() -> TitanSettings:
    return TitanSettings()

"""
BiometricRouter — source arbitration layer.
ADR-0055: Garmin preferred; ManualEntry fallback when Garmin data is stale (≥48h).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

_log = logging.getLogger(__name__)


@runtime_checkable
class BiometricSourceAdapter(Protocol):
    def get_hrv(self, date: str) -> float | None: ...
    def get_rhr(self, date: str) -> float | None: ...
    def get_sleep_hours(self, date: str) -> float | None: ...
    def get_weight_kg(self, date: str) -> float | None: ...
    def source_name(self) -> str: ...
    def data_age_hours(self) -> float: ...


class ManualEntryAdapter:
    """Reads manual_entry rows from daily_metrics. Fallback when Garmin is unavailable."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def get_hrv(self, date: str) -> float | None:
        row = self._db.get_daily_metric(date)
        if not row or row.get("data_source") != "manual_entry":
            return None
        return row.get("hrv_rmssd")

    def get_rhr(self, date: str) -> float | None:
        row = self._db.get_daily_metric(date)
        if not row or row.get("data_source") != "manual_entry":
            return None
        value = row.get("resting_hr")
        return float(value) if value is not None else None

    def get_sleep_hours(self, date: str) -> float | None:
        row = self._db.get_daily_metric(date)
        if not row or row.get("data_source") != "manual_entry":
            return None
        return row.get("sleep_hours")

    def get_weight_kg(self, date: str) -> float | None:
        row = self._db.get_daily_metric(date)
        if not row or row.get("data_source") != "manual_entry":
            return None
        return row.get("weight_kg")

    def source_name(self) -> str:
        return "manual_entry"

    def data_age_hours(self) -> float:
        # Manual entries are intentional — treat as always fresh
        return 0.0


class BiometricRouter:
    """
    Arbitrates between biometric sources.
    Primary: Garmin (age < 48h). Fallback: ManualEntry.
    Emits a structured warning log on source switch.
    """

    DATA_VOID_THRESHOLD_HOURS = 48.0

    def __init__(
        self,
        garmin_age_hours: float,
        manual_adapter: ManualEntryAdapter,
    ) -> None:
        self._garmin_age = garmin_age_hours
        self._manual = manual_adapter
        self._using_fallback = garmin_age_hours > self.DATA_VOID_THRESHOLD_HOURS
        if self._using_fallback:
            _log.warning(
                "BiometricRouter: Garmin data stale (%.1fh > %.1fh threshold). "
                "Switching to manual_entry fallback.",
                garmin_age_hours,
                self.DATA_VOID_THRESHOLD_HOURS,
            )

    @property
    def active_source(self) -> str:
        return "manual_entry" if self._using_fallback else "garmin"

    @property
    def using_fallback(self) -> bool:
        return self._using_fallback

    def get_hrv(self, date: str, garmin_value: float | None) -> float | None:
        if not self._using_fallback:
            return garmin_value
        return self._manual.get_hrv(date)

    def get_rhr(self, date: str, garmin_value: float | None) -> float | None:
        if not self._using_fallback:
            return garmin_value
        return self._manual.get_rhr(date)

    def get_sleep_hours(self, date: str, garmin_value: float | None) -> float | None:
        if not self._using_fallback:
            return garmin_value
        return self._manual.get_sleep_hours(date)

    def get_weight_kg(self, date: str, garmin_value: float | None) -> float | None:
        if not self._using_fallback:
            return garmin_value
        return self._manual.get_weight_kg(date)

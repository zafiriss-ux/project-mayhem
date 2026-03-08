"""TITAN Persistence Adapter — T5-08-B D1 scaffolding

Abstract contract layer that separates the coaching pipeline from any specific
storage backend (SQLite today; PostgreSQL in Phase 8A per ADR-0044).

Concrete implementations (Phase 8A work, not yet shipped):
  - SQLiteAdapter      — thin wrapper around the existing DatabaseManager
  - PostgreSQLAdapter  — SQLAlchemy Core + Alembic migrations

Until Phase 8A lands, callers continue to use DatabaseManager directly.
This module defines the interface they will eventually program against.

Thread-safety contract: every concrete backend must be safe for concurrent
access from multiple threads (matching the current DatabaseManager guarantee).
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from datetime import datetime
from typing import Any

from titan.core.database import DatabaseManager, PostgreSQLDatabaseManager

_log = logging.getLogger(__name__)


class PersistenceAdapter(ABC):
    """Abstract persistence adapter — the storage-backend contract for TITAN.

    All concrete backends (SQLite, PostgreSQL) must satisfy this interface so
    that orchestration code (DailyCoach, OutcomeTracker, etc.) can be written
    against the adapter rather than against backend-specific drivers.
    """

    # ------------------------------------------------------------------ #
    # Daily metrics                                                        #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def save_daily_metric(
        self,
        date: str,
        *,
        weight: float | None = None,
        hrv: float | None = None,
        rhr: int | None = None,
        sleep_hours: float | None = None,
        sleep_quality: int | None = None,
        soreness: int | None = None,
        fatigue: int | None = None,
        mood: int | None = None,
        notes: str | None = None,
        quality_flag: str | None = None,
    ) -> None:
        """Persist a morning check-in row (INSERT OR REPLACE semantics)."""

    @abstractmethod
    def get_baseline_rhr(self, days: int = 7) -> float | None:
        """Return the rolling median RHR over the last *days* days, or None."""

    @abstractmethod
    def get_hrv_history(self, days: int = 14) -> list[tuple[str, float]]:
        """Return [(date_iso, hrv_rmssd), ...] ordered newest-first."""

    @abstractmethod
    def get_weight_history(self, days: int = 30) -> list[tuple[str, float]]:
        """Return [(date_iso, weight_kg), ...] ordered newest-first."""

    # ------------------------------------------------------------------ #
    # Training sessions                                                    #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def save_session(
        self,
        date: str,
        session_type: str,
        distance_km: float,
        duration_sec: int,
        *,
        avg_hr: int | None = None,
        max_hr: int | None = None,
        rpe: int | None = None,
        shoe_id: int | None = None,
        surface: str | None = None,
        temperature_c: float | None = None,
        notes: str | None = None,
        garmin_activity_id: str | None = None,
        quality_flag: str | None = None,
    ) -> None:
        """Persist a training session row (INSERT OR IGNORE on duplicate)."""

    @abstractmethod
    def get_training_load_history(
        self, days: int | None = None
    ) -> list[tuple[str, float]]:
        """Return [(date_iso, training_load), ...] ordered newest-first."""

    @abstractmethod
    def get_ctl_atl_tsb(self) -> tuple[float, float, float]:
        """Return (CTL, ATL, TSB) as floats (Banister/Coggan model)."""

    # ------------------------------------------------------------------ #
    # Gear                                                                 #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def add_shoe(
        self, name: str, shoe_type: str = "DAILY", max_km: int = 800
    ) -> int:
        """Insert a new shoe row and return its generated id."""

    @abstractmethod
    def get_active_shoes(self) -> list[tuple]:
        """Return all active shoes as (id, name, type, total_km, max_km, …) tuples."""

    @abstractmethod
    def check_shoe_availability(self, shoe_id: int) -> tuple[bool, str]:
        """Return (available, reason_string)."""

    @abstractmethod
    def update_shoe_mileage(
        self, shoe_id: int, distance_km: float, date: str
    ) -> None:
        """Add *distance_km* to the shoe's running total."""

    # ------------------------------------------------------------------ #
    # Personal bests                                                       #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def save_personal_best(
        self,
        distance_km: float,
        time_seconds: int,
        date: str,
        *,
        race_name: str | None = None,
        notes: str | None = None,
    ) -> None:
        """Persist a personal-best row."""

    @abstractmethod
    def get_pr(
        self, distance_km: float
    ) -> tuple[int, str, str | None] | None:
        """Return (time_seconds, date, race_name) for the best at *distance_km*, or None."""

    # ------------------------------------------------------------------ #
    # Heart-rate recovery                                                  #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def save_hrr(self, date: str, hrr_60: int, hrr_120: int = 0) -> None:
        """Persist a heart-rate-recovery measurement."""

    @abstractmethod
    def get_hrr_history(
        self, days: int = 28
    ) -> list[tuple[str, int, int]]:
        """Return [(date_iso, hrr_60, hrr_120), ...] ordered newest-first."""

    # ------------------------------------------------------------------ #
    # Glycogen / critical speed                                            #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def update_glycogen_debt(self, date: str, debt_score: float) -> None:
        """Write or update the glycogen debt score for *date*."""

    @abstractmethod
    def log_cs_performance(
        self,
        date: str,
        critical_speed: float,
        w_prime: float,
        *,
        notes: str | None = None,
    ) -> None:
        """Persist a critical-speed test result."""

    @abstractmethod
    def get_cs_performances(
        self, limit: int = 10
    ) -> list[tuple[str, float, float]]:
        """Return [(date_iso, critical_speed, w_prime), ...] newest-first."""

    # ------------------------------------------------------------------ #
    # Override log                                                         #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def log_override(
        self,
        date: str,
        original_recommendation: str,
        override_reason: str,
        *,
        athlete_id: str = "default",
    ) -> None:
        """Record a manual coaching override."""

    @abstractmethod
    def record_override_signal(
        self,
        date: str,
        signal: str,
        *,
        athlete_id: str = "default",
    ) -> None:
        """Record a raw override signal for ratio tracking."""

    @abstractmethod
    def get_override_ratio(self, days: int = 14) -> float:
        """Return the fraction of sessions with overrides in the last *days* days."""

    @abstractmethod
    def get_override_log(self, limit: int = 50) -> list[dict[str, str]]:
        """Return the most recent override entries as dicts."""

    # ------------------------------------------------------------------ #
    # Governance outcomes                                                  #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def save_governance_decision(self, decision: dict[str, Any]) -> None:
        """Persist a governance decision snapshot."""

    @abstractmethod
    def update_governance_outcome(
        self,
        date: str,
        outcome: dict[str, Any],
        *,
        athlete_id: str = "default",
    ) -> None:
        """Update an existing governance decision row with its post-session outcome."""

    @abstractmethod
    def get_governance_decisions(
        self, limit: int = 1000
    ) -> list[dict[str, Any]]:
        """Return the most recent governance decision rows as dicts."""

    @abstractmethod
    def annotate_governance_outcome(self, date: str, note: str) -> bool:
        """Append a free-text annotation to a governance outcome row. Returns True on success."""

    # ------------------------------------------------------------------ #
    # Sync tracking                                                        #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def record_sync_outcome(
        self,
        source: str,
        success: bool,
        *,
        error_msg: str | None = None,
        records_synced: int = 0,
    ) -> None:
        """Record the result of an external-data sync (Garmin, weather, …)."""

    @abstractmethod
    def get_last_sync_outcome(self, source: str) -> dict[str, Any] | None:
        """Return the most recent sync outcome row for *source*, or None."""

    @abstractmethod
    def get_last_garmin_sync_timestamp(self) -> datetime | None:
        """Return the datetime of the most recent successful Garmin sync, or None."""

    # ------------------------------------------------------------------ #
    # Backup / lifecycle                                                   #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def backup_database(
        self, backup_dir: Any = None, keep: int = 30
    ) -> Any:
        """Trigger a backend-appropriate backup and return the backup path, or None."""

    @abstractmethod
    def transaction(self) -> AbstractContextManager:
        """Return a context manager that wraps multiple writes in a single transaction."""

    @abstractmethod
    def close(self) -> None:
        """Release all backend resources held by this adapter."""


class SQLiteAdapter(PersistenceAdapter):
    """SQLite persistence adapter backed by the existing ``DatabaseManager``."""

    def __init__(
        self,
        db_name: str = "titan_core.db",
        db_dir: Any = None,
        manager: DatabaseManager | None = None,
    ) -> None:
        self._manager = manager or DatabaseManager(db_name=db_name, db_dir=db_dir)

    def save_daily_metric(self, date: str, **kwargs: Any) -> None:
        self._manager.save_daily_metric(date, **kwargs)

    def get_baseline_rhr(self, days: int = 7) -> float | None:
        return self._manager.get_baseline_rhr(days=days)

    def get_hrv_history(self, days: int = 14) -> list[tuple[str, float]]:
        return self._manager.get_hrv_history(days=days)

    def get_weight_history(self, days: int = 30) -> list[tuple[str, float]]:
        return self._manager.get_weight_history(days=days)

    def save_session(
        self,
        date: str,
        session_type: str,
        distance_km: float,
        duration_sec: int,
        **kwargs: Any,
    ) -> None:
        self._manager.save_session(
            date,
            session_type,
            distance_km,
            duration_sec,
            **kwargs,
        )

    def get_training_load_history(
        self, days: int | None = None
    ) -> list[tuple[str, float]]:
        return self._manager.get_training_load_history(days=days)

    def get_ctl_atl_tsb(self) -> tuple[float, float, float]:
        return self._manager.get_ctl_atl_tsb()

    def add_shoe(
        self, name: str, shoe_type: str = "DAILY", max_km: int = 800
    ) -> int:
        return self._manager.add_shoe(name=name, shoe_type=shoe_type, max_km=max_km)

    def get_active_shoes(self) -> list[tuple]:
        return self._manager.get_active_shoes()

    def check_shoe_availability(self, shoe_id: int) -> tuple[bool, str]:
        return self._manager.check_shoe_availability(shoe_id=shoe_id)

    def update_shoe_mileage(
        self, shoe_id: int, distance_km: float, date: str
    ) -> None:
        self._manager.update_shoe_mileage(
            shoe_id=shoe_id,
            distance_km=distance_km,
            date=date,
        )

    def save_personal_best(
        self,
        distance_km: float,
        time_seconds: int,
        date: str,
        *,
        race_name: str | None = None,
        notes: str | None = None,
    ) -> None:
        self._manager.save_personal_best(
            distance_km=distance_km,
            time_seconds=time_seconds,
            date=date,
            race_name=race_name,
            notes=notes,
        )

    def get_pr(
        self, distance_km: float
    ) -> tuple[int, str, str | None] | None:
        return self._manager.get_pr(distance_km=distance_km)

    def save_hrr(self, date: str, hrr_60: int, hrr_120: int = 0) -> None:
        self._manager.save_hrr(date=date, hrr_60=hrr_60, hrr_120=hrr_120)

    def get_hrr_history(self, days: int = 28) -> list[tuple[str, int, int]]:
        return self._manager.get_hrr_history(days=days)

    def update_glycogen_debt(self, date: str, debt_score: float) -> None:
        self._manager.update_glycogen_debt(date=date, debt_score=debt_score)

    def log_cs_performance(
        self,
        date: str,
        critical_speed: float,
        w_prime: float,
        *,
        notes: str | None = None,
    ) -> None:
        self._manager.log_cs_performance(
            date=date,
            critical_speed=critical_speed,
            w_prime=w_prime,
            notes=notes,
        )

    def get_cs_performances(self, limit: int = 10) -> list[tuple[str, float, float]]:
        return self._manager.get_cs_performances(limit=limit)

    def log_override(
        self,
        date: str,
        original_recommendation: str,
        override_reason: str,
        *,
        athlete_id: str = "default",
    ) -> None:
        self._manager.log_override(
            date=date,
            original_recommendation=original_recommendation,
            override_reason=override_reason,
            athlete_id=athlete_id,
        )

    def record_override_signal(
        self,
        date: str,
        signal: str,
        *,
        athlete_id: str = "default",
    ) -> None:
        self._manager.record_override_signal(
            date=date,
            signal=signal,
            athlete_id=athlete_id,
        )

    def get_override_ratio(self, days: int = 14) -> float:
        return self._manager.get_override_ratio(days=days)

    def get_override_log(self, limit: int = 50) -> list[dict[str, str]]:
        return self._manager.get_override_log(limit=limit)

    def save_governance_decision(self, decision: dict[str, Any]) -> None:
        self._manager.save_governance_decision(decision=decision)

    def update_governance_outcome(
        self,
        date: str,
        outcome: dict[str, Any],
        *,
        athlete_id: str = "default",
    ) -> None:
        self._manager.update_governance_outcome(
            date=date,
            outcome=outcome,
            athlete_id=athlete_id,
        )

    def get_governance_decisions(self, limit: int = 1000) -> list[dict[str, Any]]:
        return self._manager.get_governance_decisions(limit=limit)

    def annotate_governance_outcome(self, date: str, note: str) -> bool:
        return self._manager.annotate_governance_outcome(date=date, note=note)

    def record_sync_outcome(
        self,
        source: str,
        success: bool,
        *,
        error_msg: str | None = None,
        records_synced: int = 0,
    ) -> None:
        self._manager.record_sync_outcome(
            source=source,
            success=success,
            error_msg=error_msg,
            records_synced=records_synced,
        )

    def get_last_sync_outcome(self, source: str) -> dict[str, Any] | None:
        return self._manager.get_last_sync_outcome(source=source)

    def get_last_garmin_sync_timestamp(self) -> datetime | None:
        return self._manager.get_last_garmin_sync_timestamp()

    def backup_database(self, backup_dir: Any = None, keep: int = 30) -> Any:
        return self._manager.backup_database(backup_dir=backup_dir, keep=keep)

    def transaction(self) -> AbstractContextManager:
        return self._manager.transaction()

    def close(self) -> None:
        self._manager.close()


class PostgreSQLAdapter(PersistenceAdapter):
    """PostgreSQL persistence adapter backed by ``PostgreSQLDatabaseManager``."""

    _UNSUPPORTED_MESSAGE = (
        "PostgreSQL backend method is not implemented in PostgreSQLDatabaseManager"
    )

    def __init__(
        self,
        dsn: str,
        manager: PostgreSQLDatabaseManager | None = None,
    ) -> None:
        self._manager = manager or PostgreSQLDatabaseManager(dsn=dsn)

    def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self._manager, method_name, None)
        if not callable(method):
            raise NotImplementedError(f"{self._UNSUPPORTED_MESSAGE}: {method_name}")
        return method(*args, **kwargs)

    def save_daily_metric(self, date: str, **kwargs: Any) -> None:
        self._call("save_daily_metric", date, **kwargs)

    def get_baseline_rhr(self, days: int = 7) -> float | None:
        return self._call("get_baseline_rhr", days=days)

    def get_hrv_history(self, days: int = 14) -> list[tuple[str, float]]:
        return self._call("get_hrv_history", days=days)

    def get_weight_history(self, days: int = 30) -> list[tuple[str, float]]:
        return self._call("get_weight_history", days=days)

    def save_session(
        self,
        date: str,
        session_type: str,
        distance_km: float,
        duration_sec: int,
        **kwargs: Any,
    ) -> None:
        self._call(
            "save_session",
            date,
            session_type,
            distance_km,
            duration_sec,
            **kwargs,
        )

    def get_training_load_history(
        self, days: int | None = None
    ) -> list[tuple[str, float]]:
        return self._call("get_training_load_history", days=days)

    def get_ctl_atl_tsb(self) -> tuple[float, float, float]:
        return self._call("get_ctl_atl_tsb")

    def add_shoe(
        self, name: str, shoe_type: str = "DAILY", max_km: int = 800
    ) -> int:
        return self._call("add_shoe", name=name, shoe_type=shoe_type, max_km=max_km)

    def get_active_shoes(self) -> list[tuple]:
        return self._call("get_active_shoes")

    def check_shoe_availability(self, shoe_id: int) -> tuple[bool, str]:
        return self._call("check_shoe_availability", shoe_id=shoe_id)

    def update_shoe_mileage(
        self, shoe_id: int, distance_km: float, date: str
    ) -> None:
        self._call(
            "update_shoe_mileage",
            shoe_id=shoe_id,
            distance_km=distance_km,
            date=date,
        )

    def save_personal_best(
        self,
        distance_km: float,
        time_seconds: int,
        date: str,
        *,
        race_name: str | None = None,
        notes: str | None = None,
    ) -> None:
        self._call(
            "save_personal_best",
            distance_km=distance_km,
            time_seconds=time_seconds,
            date=date,
            race_name=race_name,
            notes=notes,
        )

    def get_pr(
        self, distance_km: float
    ) -> tuple[int, str, str | None] | None:
        return self._call("get_pr", distance_km=distance_km)

    def save_hrr(self, date: str, hrr_60: int, hrr_120: int = 0) -> None:
        self._call("save_hrr", date=date, hrr_60=hrr_60, hrr_120=hrr_120)

    def get_hrr_history(self, days: int = 28) -> list[tuple[str, int, int]]:
        return self._call("get_hrr_history", days=days)

    def update_glycogen_debt(self, date: str, debt_score: float) -> None:
        self._call("update_glycogen_debt", date=date, debt_score=debt_score)

    def log_cs_performance(
        self,
        date: str,
        critical_speed: float,
        w_prime: float,
        *,
        notes: str | None = None,
    ) -> None:
        self._call(
            "log_cs_performance",
            date=date,
            critical_speed=critical_speed,
            w_prime=w_prime,
            notes=notes,
        )

    def get_cs_performances(self, limit: int = 10) -> list[tuple[str, float, float]]:
        return self._call("get_cs_performances", limit=limit)

    def log_override(
        self,
        date: str,
        original_recommendation: str,
        override_reason: str,
        *,
        athlete_id: str = "default",
    ) -> None:
        self._call(
            "log_override",
            date=date,
            original_recommendation=original_recommendation,
            override_reason=override_reason,
            athlete_id=athlete_id,
        )

    def record_override_signal(
        self,
        date: str,
        signal: str,
        *,
        athlete_id: str = "default",
    ) -> None:
        self._call(
            "record_override_signal",
            date=date,
            signal=signal,
            athlete_id=athlete_id,
        )

    def get_override_ratio(self, days: int = 14) -> float:
        return self._call("get_override_ratio", days=days)

    def get_override_log(self, limit: int = 50) -> list[dict[str, str]]:
        return self._call("get_override_log", limit=limit)

    def save_governance_decision(self, decision: dict[str, Any]) -> None:
        self._call("save_governance_decision", decision=decision)

    def update_governance_outcome(
        self,
        date: str,
        outcome: dict[str, Any],
        *,
        athlete_id: str = "default",
    ) -> None:
        self._call(
            "update_governance_outcome",
            date=date,
            outcome=outcome,
            athlete_id=athlete_id,
        )

    def get_governance_decisions(self, limit: int = 1000) -> list[dict[str, Any]]:
        return self._call("get_governance_decisions", limit=limit)

    def annotate_governance_outcome(self, date: str, note: str) -> bool:
        return self._call("annotate_governance_outcome", date=date, note=note)

    def record_sync_outcome(
        self,
        source: str,
        success: bool,
        *,
        error_msg: str | None = None,
        records_synced: int = 0,
    ) -> None:
        self._call(
            "record_sync_outcome",
            source=source,
            success=success,
            error_msg=error_msg,
            records_synced=records_synced,
        )

    def get_last_sync_outcome(self, source: str) -> dict[str, Any] | None:
        return self._call("get_last_sync_outcome", source=source)

    def get_last_garmin_sync_timestamp(self) -> datetime | None:
        return self._call("get_last_garmin_sync_timestamp")

    def backup_database(self, backup_dir: Any = None, keep: int = 30) -> Any:
        return self._call("backup_database", backup_dir=backup_dir, keep=keep)

    def transaction(self) -> AbstractContextManager:
        return self._call("transaction")

    def close(self) -> None:
        self._call("close")

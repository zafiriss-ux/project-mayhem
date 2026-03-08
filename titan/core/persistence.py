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

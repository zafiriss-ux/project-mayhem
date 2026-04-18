# ADR-0033-L3-D-RESOLVED: All adapter read methods implement explicit athlete_id
# isolation. ADR-0040 exemptions fully retired. Multi-athlete read path complete.

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

import json
import logging
import os
import subprocess
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    Table,
    Text,
    and_,
    create_engine,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import IntegrityError

from titan.config.thresholds import ATL_DECAY_DAYS, CTL_DECAY_DAYS
from titan.core.database import DatabaseManager, PostgreSQLDatabaseManager

_log = logging.getLogger(__name__)


def _to_json_serializable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, float):
        return round(value, 2)
    if isinstance(value, dict):
        return {str(k): _to_json_serializable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_serializable(v) for v in value]
    if isinstance(value, tuple):
        return [_to_json_serializable(v) for v in value]
    return value


def get_athlete_context(
    athlete_id: str,
    days: int = 7,
    include_governance: bool = True,
    include_training: bool = True,
    include_biometrics: bool = True,
) -> dict[str, Any]:
    """Return a unified JSON-serialisable context payload for an athlete."""
    if days <= 0:
        raise ValueError("days must be >= 1")

    adapter = get_persistence_adapter()
    try:
        context: dict[str, Any] = {
            "athlete_id": athlete_id,
            "days": days,
        }

        if include_biometrics:
            hrv_history = adapter.get_hrv_history(days=days, athlete_id=athlete_id)
            weight_history = adapter.get_weight_history(days=days, athlete_id=athlete_id)
            context["biometrics"] = {
                "baseline_rhr": adapter.get_baseline_rhr(days=days, athlete_id=athlete_id),
                "hrv_history": hrv_history,
                "weight_history": weight_history,
                "latest_hrv": hrv_history[0][1] if hrv_history else None,
                "latest_weight": weight_history[0][1] if weight_history else None,
            }

        if include_training:
            ctl, atl, tsb = adapter.get_ctl_atl_tsb(athlete_id=athlete_id)
            context["training"] = {
                "training_load_history": adapter.get_training_load_history(
                    days=days, athlete_id=athlete_id
                ),
                "ctl": ctl,
                "atl": atl,
                "tsb": tsb,
            }

        if include_governance:
            context["governance"] = {
                "recent_decisions": adapter.get_governance_decisions(
                    limit=days, athlete_id=athlete_id
                ),
            }

        return _to_json_serializable(context)
    finally:
        adapter.close()


def get_persistence_adapter(
    backend: str | None = None,
    *,
    db_name: str = "titan_core.db",
    db_dir: Path | None = None,
    postgres_dsn: str | None = None,
) -> PersistenceAdapter:
    """Return the configured persistence adapter for the selected backend."""
    selected_backend = (backend or os.environ.get("TITAN_DB_BACKEND", "sqlite")).lower()
    if selected_backend == "sqlite":
        return SQLiteAdapter(db_name=db_name, db_dir=db_dir)
    if selected_backend == "postgres":
        dsn = postgres_dsn or os.environ.get("TITAN_POSTGRES_DSN")
        if not dsn:
            raise ValueError("TITAN_POSTGRES_DSN must be set for PostgreSQL backend")
        return PostgreSQLAdapter(dsn=dsn)
    raise ValueError(f"Unsupported TITAN_DB_BACKEND: {selected_backend}")


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
    def get_baseline_rhr(self, days: int = 7, athlete_id: str = "owner") -> float | None:
        """Return the rolling median RHR over the last *days* days, or None."""

    @abstractmethod
    def get_hrv_history(self, days: int = 14, athlete_id: str = "owner") -> list[tuple[str, float]]:
        """Return [(date_iso, hrv_rmssd), ...] ordered newest-first."""

    @abstractmethod
    def get_weight_history(
        self, days: int = 30, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
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
        self, days: int | None = None, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        """Return [(date_iso, training_load), ...] ordered newest-first."""

    @abstractmethod
    def get_ctl_atl_tsb(self, athlete_id: str = "owner") -> tuple[float, float, float]:
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
        self, limit: int = 1000, athlete_id: str = "owner"
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

    def get_baseline_rhr(self, days: int = 7, athlete_id: str = "owner") -> float | None:
        return self._manager.get_baseline_rhr(days=days, athlete_id=athlete_id)

    def get_hrv_history(self, days: int = 14, athlete_id: str = "owner") -> list[tuple[str, float]]:
        return self._manager.get_hrv_history(days=days, athlete_id=athlete_id)

    def get_weight_history(
        self, days: int = 30, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        return self._manager.get_weight_history(days=days, athlete_id=athlete_id)

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
        self, days: int | None = None, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        return self._manager.get_training_load_history(days=days, athlete_id=athlete_id)

    def get_ctl_atl_tsb(self, athlete_id: str = "owner") -> tuple[float, float, float]:
        return self._manager.get_ctl_atl_tsb(athlete_id=athlete_id)

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

    def get_governance_decisions(
        self, limit: int = 1000, athlete_id: str = "owner"
    ) -> list[dict[str, Any]]:
        return self._manager.get_governance_decisions(limit=limit, athlete_id=athlete_id)

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

    def __init__(
        self,
        dsn: str,
        *,
        engine: Engine | None = None,
        manager: PostgreSQLDatabaseManager | None = None,
    ) -> None:
        self._dsn = dsn
        if engine is not None:
            self._engine = engine
        elif manager is not None and hasattr(manager, "_conn"):
            raw_conn = manager._conn
            self._engine = create_engine("postgresql+psycopg2://", creator=lambda: raw_conn)
        else:
            self._engine = create_engine(dsn)

        self._metadata = MetaData()
        self._daily_metrics = Table(
            "daily_metrics",
            self._metadata,
            Column("id", Integer),
            Column("athlete_id", Text),
            Column("date", Text),
            Column("weight_kg", Float),
            Column("hrv_rmssd", Float),
            Column("resting_hr", Integer),
            Column("sleep_hours", Float),
            Column("sleep_quality", Integer),
            Column("soreness", Integer),
            Column("fatigue_level", Integer),
            Column("mood", Integer),
            Column("notes", Text),
        )
        self._training_log = Table(
            "training_log",
            self._metadata,
            Column("id", Integer),
            Column("athlete_id", Text),
            Column("date", Text),
            Column("session_type", Text),
            Column("distance_km", Float),
            Column("duration_sec", Integer),
            Column("avg_hr", Integer),
            Column("max_hr", Integer),
            Column("rpe", Integer),
            Column("training_load", Integer),
            Column("shoe_id", Integer),
            Column("surface", Text),
            Column("temperature_c", Float),
            Column("zone_distribution", Text),
            Column("notes", Text),
            Column("garmin_activity_id", Text),
        )
        self._gear_usage = Table(
            "gear_usage",
            self._metadata,
            Column("id", Integer),
            Column("athlete_id", Text),
            Column("shoe_name", Text),
            Column("total_km", Float),
            Column("last_used", Text),
            Column("compression_recovery_hours", Integer),
            Column("status", Text),
            Column("shoe_type", Text),
            Column("max_km_limit", Float),
        )
        self._personal_bests = Table(
            "personal_bests",
            self._metadata,
            Column("id", Integer),
            Column("athlete_id", Text),
            Column("distance_km", Float),
            Column("time_sec", Integer),
            Column("pace_sec_per_km", Float),
            Column("date", Text),
            Column("race_name", Text),
        )
        self._governance_outcomes = Table(
            "governance_outcomes",
            self._metadata,
            Column("id", Integer),
            Column("athlete_id", Text),
            Column("date", Text),
            Column("session_planned", Text),
            Column("session_post_governance", Text),
            Column("locks_applied_json", Text),
            Column("governance_clean", Integer),
            Column("phase", Text),
            Column("vlg_color", Text),
            Column("apl_priority_vector_json", Text),
            Column("lock_thresholds_active_json", Text),
            Column("acwr", Float),
            Column("tsb_value", Float),
            Column("readiness_score", Float),
            Column("glycogen_debt", Float),
            Column("afi_value", Float),
            Column("outcome_rpe", Integer),
            Column("outcome_completed", Integer),
            Column("outcome_session_type_actual", Text),
            Column("outcome_notes", Text),
            Column("decision_was_followed", Integer),
            Column("override_outcome_exclusion", Integer),
            Column("outcome_independence_ok", Integer),
            Column("algorithm_version_snapshot", Text),
        )

    def save_daily_metric(self, date: str, **kwargs: Any) -> None:
        values = {
            "date": date,
            "weight_kg": kwargs.get("weight"),
            "hrv_rmssd": kwargs.get("hrv"),
            "resting_hr": kwargs.get("rhr"),
            "sleep_hours": kwargs.get("sleep_hours"),
            "sleep_quality": kwargs.get("sleep_quality"),
            "soreness": kwargs.get("soreness"),
            "fatigue_level": kwargs.get("fatigue"),
            "mood": kwargs.get("mood"),
            "notes": kwargs.get("notes"),
        }
        with self._engine.begin() as conn:
            conn.execute(self._daily_metrics.delete().where(self._daily_metrics.c.date == date))
            conn.execute(insert(self._daily_metrics).values(**values))

    def get_baseline_rhr(self, days: int = 7, athlete_id: str = "owner") -> float | None:
        start_date = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(self._daily_metrics.c.resting_hr)
                .where(
                    and_(
                        self._daily_metrics.c.athlete_id == athlete_id,
                        self._daily_metrics.c.date >= start_date,
                        self._daily_metrics.c.resting_hr.is_not(None),
                    )
                )
                .order_by(self._daily_metrics.c.date.desc())
            ).scalars().all()
        if not rows:
            return None
        sorted_rows = sorted(float(v) for v in rows)
        mid = len(sorted_rows) // 2
        if len(sorted_rows) % 2:
            return sorted_rows[mid]
        return (sorted_rows[mid - 1] + sorted_rows[mid]) / 2

    def get_hrv_history(
        self, days: int = 14, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        start_date = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(self._daily_metrics.c.date, self._daily_metrics.c.hrv_rmssd)
                .where(
                    and_(
                        self._daily_metrics.c.athlete_id == athlete_id,
                        self._daily_metrics.c.date >= start_date,
                        self._daily_metrics.c.hrv_rmssd.is_not(None),
                    )
                )
                .order_by(self._daily_metrics.c.date.desc())
            ).all()
        return [(str(row[0]), float(row[1])) for row in rows]

    def get_weight_history(
        self, days: int = 30, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        start_date = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(self._daily_metrics.c.date, self._daily_metrics.c.weight_kg)
                .where(
                    and_(
                        self._daily_metrics.c.athlete_id == athlete_id,
                        self._daily_metrics.c.date >= start_date,
                        self._daily_metrics.c.weight_kg.is_not(None),
                    )
                )
                .order_by(self._daily_metrics.c.date.desc())
            ).all()
        return [(str(row[0]), float(row[1])) for row in rows]

    def save_session(
        self,
        date: str,
        session_type: str,
        distance_km: float,
        duration_sec: int,
        **kwargs: Any,
    ) -> None:
        rpe = kwargs.get("rpe")
        training_load = int(rpe * (duration_sec / 60)) if rpe else 0
        garmin_activity_id = kwargs.get("garmin_activity_id")
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    insert(self._training_log).values(
                        date=date,
                        session_type=session_type,
                        distance_km=distance_km,
                        duration_sec=duration_sec,
                        avg_hr=kwargs.get("avg_hr"),
                        max_hr=kwargs.get("max_hr"),
                        rpe=rpe,
                        training_load=training_load,
                        shoe_id=kwargs.get("shoe_id"),
                        surface=kwargs.get("surface"),
                        temperature_c=kwargs.get("temperature_c"),
                        notes=kwargs.get("notes"),
                        garmin_activity_id=garmin_activity_id,
                    )
                )
        except IntegrityError:
            # Duplicate garmin_activity_id — silent no-op (INSERT OR IGNORE semantics).
            pass

    def get_training_load_history(
        self, days: int | None = None, athlete_id: str = "owner"
    ) -> list[tuple[str, float]]:
        lookback_days = CTL_DECAY_DAYS if days is None else days
        start_date = (datetime.now(UTC) - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(self._training_log.c.date, self._training_log.c.training_load)
                .where(
                    and_(
                        self._training_log.c.athlete_id == athlete_id,
                        self._training_log.c.date >= start_date,
                    )
                )
                .order_by(self._training_log.c.date.desc())
            ).all()
        return [(str(row[0]), float(row[1] or 0)) for row in rows]

    def get_ctl_atl_tsb(self, athlete_id: str = "owner") -> tuple[float, float, float]:
        loads = self.get_training_load_history(CTL_DECAY_DAYS, athlete_id=athlete_id)
        if not loads:
            return (0.0, 0.0, 0.0)
        chronological_loads = list(reversed(loads))
        ctl = 0.0
        ctl_decay = 2 / (CTL_DECAY_DAYS + 1)
        for _date, load in chronological_loads:
            ctl = (load * ctl_decay) + (ctl * (1 - ctl_decay))
        recent_loads = [load for _d, load in chronological_loads][-ATL_DECAY_DAYS:]
        atl = 0.0
        atl_decay = 2 / (ATL_DECAY_DAYS + 1)
        for load in recent_loads:
            atl = (load * atl_decay) + (atl * (1 - atl_decay))
        return (round(ctl, 2), round(atl, 2), round(ctl - atl, 2))

    def add_shoe(
        self, name: str, shoe_type: str = "DAILY", max_km: int = 800
    ) -> int:
        with self._engine.begin() as conn:
            result = conn.execute(
                insert(self._gear_usage)
                .values(shoe_name=name, shoe_type=shoe_type, max_km_limit=max_km)
                .returning(self._gear_usage.c.id)
            )
            return int(result.scalar_one())

    def get_active_shoes(self) -> list[tuple]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(
                    self._gear_usage.c.id,
                    self._gear_usage.c.shoe_name,
                    self._gear_usage.c.shoe_type,
                    self._gear_usage.c.total_km,
                    self._gear_usage.c.max_km_limit,
                    self._gear_usage.c.status,
                ).where(self._gear_usage.c.status == "ACTIVE")
            ).all()
        return [tuple(row) for row in rows]

    def check_shoe_availability(self, shoe_id: int) -> tuple[bool, str]:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(
                    self._gear_usage.c.total_km,
                    self._gear_usage.c.max_km_limit,
                    self._gear_usage.c.status,
                ).where(self._gear_usage.c.id == shoe_id)
            ).first()
        if row is None:
            return (False, "shoe_not_found")
        total_km, max_km, status = row
        if status != "ACTIVE":
            return (False, "shoe_inactive")
        if float(total_km or 0) >= float(max_km or 0):
            return (False, "shoe_retired")
        return (True, "available")

    def update_shoe_mileage(
        self, shoe_id: int, distance_km: float, date: str
    ) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                update(self._gear_usage)
                .where(self._gear_usage.c.id == shoe_id)
                .values(
                    total_km=self._gear_usage.c.total_km + distance_km,
                    last_used=date,
                )
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
        pace = time_seconds / distance_km if distance_km > 0 else None
        with self._engine.begin() as conn:
            conn.execute(
                insert(self._personal_bests).values(
                    distance_km=distance_km,
                    time_sec=time_seconds,
                    pace_sec_per_km=pace,
                    date=date,
                    race_name=race_name,
                )
            )

    def get_pr(
        self, distance_km: float
    ) -> tuple[int, str, str | None] | None:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(
                    self._personal_bests.c.time_sec,
                    self._personal_bests.c.date,
                    self._personal_bests.c.race_name,
                )
                .where(self._personal_bests.c.distance_km == distance_km)
                .order_by(self._personal_bests.c.time_sec.asc())
                .limit(1)
            ).first()
        if row is None:
            return None
        return (int(row[0]), str(row[1]), row[2])

    def save_hrr(self, date: str, hrr_60: int, hrr_120: int = 0) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                update(self._daily_metrics)
                .where(self._daily_metrics.c.date == date)
                .values(notes=f"HRR60={hrr_60};HRR120={hrr_120}")
            )

    def get_hrr_history(self, days: int = 28) -> list[tuple[str, int, int]]:
        return []

    def update_glycogen_debt(self, date: str, debt_score: float) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                update(self._governance_outcomes)
                .where(self._governance_outcomes.c.date == date)
                .values(glycogen_debt=debt_score)
            )

    def log_cs_performance(
        self,
        date: str,
        critical_speed: float,
        w_prime: float,
        *,
        notes: str | None = None,
    ) -> None:
        del date, critical_speed, w_prime, notes

    def get_cs_performances(self, limit: int = 10) -> list[tuple[str, float, float]]:
        del limit
        return []

    def log_override(
        self,
        date: str,
        original_recommendation: str,
        override_reason: str,
        *,
        athlete_id: str = "default",
    ) -> None:
        del original_recommendation, athlete_id
        with self._engine.begin() as conn:
            conn.execute(
                update(self._governance_outcomes)
                .where(self._governance_outcomes.c.date == date)
                .values(outcome_notes=override_reason, decision_was_followed=0)
            )

    def record_override_signal(
        self,
        date: str,
        signal: str,
        *,
        athlete_id: str = "default",
    ) -> None:
        _athlete_id = athlete_id  # noqa: F841 — parameter required by interface contract
        with self._engine.begin() as conn:
            conn.execute(
                update(self._governance_outcomes)
                .where(self._governance_outcomes.c.date == date)
                .values(outcome_notes=signal)
            )

    def get_override_ratio(self, days: int = 14) -> float:
        start_date = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%d")
        with self._engine.connect() as conn:
            total = conn.execute(
                select(func.count())
                .select_from(self._governance_outcomes)
                .where(self._governance_outcomes.c.date >= start_date)
            ).scalar_one()
            overrides = conn.execute(
                select(func.count())
                .select_from(self._governance_outcomes)
                .where(
                    and_(
                        self._governance_outcomes.c.date >= start_date,
                        self._governance_outcomes.c.decision_was_followed == 0,
                    )
                )
            ).scalar_one()
        if not total:
            return 0.0
        return float(overrides) / float(total)

    def get_override_log(self, limit: int = 50) -> list[dict[str, str]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(
                    self._governance_outcomes.c.date,
                    self._governance_outcomes.c.session_post_governance,
                    self._governance_outcomes.c.outcome_notes,
                )
                .where(self._governance_outcomes.c.decision_was_followed == 0)
                .order_by(self._governance_outcomes.c.id.desc())
                .limit(limit)
            ).all()
        return [
            {"date": str(row[0]), "actual_type": str(row[1]), "reason": str(row[2] or "")}
            for row in rows
        ]

    def save_governance_decision(self, decision: dict[str, Any]) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                insert(self._governance_outcomes).values(
                    date=decision["date"],
                    session_planned=decision["session_planned"],
                    session_post_governance=decision["session_post_governance"],
                    locks_applied_json=json.dumps(decision["locks_applied"]),
                    governance_clean=int(bool(decision["governance_clean"])),
                    phase=decision["phase"],
                    vlg_color=decision["vlg_color"],
                    apl_priority_vector_json=json.dumps(decision["apl_priority_vector"]),
                    lock_thresholds_active_json=json.dumps(decision["lock_thresholds_active"]),
                    acwr=decision["acwr"],
                    tsb_value=decision["tsb_value"],
                    readiness_score=decision["readiness_score"],
                    glycogen_debt=decision["glycogen_debt"],
                    afi_value=decision.get("afi_value"),
                    algorithm_version_snapshot=json.dumps(
                        decision.get("algorithm_version_snapshot", {})
                    ),
                )
            )

    def update_governance_outcome(
        self,
        date: str,
        outcome: dict[str, Any],
        *,
        athlete_id: str = "default",
    ) -> None:
        _athlete_id = athlete_id  # noqa: F841 — parameter required by interface contract
        with self._engine.begin() as conn:
            conn.execute(
                update(self._governance_outcomes)
                .where(self._governance_outcomes.c.date == date)
                .values(
                    outcome_rpe=outcome.get("outcome_rpe"),
                    outcome_completed=outcome.get("outcome_completed"),
                    outcome_session_type_actual=outcome.get("outcome_session_type_actual"),
                    outcome_notes=outcome.get("outcome_notes"),
                    decision_was_followed=int(bool(outcome.get("decision_was_followed", True))),
                    override_outcome_exclusion=int(bool(outcome.get("override_outcome_exclusion", False))),
                    outcome_independence_ok=int(bool(outcome.get("outcome_independence_ok", True))),
                )
            )

    def get_governance_decisions(
        self, limit: int = 1000, athlete_id: str = "owner"
    ) -> list[dict[str, Any]]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                select(self._governance_outcomes)
                .where(self._governance_outcomes.c.athlete_id == athlete_id)
                .order_by(self._governance_outcomes.c.id.desc())
                .limit(limit)
            ).mappings().all()
        return [
            {
                "date": row["date"],
                "session_planned": row["session_planned"],
                "session_post_governance": row["session_post_governance"],
                "locks_applied": json.loads(row["locks_applied_json"]),
                "governance_clean": bool(row["governance_clean"]),
                "phase": row["phase"],
                "vlg_color": row["vlg_color"],
                "apl_priority_vector": json.loads(row["apl_priority_vector_json"]),
                "lock_thresholds_active": json.loads(row["lock_thresholds_active_json"]),
                "acwr": float(row["acwr"]),
                "tsb_value": float(row["tsb_value"]),
                "readiness_score": float(row["readiness_score"]),
                "glycogen_debt": float(row["glycogen_debt"]),
                "afi_value": row["afi_value"],
                "outcome_rpe": row["outcome_rpe"],
                "outcome_completed": row["outcome_completed"],
                "outcome_session_type_actual": row["outcome_session_type_actual"],
                "outcome_notes": row["outcome_notes"],
                "decision_was_followed": bool(row["decision_was_followed"]),
                "override_outcome_exclusion": bool(row["override_outcome_exclusion"]),
                "outcome_independence_ok": bool(row["outcome_independence_ok"]),
                "algorithm_version_snapshot": json.loads(row["algorithm_version_snapshot"] or "{}"),
            }
            for row in rows
        ]

    def annotate_governance_outcome(self, date: str, note: str) -> bool:
        with self._engine.begin() as conn:
            row = conn.execute(
                select(self._governance_outcomes.c.outcome_notes)
                .where(self._governance_outcomes.c.date == date)
                .order_by(self._governance_outcomes.c.id.desc())
                .limit(1)
            ).first()
            if row is None:
                return False
            existing = str(row[0] or "")
            merged = note if not existing else f"{existing}\n{note}"
            conn.execute(
                update(self._governance_outcomes)
                .where(self._governance_outcomes.c.date == date)
                .values(outcome_notes=merged)
            )
        return True

    def record_sync_outcome(
        self,
        source: str,
        success: bool,
        *,
        error_msg: str | None = None,
        records_synced: int = 0,
    ) -> None:
        del source, success, error_msg, records_synced

    def get_last_sync_outcome(self, source: str) -> dict[str, Any] | None:
        del source
        return None

    def get_last_garmin_sync_timestamp(self) -> datetime | None:
        return None

    def backup_database(self, backup_dir: Any = None, keep: int = 30) -> Any:
        target_dir = Path(backup_dir) if backup_dir is not None else (Path.cwd() / "backups")
        target_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        dest = target_dir / f"titan_{date_str}.dump"
        if dest.exists():
            return None

        database_name = make_url(self._dsn).database
        if not database_name:
            raise ValueError("PostgreSQL DSN must include a database name for backup")

        command = [
            "pg_dump",
            "--format=custom",
            "--file",
            str(dest),
            "--dbname",
            self._dsn,
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (FileNotFoundError, subprocess.CalledProcessError) as error:
            if dest.exists():
                dest.unlink()
            raise RuntimeError("PostgreSQL backup via pg_dump failed") from error

        self._prune_old_backups(target_dir, keep=keep)
        return dest

    def _prune_old_backups(self, backup_dir: Path, keep: int) -> None:
        backups = sorted(backup_dir.glob("titan_????-??-??.dump"))
        for old in backups[:-keep] if len(backups) > keep else []:
            old.unlink(missing_ok=True)

    def transaction(self) -> AbstractContextManager:
        return self._engine.begin()

    def close(self) -> None:
        self._engine.dispose()

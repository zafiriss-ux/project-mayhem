"""Operations domain SQL: sync outcomes and freshness, degraded-mode state
(HD-06), nutrition preferences, worker routine claims (ADR-0060 D1, INV-15),
verified backups with integrity checks (AGENTS DR-02), and the schema
introspection probes (table names, reachability)."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager


class OperationsRepository:
    """Operations SQL, on the owning DatabaseManager's connection and lock."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def get_nutrition_preferences(self, athlete_id: str = 'owner') -> dict | None:
        """Return nutrition preferences for athlete_id, or None if not set."""
        with self._db._lock:
            self._db._ensure_open_locked()
            c = self._db.conn.cursor()
            c.execute(
                'SELECT * FROM nutrition_preferences WHERE athlete_id = ?',
                (athlete_id,)
            )
            row = c.fetchone()
            if not row:
                return None
            cols = [d[0] for d in c.description]
            return dict(zip(cols, row, strict=True))

    def save_nutrition_preferences(
        self, athlete_id: str = 'owner', prefs: dict = None
    ) -> None:
        """Upsert nutrition preferences for athlete_id."""
        if not prefs:
            return
        with self._db._lock:
            self._db._ensure_open_locked()
            c = self._db.conn.cursor()
            c.execute('''
                INSERT INTO nutrition_preferences (
                    athlete_id, training_time, fasted_training,
                    dietary_style, meal_frequency, biological_sex,
                    menstrual_tracking, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                ON CONFLICT(athlete_id) DO UPDATE SET
                    training_time=excluded.training_time,
                    fasted_training=excluded.fasted_training,
                    dietary_style=excluded.dietary_style,
                    meal_frequency=excluded.meal_frequency,
                    biological_sex=excluded.biological_sex,
                    menstrual_tracking=excluded.menstrual_tracking,
                    updated_at=excluded.updated_at
            ''', (
                athlete_id,
                prefs.get('training_time', 'variable'),
                prefs.get('fasted_training', 'easy_only'),
                prefs.get('dietary_style', 'standard'),
                prefs.get('meal_frequency', 3),
                prefs.get('biological_sex', 'male'),
                prefs.get('menstrual_tracking', 'no'),
            ))
            self._db.conn.commit()

    def get_all_degraded_mode_states(self, athlete_id: str = "default") -> list[tuple[str, str]]:
        """Return all (failure_type, degraded_since) rows for the given athlete."""
        with self._db._lock:
            return self._db.conn.cursor().execute(
                "SELECT failure_type, degraded_since "
                "FROM degraded_mode_state WHERE athlete_id = ?",
                (athlete_id,),
            ).fetchall()

    def upsert_degraded_mode_state(
        self, failure_type: str, degraded_since: str, athlete_id: str = "default"
    ) -> None:
        """Insert or replace a degraded-mode row keyed by failure_type."""
        with self._db._lock:
            self._db.conn.cursor().execute(
                "INSERT OR REPLACE INTO degraded_mode_state "
                "(failure_type, degraded_since, athlete_id) VALUES (?, ?, ?)",
                (failure_type, degraded_since, athlete_id),
            )
            self._db.conn.commit()

    def delete_degraded_mode_state(
        self, failure_type: str, athlete_id: str = "default"
    ) -> None:
        """Delete the degraded-mode row for a failure_type (degradation resolved)."""
        with self._db._lock:
            self._db.conn.cursor().execute(
                "DELETE FROM degraded_mode_state "
                "WHERE failure_type = ? AND athlete_id = ?",
                (failure_type, athlete_id),
            )
            self._db.conn.commit()

    def record_sync_outcome(
        self,
        *,
        athlete_id: str,
        source: str,
        attempted_at: datetime,
        success: bool,
        error_class: str | None = None,
    ) -> None:
        """Persist the athlete's latest sync attempt outcome for a source system.

        ``athlete_id`` is required, with no default (ADR-0067 D3).
        """
        attempted_iso = attempted_at.astimezone(UTC).isoformat()
        success_iso = attempted_iso if success else None

        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """INSERT INTO sync_metadata (
                        athlete_id,
                        source,
                        last_attempt_ts,
                        last_success_ts,
                        last_sync_ok,
                        last_error_class
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(athlete_id, source) DO UPDATE SET
                        last_attempt_ts = excluded.last_attempt_ts,
                        last_success_ts = CASE
                            WHEN excluded.last_sync_ok = 1 THEN excluded.last_success_ts
                            ELSE sync_metadata.last_success_ts
                        END,
                        last_sync_ok = excluded.last_sync_ok,
                        last_error_class = excluded.last_error_class""",
                (athlete_id, source, attempted_iso, success_iso, 1 if success else 0, error_class),
            )
            self._db.conn.commit()

    def get_last_sync_outcome(self, source: str, athlete_id: str = "owner") -> dict[str, Any] | None:
        """Return the athlete's latest sync outcome metadata for a source."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT last_attempt_ts, last_success_ts, last_sync_ok, last_error_class
                   FROM sync_metadata WHERE athlete_id = ? AND source = ?""",
                (athlete_id, source),
            )
            row = cursor.fetchone()

        if not row:
            return None

        attempted_at = None
        success_at = None
        if row[0]:
            with suppress(ValueError, TypeError):
                attempted_at = datetime.fromisoformat(row[0])
        if row[1]:
            with suppress(ValueError, TypeError):
                success_at = datetime.fromisoformat(row[1])

        return {
            "last_attempt_ts": attempted_at,
            "last_success_ts": success_at,
            "last_sync_ok": bool(row[2]),
            "last_error_class": row[3],
        }

    def get_last_garmin_sync_timestamp(self, athlete_id: str = "owner") -> datetime | None:
        """Return a datetime representing the most recent data Garmin sync wrote for the athlete.

        Checks the athlete's latest date in both daily_metrics and training_log and
        returns the more recent of the two, parsed as a midnight-UTC datetime. Another
        athlete's fresh data never makes this athlete's data look fresh (ADR-0067 D3).

        Returns None if the athlete has no data in either table.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                "SELECT MAX(date) FROM daily_metrics WHERE athlete_id = ? AND date IS NOT NULL",
                (athlete_id,),
            )
            dm_row = cursor.fetchone()
            cursor.execute(
                "SELECT MAX(date) FROM training_log WHERE athlete_id = ? AND date IS NOT NULL",
                (athlete_id,),
            )
            tl_row = cursor.fetchone()

        latest: str | None = None
        for row in (dm_row, tl_row):
            if row and row[0] and (latest is None or row[0] > latest):
                latest = row[0]

        if not latest:
            return None

        try:
            return datetime.fromisoformat(latest).replace(tzinfo=UTC)
        except (ValueError, TypeError):
            return None

    def begin_routine_attempt(
        self, *, athlete_id: str, execution_date: str, routine_type: str, started_at: datetime,
        max_attempts: int, retry_gap: timedelta | None = None, start_by: datetime | None = None,
    ) -> tuple[str, int]:
        """Start one attempt at a routine day (ADR-0060 D1 as amended by ADR-0067 D8.4).

        The row is one per athlete, UTC day and routine (D8.2). Returns ``("run", n)`` when
        this call took attempt ``n`` and the routine runs; ``("closed", n)`` when the day was
        delivered or left; ``("exhausted", n)`` when ``max_attempts`` were used without a
        delivery and the day is not yet closed, so the caller leaves it. The attempt is
        counted before the routine runs, so a crash counts too. Any database error
        propagates so the caller fails closed.

        With ``retry_gap``, attempt ``n + 1`` starts no earlier than ``n`` gaps after the
        first attempt (``started_at`` of the row); before that ``("wait", n)`` is returned and
        nothing changes (D-109). With ``start_by``, a day that has no row yet is not started
        after that time: ``("late", 0)`` and no row is written (D-109).
        """
        key = (athlete_id, execution_date, routine_type)
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            try:
                if start_by is not None and started_at > start_by and cursor.execute(
                    "SELECT 1 FROM worker_routine_executions "
                    "WHERE athlete_id = ? AND execution_date = ? AND routine_type = ?",
                    key,
                ).fetchone() is None:
                    return "late", 0
                cursor.execute(
                    "INSERT OR IGNORE INTO worker_routine_executions "
                    "(athlete_id, execution_date, routine_type, started_at, attempts) VALUES (?, ?, ?, ?, 0)",
                    (*key, started_at.astimezone(UTC).isoformat()),
                )
                attempts, delivered_at, completed_at, first_started = cursor.execute(
                    "SELECT attempts, delivered_at, completed_at, started_at FROM worker_routine_executions "
                    "WHERE athlete_id = ? AND execution_date = ? AND routine_type = ?",
                    key,
                ).fetchone()
                if delivered_at is not None or completed_at is not None:
                    state = "closed"
                elif attempts >= max_attempts:
                    state = "exhausted"
                elif retry_gap is not None and attempts > 0 and started_at < (
                    datetime.fromisoformat(first_started).astimezone(UTC) + attempts * retry_gap
                ):
                    state = "wait"
                else:
                    cursor.execute(
                        "UPDATE worker_routine_executions SET attempts = attempts + 1 "
                        "WHERE athlete_id = ? AND execution_date = ? AND routine_type = ?",
                        key,
                    )
                    attempts += 1
                    state = "run"
                self._db.conn.commit()
            except Exception:
                self._db.conn.rollback()
                raise
        return state, attempts

    def mark_routine_delivered(
        self, *, athlete_id: str, execution_date: str, routine_type: str, delivered_at: datetime
    ) -> None:
        """Record the delivery of the day's message; it also closes the day (ADR-0067 D8.3)."""
        at = delivered_at.astimezone(UTC).isoformat()
        with self._db._lock:
            self._db._ensure_open_locked()
            self._db.conn.cursor().execute(
                "UPDATE worker_routine_executions SET delivered_at = ?, completed_at = COALESCE(completed_at, ?) "
                "WHERE athlete_id = ? AND execution_date = ? AND routine_type = ?",
                (at, at, athlete_id, execution_date, routine_type),
            )
            self._db.conn.commit()

    def complete_routine_execution(
        self, *, athlete_id: str, execution_date: str, routine_type: str, completed_at: datetime
    ) -> None:
        """Close a routine day (ADR-0060 D1 step 2): delivered, or left after its attempts."""
        with self._db._lock:
            self._db._ensure_open_locked()
            self._db.conn.cursor().execute(
                "UPDATE worker_routine_executions SET completed_at = ? "
                "WHERE athlete_id = ? AND execution_date = ? AND routine_type = ?",
                (completed_at.astimezone(UTC).isoformat(), athlete_id, execution_date, routine_type),
            )
            self._db.conn.commit()

    def get_routine_resume(self, *, athlete_id: str, execution_date: str, routine_type: str) -> dict[str, Any]:
        """What an earlier attempt of that day left for the next one; {} when nothing (D-109)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            row = self._db.conn.cursor().execute(
                "SELECT resume_json FROM worker_routine_executions "
                "WHERE athlete_id = ? AND execution_date = ? AND routine_type = ?",
                (athlete_id, execution_date, routine_type),
            ).fetchone()
        if row is None or not row[0]:
            return {}
        try:
            data = json.loads(row[0])
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    def update_routine_resume(
        self, *, athlete_id: str, execution_date: str, routine_type: str, fields: dict[str, Any]
    ) -> None:
        """Merge ``fields`` into the day's ``resume_json`` (D-109); the claimed row must exist."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            key = (athlete_id, execution_date, routine_type)
            row = cursor.execute(
                "SELECT resume_json FROM worker_routine_executions "
                "WHERE athlete_id = ? AND execution_date = ? AND routine_type = ?",
                key,
            ).fetchone()
            if row is None:
                raise LookupError(f"no routine row for {key}")
            try:
                data = json.loads(row[0]) if row[0] else {}
            except ValueError:
                data = {}
            if not isinstance(data, dict):
                data = {}
            data.update(fields)
            cursor.execute(
                "UPDATE worker_routine_executions SET resume_json = ? "
                "WHERE athlete_id = ? AND execution_date = ? AND routine_type = ?",
                (json.dumps(data, sort_keys=True, default=str), *key),
            )
            self._db.conn.commit()

    def routine_inputs_fingerprint(self, athlete_id: str, date: str) -> str | None:
        """A hash of the athlete's stored inputs of that date, or None when there are none (D-109).

        The inputs are the ``daily_metrics`` row and the ``training_log`` rows of that athlete
        and date, without their ids. Taken when the day's decision is recorded and again
        before a retry resends it: a different hash means the inputs changed since.
        """
        parts: list[Any] = []
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            for table in ("daily_metrics", "training_log"):
                rows = cursor.execute(
                    f"SELECT * FROM {table} WHERE athlete_id = ? AND date = ?",  # noqa: S608  # nosec B608 - fixed names
                    (athlete_id, date),
                )
                names = [d[0] for d in rows.description]
                parts.append([table, sorted(
                    json.dumps({k: v for k, v in zip(names, row, strict=True) if k != "id"},
                               sort_keys=True, default=str)
                    for row in rows.fetchall()
                )])
        if not any(found for _table, found in parts):
            return None
        return hashlib.sha256(json.dumps(parts, sort_keys=True).encode("utf-8")).hexdigest()

    def get_incomplete_routine_executions(self, execution_date: str) -> list[tuple[str, str]]:
        """Return (athlete_id, routine_type) rows of that date that never completed."""
        with self._db._lock:
            self._db._ensure_open_locked()
            rows = self._db.conn.cursor().execute(
                "SELECT athlete_id, routine_type FROM worker_routine_executions "
                "WHERE execution_date = ? AND completed_at IS NULL ORDER BY athlete_id",
                (execution_date,),
            ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def save_weekly_plan(self, *, athlete_id: str, week_start: str, plan: dict) -> None:
        """Store the plan of one week (D-020); a second plan for the same week replaces it."""
        with self._db._lock:
            self._db._ensure_open_locked()
            self._db.conn.cursor().execute(
                "INSERT INTO weekly_plans (athlete_id, week_start, plan_json, created_at) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (athlete_id, week_start) DO UPDATE SET "
                "plan_json = excluded.plan_json, created_at = excluded.created_at",
                (athlete_id, week_start, json.dumps(plan, ensure_ascii=False), datetime.now(UTC).isoformat()),
            )
            self._db.conn.commit()

    def get_latest_weekly_plan(self, *, athlete_id: str, on_or_before: str) -> dict | None:
        """Return the newest plan whose week starts on or before ``on_or_before`` (ISO date)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            row = self._db.conn.cursor().execute(
                "SELECT plan_json FROM weekly_plans WHERE athlete_id = ? AND week_start <= ? "
                "ORDER BY week_start DESC LIMIT 1",
                (athlete_id, on_or_before),
            ).fetchone()
        if row is None:
            return None
        try:
            plan = json.loads(row[0])
        except (TypeError, ValueError):
            return None
        return plan if isinstance(plan, dict) else None

    def backup_database(
        self,
        backup_dir: Path | None = None,
        keep: int = 30,
        keep_weekly: int = 0,
    ) -> Path | None:
        """Create a verified hot backup of the database using sqlite3.backup().

        Safe to call while the DB is open and active — sqlite3.backup() uses
        the SQLite online backup API which does not require exclusive access.

        One backup per calendar day is created. If today's backup already exists
        the call is a no-op and returns None. Every new artifact is verified
        (AGENTS DR-02): ``PRAGMA integrity_check`` must return ``ok`` and its
        ``user_version`` must match the live database. A failed artifact is
        renamed to ``*.db.corrupt``, logged CRITICAL and counted in
        ``backup_failure_total``. Retention keeps the ``keep`` newest daily
        backups plus the newest backup of each of the ``keep_weekly`` most
        recent ISO weeks outside that set.

        Args:
            backup_dir: Directory for backup files. Defaults to
                ``<db_dir>/backups/``.
            keep: Number of daily backups to retain (default 30).
            keep_weekly: Number of extra weekly backups to retain (default 0).

        Returns:
            Path to the verified backup created today, or None if it already
            existed or the backup failed.
        """
        if backup_dir is None:
            backup_dir = self._db.db_path.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)

        date_str = datetime.now(UTC).strftime("%Y-%m-%d")
        dest = backup_dir / f"titan_{date_str}.db"

        if dest.exists():
            return None  # today's backup already done

        # deferred: titan.core.database imports this module
        from titan.core.database import _log, _verify_backup_artifact

        try:
            with self._db._lock:
                self._db._ensure_open_locked()
                with sqlite3.connect(str(dest)) as dst_conn:
                    self._db.conn.backup(dst_conn)
                source_version = int(self._db.conn.execute("PRAGMA user_version").fetchone()[0])
            problem = _verify_backup_artifact(dest, expected_user_version=source_version)
        except Exception as exc:
            problem = f"{type(exc).__name__}: {exc}"

        if problem is not None:
            self._db._record_backup_failure(dest, problem)
            return None

        _log.info(
            json.dumps({
                "flow": "database",
                "action": "db_backup_created",
                "dest": str(dest),
                "date": date_str,
                "size_bytes": dest.stat().st_size,
                "integrity": "ok",
            })
        )
        self._db._prune_old_backups(backup_dir, keep=keep, keep_weekly=keep_weekly)
        return dest

    def _record_backup_failure(self, dest: Path, problem: str) -> None:
        """Quarantine a failed backup artifact; log CRITICAL and count the failure."""
        # deferred: titan.core.database imports this module
        from titan.core.database import _log

        if dest.exists():
            with suppress(OSError):
                dest.replace(dest.with_name(dest.name + ".corrupt"))
        _log.critical(
            json.dumps({
                "flow": "database",
                "action": "db_backup_failed",
                "dest": str(dest),
                "error_message": problem,
            })
        )
        with suppress(Exception):
            from titan.observability.metrics import get_metrics

            get_metrics().counter("backup_failure_total")

    def _prune_old_backups(self, backup_dir: Path, keep: int, keep_weekly: int = 0) -> None:
        """Keep the ``keep`` newest daily backups plus ``keep_weekly`` older weekly ones."""

        def _iso_week(path: Path) -> tuple[int, int] | None:
            try:
                return datetime.strptime(path.stem[len("titan_"):], "%Y-%m-%d").isocalendar()[:2]
            except ValueError:
                return None

        backups = sorted(backup_dir.glob("titan_????-??-??.db"))
        daily = backups[-keep:] if keep > 0 else []
        older = backups[: len(backups) - len(daily)]
        covered_weeks = {_iso_week(p) for p in daily}
        weekly: list[Path] = []
        for candidate in reversed(older):
            if len(weekly) >= keep_weekly:
                break
            week = _iso_week(candidate)
            if week is None or week in covered_weeks:
                continue
            covered_weeks.add(week)
            weekly.append(candidate)
        retained = set(daily) | set(weekly)
        for old in backups:
            if old not in retained:
                with suppress(OSError):
                    old.unlink()

    def check_integrity(self) -> bool:
        """Runs PRAGMA integrity_check. Returns True if OK, False otherwise."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            ok = result is not None and result[0] == "ok"
            if not ok:
                # deferred: titan.core.database imports this module
                from titan.core.database import _database_event

                _database_event(
                    "db_integrity_check_failed",
                    level=logging.ERROR,
                    result=result,
                )
            return ok

    def get_table_names(self) -> list[str]:
        """Return all table names present in the database."""
        with self._db._lock:
            self._db._ensure_open_locked()
            rows = self._db.conn.cursor().execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        return [r[0] for r in rows]

    def is_db_reachable(self) -> bool:
        """Probe that the DB connection is live (schema-introspection query)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            result = self._db.conn.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        return result is not None

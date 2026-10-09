"""Operations domain SQL: sync outcomes and freshness, degraded-mode state
(HD-06), nutrition preferences, worker routine claims (ADR-0060 D1, INV-15),
and verified backups with integrity checks (AGENTS DR-02)."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import suppress
from datetime import UTC, datetime
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
        source: str,
        attempted_at: datetime,
        success: bool,
        error_class: str | None = None,
    ) -> None:
        """Persist latest sync attempt outcome for a source system."""
        attempted_iso = attempted_at.astimezone(UTC).isoformat()
        success_iso = attempted_iso if success else None

        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """INSERT INTO sync_metadata (
                        source,
                        last_attempt_ts,
                        last_success_ts,
                        last_sync_ok,
                        last_error_class
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(source) DO UPDATE SET
                        last_attempt_ts = excluded.last_attempt_ts,
                        last_success_ts = CASE
                            WHEN excluded.last_sync_ok = 1 THEN excluded.last_success_ts
                            ELSE sync_metadata.last_success_ts
                        END,
                        last_sync_ok = excluded.last_sync_ok,
                        last_error_class = excluded.last_error_class""",
                (source, attempted_iso, success_iso, 1 if success else 0, error_class),
            )
            self._db.conn.commit()

    def get_last_sync_outcome(self, source: str) -> dict[str, Any] | None:
        """Return latest sync outcome metadata for a source."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT last_attempt_ts, last_success_ts, last_sync_ok, last_error_class
                   FROM sync_metadata WHERE source = ?""",
                (source,),
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

    def get_last_garmin_sync_timestamp(self) -> datetime | None:
        """Return a datetime representing the most recent data written by Garmin sync.

        Checks the latest date in both daily_metrics and training_log and returns
        the more recent of the two, parsed as a midnight-UTC datetime.

        Returns None if no data exists in either table.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                "SELECT MAX(date) FROM daily_metrics WHERE date IS NOT NULL"
            )
            dm_row = cursor.fetchone()
            cursor.execute(
                "SELECT MAX(date) FROM training_log WHERE date IS NOT NULL"
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

    def claim_routine_execution(
        self, *, athlete_id: str, execution_date: str, routine_type: str, started_at: datetime
    ) -> bool:
        """Claim one routine run (ADR-0060 D1): True if this call inserted the row.

        False means the row already exists, so the routine already started that
        day. Any other database error propagates so the caller fails closed.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            try:
                self._db.conn.cursor().execute(
                    "INSERT INTO worker_routine_executions "
                    "(athlete_id, execution_date, routine_type, started_at) VALUES (?, ?, ?, ?)",
                    (athlete_id, execution_date, routine_type, started_at.astimezone(UTC).isoformat()),
                )
            except sqlite3.IntegrityError:
                self._db.conn.rollback()
                return False
            self._db.conn.commit()
            return True

    def complete_routine_execution(
        self, *, athlete_id: str, execution_date: str, routine_type: str, completed_at: datetime
    ) -> None:
        """Mark a claimed routine as returned (ADR-0060 D1 step 2)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            self._db.conn.cursor().execute(
                "UPDATE worker_routine_executions SET completed_at = ? "
                "WHERE athlete_id = ? AND execution_date = ? AND routine_type = ?",
                (completed_at.astimezone(UTC).isoformat(), athlete_id, execution_date, routine_type),
            )
            self._db.conn.commit()

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

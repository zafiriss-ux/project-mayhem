"""Governance domain SQL: override audit log, governance decisions with their
outcomes, per-athlete threshold offsets, cold start and calibration rates."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager


class GovernanceRepository:
    """Governance SQL, on the owning DatabaseManager's connection and lock."""

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    def log_override(
        self,
        date: str,
        prescribed: str,
        actual: str,
        reason: str = '',
    ) -> None:
        """
        Record a session override (athlete deviated from prescribed session).
        Used by GovernanceEngine to calculate override_ratio.

        Args:
            date:       Date in ISO format
            prescribed: Prescribed session type (e.g. 'REST')
            actual:     Actual session performed (e.g. 'INTERVALS')
            reason:     Optional athlete-supplied reason
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """INSERT INTO override_log (date, prescribed_type, actual_type, reason)
                   VALUES (?, ?, ?, ?)""",
                (date, prescribed, actual, reason),
            )
            self._db.conn.commit()

    def record_override_signal(
        self,
        *,
        decision_id: str,
        athlete_id: str,
        override_source: str,
        override_reason: str,
        created_at: str,
    ) -> None:
        """Persist structured override signal entries (ADR-0042)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """INSERT INTO override_signals (
                       decision_id, athlete_id, override_source, override_reason, created_at
                   ) VALUES (?, ?, ?, ?, ?)""",
                (decision_id, athlete_id, override_source, override_reason, created_at),
            )
            self._db.conn.commit()

    def get_override_ratio(self, athlete_id: str = "owner", days: int = 14) -> float | None:
        """
        Calculate the fraction of days in the last N days with an override.

        Returns:
            None on cold-start (no governance_outcomes history).
            Float 0.0–1.0 (1.0 = overrode every day in the window).
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM governance_outcomes WHERE athlete_id = ?",
                (athlete_id,),
            )
            count_row = cursor.fetchone()
            count = count_row[0] if count_row else 0
            if count == 0:
                return None  # cold-start: no outcome history
            cursor.execute(
                """SELECT COUNT(*) FROM override_log
                   WHERE date >= date('now', '-' || ? || ' days')""",
                (days,),
            )
            row = cursor.fetchone()
        overrides = row[0] if row else 0
        return round(overrides / days, 3)

    def get_override_log(self, limit: int = 50) -> list[dict[str, str]]:
        """Return recent override audit rows (oldest first) for operator review."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT date, prescribed_type, actual_type, reason
                   FROM override_log
                   ORDER BY id ASC
                   LIMIT ?""",
                (limit,),
            )
            rows = cursor.fetchall()
        return [
            {
                'date': row[0],
                'prescribed_type': row[1],
                'actual_type': row[2],
                'reason': row[3],
            }
            for row in rows
        ]

    def save_governance_decision(self, decision: dict[str, Any]) -> None:
        """Persist a governance decision snapshot into governance_outcomes."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """INSERT INTO governance_outcomes (
                       athlete_id,
                       date, session_planned, session_post_governance,
                       locks_applied_json, governance_clean, phase, vlg_color,
                       apl_priority_vector_json, lock_thresholds_active_json,
                       acwr, tsb_value, readiness_score, glycogen_debt, afi_value,
                       outcome_rpe, outcome_completed, outcome_session_type_actual, outcome_notes,
                       decision_was_followed, override_outcome_exclusion,
                       outcome_independence_ok, algorithm_version_snapshot
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision.get('athlete_profile_id', 'owner'),
                    decision['date'],
                    decision['session_planned'],
                    decision['session_post_governance'],
                    json.dumps(decision.get('locks_applied', []), default=str),
                    int(bool(decision.get('governance_clean', False))),
                    decision.get('phase', ''),
                    decision.get('vlg_color', ''),
                    json.dumps(decision.get('apl_priority_vector', {}), default=str),
                    json.dumps(decision.get('lock_thresholds_active', {}), default=str),
                    float(decision.get('acwr', 0.0)),
                    float(decision.get('tsb_value', 0.0)),
                    float(decision.get('readiness_score', 0.0)),
                    float(decision.get('glycogen_debt', 0.0)),
                    decision.get('afi_value'),
                    decision.get('outcome_rpe'),
                    int(decision['outcome_completed']) if decision.get('outcome_completed') is not None else None,
                    decision.get('outcome_session_type_actual'),
                    decision.get('outcome_notes'),
                    int(bool(decision.get('decision_was_followed', True))),
                    int(bool(decision.get('override_outcome_exclusion', False))),
                    int(bool(decision.get('outcome_independence_ok', True))),
                    json.dumps(decision.get('algorithm_version_snapshot', {}), default=str),
                ),
            )
            self._db.conn.commit()

    def update_governance_outcome(
        self,
        date: str,
        rpe: int | None = None,
        completed: bool | None = None,
        actual_session_type: str | None = None,
        notes: str | None = None,
        decision_was_followed: bool | None = None,
        override_outcome_exclusion: bool | None = None,
        outcome_independence_ok: bool | None = None,
        algorithm_version_snapshot: dict[str, str] | None = None,
        athlete_id: str = "owner",
    ) -> bool:
        """Update latest governance decision for athlete_id/date with post-session outcome."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """UPDATE governance_outcomes
                   SET outcome_rpe = ?,
                       outcome_completed = ?,
                       outcome_session_type_actual = ?,
                       outcome_notes = ?,
                       decision_was_followed = COALESCE(?, decision_was_followed),
                       override_outcome_exclusion = COALESCE(?, override_outcome_exclusion),
                       outcome_independence_ok = COALESCE(?, outcome_independence_ok),
                       algorithm_version_snapshot = COALESCE(?, algorithm_version_snapshot)
                   WHERE id = (
                       SELECT id FROM governance_outcomes
                       WHERE athlete_id = ? AND date = ?
                       ORDER BY id DESC
                       LIMIT 1
                   )""",
                (
                    rpe,
                    int(completed) if completed is not None else None,
                    actual_session_type,
                    notes,
                    int(decision_was_followed) if decision_was_followed is not None else None,
                    int(override_outcome_exclusion) if override_outcome_exclusion is not None else None,
                    int(outcome_independence_ok) if outcome_independence_ok is not None else None,
                    json.dumps(algorithm_version_snapshot, default=str)
                    if algorithm_version_snapshot is not None
                    else None,
                    athlete_id,
                    date,
                ),
            )
            self._db.conn.commit()
            return cursor.rowcount > 0

    def get_governance_decisions(
        self, limit: int = 1000, athlete_id: str = "owner"
    ) -> list[dict[str, Any]]:
        """Fetch governance decisions ordered by insertion order (oldest first)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT date, session_planned, session_post_governance,
                          locks_applied_json, governance_clean, phase, vlg_color,
                          apl_priority_vector_json, lock_thresholds_active_json,
                          acwr, tsb_value, readiness_score, glycogen_debt, afi_value,
                          outcome_rpe, outcome_completed, outcome_session_type_actual, outcome_notes,
                          decision_was_followed, override_outcome_exclusion,
                          outcome_independence_ok, algorithm_version_snapshot
                   FROM governance_outcomes
                   WHERE athlete_id = ?
                   ORDER BY id ASC
                   LIMIT ?""",
                (athlete_id, limit),
            )

            rows = cursor.fetchall()
        # deferred: titan.core.database imports this module
        from titan.core.database import _safe_json

        decisions: list[dict[str, Any]] = []
        for row in rows:
            decisions.append({
                'date': row[0],
                'session_planned': row[1],
                'session_post_governance': row[2],
                'locks_applied': _safe_json(row[3], [], 'locks_applied_json'),
                'governance_clean': bool(row[4]),
                'phase': row[5],
                'vlg_color': row[6],
                'apl_priority_vector': _safe_json(row[7], {}, 'apl_priority_vector_json'),
                'lock_thresholds_active': _safe_json(row[8], {}, 'lock_thresholds_active_json'),
                'acwr': float(row[9]),
                'tsb_value': float(row[10]),
                'readiness_score': float(row[11]),
                'glycogen_debt': float(row[12]),
                'afi_value': float(row[13]) if row[13] is not None else None,
                'outcome_rpe': row[14],
                'outcome_completed': bool(row[15]) if row[15] is not None else None,
                'outcome_session_type_actual': row[16],
                'outcome_notes': row[17],
                'decision_was_followed': bool(row[18]),
                'override_outcome_exclusion': bool(row[19]),
                'outcome_independence_ok': bool(row[20]),
                'algorithm_version_snapshot': _safe_json(
                    row[21], {}, 'algorithm_version_snapshot'
                ),
            })
        return decisions

    def annotate_governance_outcome(self, date: str, note: str) -> bool:
        """Attach or replace manual operator note for latest governance decision on date."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """UPDATE governance_outcomes
                   SET outcome_notes = ?
                   WHERE id = (
                       SELECT id FROM governance_outcomes
                       WHERE date = ?
                       ORDER BY id DESC
                       LIMIT 1
                   )""",
                (note, date),
            )
            self._db.conn.commit()
            return cursor.rowcount > 0

    def save_threshold_offset(
        self,
        athlete_id: str,
        threshold_key: str,
        delta_value: float,
        source: str,
        confidence: float,
        updated_at: str,
    ) -> None:
        """Persist a per-athlete threshold offset (ADR-0052).

        Raises ValueError if threshold_key is in HARD_STOP_THRESHOLD_KEYS —
        hard-stop gates H1–H5 are permanently excluded from adaptation.
        The ±20 % ceiling is ThresholdAdapter's responsibility (Stage 2);
        this layer enforces only the H1–H5 exclusion invariant.

        The INSERT ... ON CONFLICT DO UPDATE provides UPSERT semantics:
        a second call with the same (athlete_id, threshold_key) replaces
        delta_value, source, confidence, and updated_at.

        Args:
            athlete_id:    Athlete identifier (non-empty string).
            threshold_key: Identifier for the threshold being offset.
            delta_value:   Additive offset (positive or negative float).
            source:        Origin — 'manual' or 'calibration'.
            confidence:    Confidence score in [0.0, 1.0].
            updated_at:    UTC ISO-8601 timestamp string.
        """
        from titan.config.thresholds import HARD_STOP_THRESHOLD_KEYS  # local import avoids circular
        if threshold_key in HARD_STOP_THRESHOLD_KEYS:
            raise ValueError(
                f"threshold_key '{threshold_key}' is a hard-stop gate "
                f"and cannot be adapted (ADR-0052)."
            )
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """
                INSERT INTO athlete_threshold_offsets
                    (athlete_id, threshold_key, delta_value,
                     updated_at, source, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (athlete_id, threshold_key)
                DO UPDATE SET
                    delta_value = excluded.delta_value,
                    updated_at  = excluded.updated_at,
                    source      = excluded.source,
                    confidence  = excluded.confidence
                """,
                (athlete_id, threshold_key, delta_value, updated_at, source, confidence),
            )
            if self._db._transaction_depth == 0:
                self._db.conn.commit()

    def get_athlete_threshold_offsets(self, athlete_id: str) -> list[dict]:
        """Return all threshold offset rows for an athlete.

        Returns a list of dicts with keys 'threshold_key', 'delta_value',
        'source', and 'updated_at'.
        Returns an empty list if the athlete has no recorded offsets.
        Used by ThresholdAdapter.load() and CalibrationRollbackGate (ADR-0052 Stage 2).
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            rows = self._db.conn.cursor().execute(
                "SELECT threshold_key, delta_value, source, updated_at "
                "FROM athlete_threshold_offsets WHERE athlete_id = ?",
                (athlete_id,),
            ).fetchall()
        return [
            {"threshold_key": r[0], "delta_value": r[1], "source": r[2], "updated_at": r[3]}
            for r in rows
        ]

    def delete_threshold_offset(self, athlete_id: str, threshold_key: str) -> int:
        """Delete a calibration-sourced threshold offset row (P27-04 rollback gate).

        The source='calibration' guard in the DELETE is the hard safety: a manual
        offset can never be deleted by this path even if called with a manual key.

        Returns the number of rows deleted (0 or 1).
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            c = self._db.conn.cursor()
            c.execute(
                "DELETE FROM athlete_threshold_offsets "
                "WHERE athlete_id = ? AND threshold_key = ? AND source = 'calibration'",
                (athlete_id, threshold_key),
            )
            if self._db._transaction_depth == 0:
                self._db.conn.commit()
            return c.rowcount

    def get_completion_rate(
        self, athlete_id: str, start_date: str, end_date: str
    ) -> tuple[float | None, int]:
        """Return (completion_rate, sample_count) for athlete_id in [start_date, end_date].

        completion_rate = COUNT(outcome_completed=1) / COUNT(outcome_completed IS NOT NULL)
        over governance_outcomes in the inclusive date range.

        Returns (None, 0) when there are no qualifying rows (prevents division by zero).
        Used by CalibrationRollbackGate (P27-04).
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            row = self._db.conn.cursor().execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE outcome_completed = 1) AS completed_count,
                    COUNT(*) FILTER (WHERE outcome_completed IS NOT NULL) AS total_count
                FROM governance_outcomes
                WHERE athlete_id = ? AND date >= ? AND date <= ?
                """,
                (athlete_id, start_date, end_date),
            ).fetchone()
        if row is None:
            return None, 0
        completed_count, total_count = row
        if (total_count or 0) == 0:
            return None, 0
        return completed_count / total_count, total_count

    def is_athlete_cold_start(self, athlete_id: str) -> bool:
        """Return True if the athlete is in the cold-start bootstrapping period.

        Reads the is_cold_start flag from the athletes table. Fail-closed:
        returns True (conservative) for unknown athletes (INV-05).

        The flag is cleared atomically by check_and_exit_cold_start() when both
        exit conditions are met: cold_start_sessions_count >= 30 AND
        governance_outcomes >= CALIBRATION_MIN_OUTCOME_COUNT (ADR-0033 L3-C).

        Used by coaching_pipeline() and ThresholdAdapter.is_circuit_breaker_active().
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            row = self._db.conn.cursor().execute(
                "SELECT is_cold_start FROM athletes WHERE athlete_id = ?",
                (athlete_id,),
            ).fetchone()
        if row is None:
            return True  # fail-closed: unknown athlete → treat as cold-start
        return bool(row[0])

    def check_and_exit_cold_start(self, athlete_id: str) -> bool:
        """Check cold-start exit conditions and graduate the athlete if met.

        Exit requires both (ADR-0033 L3-C):
          1. cold_start_sessions_count >= 30
          2. governance_outcomes completed >= CALIBRATION_MIN_OUTCOME_COUNT

        When both are met, sets is_cold_start=0 and cold_start_ends_at=now
        atomically and emits athlete_cold_start_completed (INFO).

        Returns True if the athlete was graduated in this call.
        """
        from titan.config.thresholds import CALIBRATION_MIN_OUTCOME_COUNT

        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            row = cursor.execute(
                "SELECT is_cold_start, cold_start_sessions_count "
                "FROM athletes WHERE athlete_id = ?",
                (athlete_id,),
            ).fetchone()

            if row is None or not row[0]:
                return False  # not in cold-start

            sessions_ok = row[1] >= 30

            outcome_count = cursor.execute(
                "SELECT COUNT(*) FROM governance_outcomes "
                "WHERE athlete_id = ? AND outcome_completed = 1",
                (athlete_id,),
            ).fetchone()[0]
            outcomes_ok = outcome_count >= CALIBRATION_MIN_OUTCOME_COUNT

            if not (sessions_ok and outcomes_ok):
                return False

            now_iso = datetime.now(UTC).isoformat()
            cursor.execute(
                "UPDATE athletes SET is_cold_start = 0, cold_start_ends_at = ? "
                "WHERE athlete_id = ?",
                (now_iso, athlete_id),
            )
            self._db.conn.commit()

        # deferred: titan.core.database imports this module
        from titan.core.database import _database_event

        _database_event(
            "athlete_cold_start_completed",
            logging.INFO,
            athlete_id=athlete_id,
        )
        return True

    def increment_cold_start_sessions(self, athlete_id: str) -> None:
        """Increment cold_start_sessions_count for a cold-start athlete.

        No-op if the athlete is not found or is already graduated (is_cold_start=0).
        Called once per coaching session during the cold-start period.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            self._db.conn.cursor().execute(
                "UPDATE athletes "
                "SET cold_start_sessions_count = cold_start_sessions_count + 1 "
                "WHERE athlete_id = ? AND is_cold_start = 1",
                (athlete_id,),
            )
            self._db.conn.commit()

    def get_false_negative_rate(self, athlete_id: str, window_days: int) -> float:
        """Return the false-negative rate for the athlete over the last window_days.

        FALSE_NEG = governance cleared training (governance_clean=1) AND athlete
        followed the recommendation (decision_was_followed=1) AND session was not
        completed (outcome_completed=0 with a non-NULL outcome_completed value).

        Returns 0.0 if:
        - Total followed-and-evaluated decisions < CALIBRATION_MIN_OUTCOME_COUNT
        - The outcome quality data is unavailable

        Used by ThresholdAdapter.is_circuit_breaker_active() (ADR-0052 Stage 2).
        """
        from titan.config.thresholds import CALIBRATION_MIN_OUTCOME_COUNT
        cutoff = (
            datetime.now(UTC) - timedelta(days=window_days)
        ).date().isoformat()
        with self._db._lock:
            self._db._ensure_open_locked()
            row = self._db.conn.cursor().execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE governance_clean = 1
                          AND decision_was_followed = 1
                          AND outcome_completed = 0
                    ) AS false_neg_count,
                    COUNT(*) FILTER (
                        WHERE governance_clean = 1
                          AND decision_was_followed = 1
                          AND outcome_completed IS NOT NULL
                    ) AS total_evaluated
                FROM governance_outcomes
                WHERE athlete_id = ? AND date >= ?
                """,
                (athlete_id, cutoff),
            ).fetchone()
        if row is None:
            return 0.0
        false_neg_count, total_evaluated = row
        if (total_evaluated or 0) < CALIBRATION_MIN_OUTCOME_COUNT:
            return 0.0
        return false_neg_count / total_evaluated

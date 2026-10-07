"""Governance domain SQL: override audit log and governance decisions with
their outcomes."""

from __future__ import annotations

import json
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

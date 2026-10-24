"""Governance domain SQL: override audit log, Telegram override nonces
(ADR-0060 D2), governance decisions with their outcomes, per-athlete threshold
offsets, cold start, calibration rates and model calibration metadata."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager


def decision_athlete_id(decision: dict[str, Any]) -> str:
    """Return the athlete a governance decision belongs to (MA-F3, D-122).

    A decision that does not name an athlete is the owner's. One that names an
    empty athlete (``""``, blanks or ``None``) is refused: guessing the owner there
    would write another athlete's decision into the owner's history.
    """
    if "athlete_profile_id" not in decision:
        return "owner"
    athlete_id = decision["athlete_profile_id"]
    if not isinstance(athlete_id, str) or not athlete_id.strip():
        raise ValueError("governance decision names an empty athlete_profile_id")
    return athlete_id


def _utc_iso(moment: datetime) -> str:
    """Fixed-width UTC ISO-8601, so nonce times compare correctly as text."""
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def _float_or_none(value: Any) -> float | None:
    """A stored ACWR or TSB: NULL stays unknown and is never read as 0.0 (OW-M2, ADR-0069 §4α)."""
    return None if value is None else float(value)


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
        *,
        athlete_id: str,
    ) -> None:
        """
        Record a session override (athlete deviated from prescribed session).
        Used by GovernanceEngine to calculate override_ratio.

        Args:
            date:       Date in ISO format
            prescribed: Prescribed session type (e.g. 'REST')
            actual:     Actual session performed (e.g. 'INTERVALS')
            reason:     Optional athlete-supplied reason
            athlete_id: The athlete who overrode; required, no default (ADR-0067 D3)
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """INSERT INTO override_log (athlete_id, date, prescribed_type, actual_type, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (athlete_id, date, prescribed, actual, reason),
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
                   WHERE athlete_id = ? AND date >= date('now', '-' || ? || ' days')""",
                (athlete_id, days),
            )
            row = cursor.fetchone()
        overrides = row[0] if row else 0
        return round(overrides / days, 3)

    def get_override_log(self, limit: int = 50, athlete_id: str = "owner") -> list[dict[str, str]]:
        """Return the athlete's recent override audit rows (oldest first) for operator review."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT date, prescribed_type, actual_type, reason
                   FROM override_log
                   WHERE athlete_id = ?
                   ORDER BY id ASC
                   LIMIT ?""",
                (athlete_id, limit),
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

    def issue_override_nonce(
        self,
        *,
        nonce: str,
        command_type: str,
        athlete_id: str,
        decision_id: str,
        issued_at: datetime,
        expires_at: datetime,
    ) -> None:
        """Store a one-time override nonce bound to its decision (INV-17)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            self._db.conn.cursor().execute(
                """INSERT INTO telegram_override_nonces
                       (nonce, command_type, athlete_id, decision_id, issued_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (nonce, command_type, athlete_id, decision_id,
                 _utc_iso(issued_at), _utc_iso(expires_at)),
            )
            self._db.conn.commit()

    def consume_override_nonce(self, *, nonce: str, command_type: str, now: datetime) -> str | None:
        """Consume a nonce; return its decision_id, or None if unknown, expired,
        already used or for another command.

        Expiry and replay are checked in the UPDATE itself (no TOCTOU, ADR-0060 D2).
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """UPDATE telegram_override_nonces
                      SET consumed_at = :now
                    WHERE nonce = :nonce
                      AND command_type = :command_type
                      AND consumed_at IS NULL
                      AND expires_at > :now""",
                {"now": _utc_iso(now), "nonce": nonce, "command_type": command_type},
            )
            if cursor.rowcount != 1:
                self._db.conn.rollback()
                return None
            row = cursor.execute(
                "SELECT decision_id FROM telegram_override_nonces WHERE nonce = ?", (nonce,)
            ).fetchone()
            self._db.conn.commit()
        return row[0]

    def prune_expired_override_nonces(self, now: datetime) -> int:
        """Delete nonces that expired before ``now``; unexpired ones stay valid."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                "DELETE FROM telegram_override_nonces WHERE expires_at < ?", (_utc_iso(now),)
            )
            self._db.conn.commit()
            return cursor.rowcount

    def save_governance_decision(self, decision: dict[str, Any]) -> None:
        """Persist a governance decision snapshot into governance_outcomes.

        One row per athlete and day (v34, ADR-0069 §4δ): a second decision of the same day
        replaces the first in place, as ``replace_governance_decision_on`` does, and the
        outcome columns stay as they are. An unknown ACWR or TSB is stored as NULL (§4α).
        """
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
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (athlete_id, date) DO UPDATE SET
                       session_planned = excluded.session_planned,
                       session_post_governance = excluded.session_post_governance,
                       locks_applied_json = excluded.locks_applied_json,
                       governance_clean = excluded.governance_clean,
                       phase = excluded.phase,
                       vlg_color = excluded.vlg_color,
                       apl_priority_vector_json = excluded.apl_priority_vector_json,
                       lock_thresholds_active_json = excluded.lock_thresholds_active_json,
                       acwr = excluded.acwr,
                       tsb_value = excluded.tsb_value,
                       readiness_score = excluded.readiness_score,
                       glycogen_debt = excluded.glycogen_debt,
                       afi_value = excluded.afi_value,
                       algorithm_version_snapshot = excluded.algorithm_version_snapshot""",
                (
                    decision_athlete_id(decision),
                    decision['date'],
                    decision['session_planned'],
                    decision['session_post_governance'],
                    json.dumps(decision.get('locks_applied', []), default=str),
                    int(bool(decision.get('governance_clean', False))),
                    decision.get('phase', ''),
                    decision.get('vlg_color', ''),
                    json.dumps(decision.get('apl_priority_vector', {}), default=str),
                    json.dumps(decision.get('lock_thresholds_active', {}), default=str),
                    _float_or_none(decision.get('acwr')),
                    _float_or_none(decision.get('tsb_value')),
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

    def replace_governance_decision_on(self, decision: dict[str, Any]) -> bool:
        """Overwrite the athlete's decision of that date with a recomputed one (D-109).

        A morning retry that computes the day again on newer inputs supersedes the
        stored decision in place, so ``governance_outcomes`` keeps one row for one athlete
        and day (ADR-0067 D8.4, D-098). The latest row of that day keeps its id; the
        outcome columns are left as they are. False when there is no row to replace.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """UPDATE governance_outcomes SET
                       session_planned = ?, session_post_governance = ?, locks_applied_json = ?,
                       governance_clean = ?, phase = ?, vlg_color = ?, apl_priority_vector_json = ?,
                       lock_thresholds_active_json = ?, acwr = ?, tsb_value = ?, readiness_score = ?,
                       glycogen_debt = ?, afi_value = ?, algorithm_version_snapshot = ?
                   WHERE id = (SELECT id FROM governance_outcomes WHERE athlete_id = ? AND date = ?
                               ORDER BY id DESC LIMIT 1)""",
                (
                    decision['session_planned'],
                    decision['session_post_governance'],
                    json.dumps(decision.get('locks_applied', []), default=str),
                    int(bool(decision.get('governance_clean', False))),
                    decision.get('phase', ''),
                    decision.get('vlg_color', ''),
                    json.dumps(decision.get('apl_priority_vector', {}), default=str),
                    json.dumps(decision.get('lock_thresholds_active', {}), default=str),
                    _float_or_none(decision.get('acwr')),
                    _float_or_none(decision.get('tsb_value')),
                    float(decision.get('readiness_score', 0.0)),
                    float(decision.get('glycogen_debt', 0.0)),
                    decision.get('afi_value'),
                    json.dumps(decision.get('algorithm_version_snapshot', {}), default=str),
                    decision_athlete_id(decision),
                    decision['date'],
                ),
            )
            replaced = cursor.rowcount > 0
            self._db.conn.commit()
        return replaced

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
                # the row's owner: an athlete's decision must come back as theirs (M0-12)
                'athlete_profile_id': athlete_id,
                'session_planned': row[1],
                'session_post_governance': row[2],
                'locks_applied': _safe_json(row[3], [], 'locks_applied_json'),
                'governance_clean': bool(row[4]),
                'phase': row[5],
                'vlg_color': row[6],
                'apl_priority_vector': _safe_json(row[7], {}, 'apl_priority_vector_json'),
                'lock_thresholds_active': _safe_json(row[8], {}, 'lock_thresholds_active_json'),
                'acwr': _float_or_none(row[9]),
                'tsb_value': _float_or_none(row[10]),
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

    def get_governance_decision_on(self, athlete_id: str, date: str) -> dict[str, Any] | None:
        """The athlete's decision of that date, or None (ADR-0067 D8.4).

        A resumed morning sends this instead of computing the day again, so
        ``governance_outcomes`` is never written twice for one athlete and day.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            row = self._db.conn.cursor().execute(
                "SELECT session_post_governance, locks_applied_json, phase, readiness_score "
                "FROM governance_outcomes "
                "WHERE athlete_id = ? AND date = ? ORDER BY id DESC LIMIT 1",
                (athlete_id, date),
            ).fetchone()
        if row is None:
            return None
        # deferred: titan.core.database imports this module
        from titan.core.database import _safe_json

        return {
            "date": date,
            "session_post_governance": row[0],
            "locks_applied": _safe_json(row[1], [], "locks_applied_json"),
            "phase": row[2],
            "readiness_score": float(row[3]),  # shown by /recovery (SD-08)
        }

    def annotate_governance_outcome(self, date: str, note: str, athlete_id: str = "owner") -> bool:
        """Attach or replace the operator note on one athlete's latest decision of *date*.

        Scoped by ``athlete_id`` (ISO-3, D-110): before, the note landed on whichever
        athlete's decision of that day was written last.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """UPDATE governance_outcomes
                   SET outcome_notes = ?
                   WHERE id = (
                       SELECT id FROM governance_outcomes
                       WHERE date = ? AND athlete_id = ?
                       ORDER BY id DESC
                       LIMIT 1
                   )""",
                (note, date, athlete_id),
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
        Raises ValueError too when delta_value is not finite or outside the
        ±THRESHOLD_ADAPTER_MAX_DELTA_PCT ceiling, so a raw or manual write can
        never store what the adapter would refuse (SG-08, D-112).

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
        import math

        from titan.config.thresholds import (  # local import avoids circular
            HARD_STOP_THRESHOLD_KEYS,
            THRESHOLD_ADAPTER_MAX_DELTA_PCT,
        )
        if threshold_key in HARD_STOP_THRESHOLD_KEYS:
            raise ValueError(
                f"threshold_key '{threshold_key}' is a hard-stop gate "
                f"and cannot be adapted (ADR-0052)."
            )
        try:
            delta = float(delta_value)
        except (TypeError, ValueError):
            delta = math.nan
        if not math.isfinite(delta) or abs(delta) > THRESHOLD_ADAPTER_MAX_DELTA_PCT:
            raise ValueError(
                f"delta_value {delta_value!r} for '{threshold_key}' is outside "
                f"±{THRESHOLD_ADAPTER_MAX_DELTA_PCT} (ADR-0052)."
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

    _PROFILE_COLUMNS = (
        "birth_date", "sex", "weight_kg", "height_cm", "max_hr", "threshold_hr",
        "training_phase", "training_goal", "location_city", "location_country",
    )

    def get_athlete_profile(self, athlete_id: str) -> tuple[str, dict] | None:
        """Return (display_name, athlete_profiles row) for the athlete, or None without a row.

        v30 (ADR-0067 D5). The owner has no row: the owner's profile is in .env.
        """
        with self._db._lock:
            self._db._ensure_open_locked()
            row = self._db.conn.cursor().execute(
                """SELECT a.display_name, p.birth_date, p.sex, p.weight_kg, p.height_cm,
                          p.max_hr, p.threshold_hr, p.training_phase, p.training_goal,
                          p.location_city, p.location_country
                   FROM athlete_profiles p JOIN athletes a ON a.athlete_id = p.athlete_id
                   WHERE p.athlete_id = ?""",
                (athlete_id,),
            ).fetchone()
        if row is None:
            return None
        return row[0], dict(zip(self._PROFILE_COLUMNS, row[1:], strict=True))

    def save_athlete_profile(self, athlete_id: str, record: dict, *, updated_at: str) -> None:
        """Insert or replace the athlete's athlete_profiles row (the caller validates it)."""
        with self._db._lock:
            self._db._ensure_open_locked()
            self._db.conn.cursor().execute(
                """INSERT INTO athlete_profiles (
                        athlete_id, birth_date, sex, weight_kg, height_cm, max_hr, threshold_hr,
                        training_phase, training_goal, location_city, location_country, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(athlete_id) DO UPDATE SET
                        birth_date = excluded.birth_date, sex = excluded.sex,
                        weight_kg = excluded.weight_kg, height_cm = excluded.height_cm,
                        max_hr = excluded.max_hr, threshold_hr = excluded.threshold_hr,
                        training_phase = excluded.training_phase,
                        training_goal = excluded.training_goal,
                        location_city = excluded.location_city,
                        location_country = excluded.location_country,
                        updated_at = excluded.updated_at""",
                (athlete_id, *(record[c] for c in self._PROFILE_COLUMNS), updated_at),
            )
            self._db.conn.commit()

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

    def upsert_model_calibration_metadata(
        self,
        *,
        model_name: str,
        calibrated_at: str,
        athlete_id: str,
        baseline_hrv_ms: float | None,
        baseline_vo2: float | None,
        schema_version: int,
    ) -> None:
        """Insert or update model calibration metadata for a named model."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """INSERT INTO model_calibration_metadata (
                        model_name,
                        athlete_id,
                        calibrated_at,
                        baseline_hrv_ms,
                        baseline_vo2,
                        schema_version
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(model_name, athlete_id) DO UPDATE SET
                        calibrated_at = excluded.calibrated_at,
                        baseline_hrv_ms = excluded.baseline_hrv_ms,
                        baseline_vo2 = excluded.baseline_vo2,
                        schema_version = excluded.schema_version""",
                (
                    model_name,
                    athlete_id,
                    calibrated_at,
                    baseline_hrv_ms,
                    baseline_vo2,
                    schema_version,
                ),
            )
            if self._db._transaction_depth == 0:
                self._db.conn.commit()

    def get_model_calibration_metadata(
        self,
        model_name: str,
        athlete_id: str = "owner",
    ) -> dict[str, Any] | None:
        """Return calibration metadata for a model, or None when no row exists."""
        with self._db._lock:
            self._db._ensure_open_locked()
            cursor = self._db.conn.cursor()
            cursor.execute(
                """SELECT model_name, athlete_id, calibrated_at,
                          baseline_hrv_ms, baseline_vo2, schema_version
                     FROM model_calibration_metadata
                     WHERE model_name = ? AND athlete_id = ?""",
                (model_name, athlete_id),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return {
            "model_name": str(row[0]),
            "athlete_id": str(row[1]),
            "calibrated_at": str(row[2]),
            "baseline_hrv_ms": float(row[3]) if row[3] is not None else None,
            "baseline_vo2": float(row[4]) if row[4] is not None else None,
            "schema_version": int(row[5]),
        }

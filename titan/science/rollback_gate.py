"""
CalibrationRollbackGate — P27-04 completion-rate rollback guard.

Reverts calibration-sourced threshold offsets when the athlete's session
completion rate degraded by >= ROLLBACK_DEGRADATION_THRESHOLD_PP percentage
points in the 30 days AFTER the offset was applied vs the 30 days BEFORE.

Protects against the ADR-0052 adaptation system making athlete outcomes worse.

Deferred follow-up: injury-event trigger (A2-04) — no injury_event column in
the schema yet; add a second trigger once that column is available.

Safe default: advisory=True — gate evaluates and logs but never auto-reverts
until the caller opts in with advisory=False.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from titan.config.thresholds import (
    CALIBRATION_MIN_OUTCOME_COUNT,
    HARD_STOP_THRESHOLD_KEYS,
    ROLLBACK_DEGRADATION_THRESHOLD_PP,
)
from titan.core.structured_events import EventSeverity, make_event_emitter

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

_log = logging.getLogger(__name__)
_gate_event = make_event_emitter("rollback_gate", _log)

MODULE_VERSION = "1.0.0"


class CalibrationRollbackGate:
    """Evaluate and optionally apply completion-rate-based calibration rollbacks.

    Usage::

        gate = CalibrationRollbackGate(db=db)
        recs = gate.apply(athlete_id="owner", advisory=True)   # default — safe
        recs = gate.apply(athlete_id="owner", advisory=False)  # actually reverts
    """

    def __init__(self, db: DatabaseManager) -> None:
        self._db = db

    # ── Public interface ──────────────────────────────────────────────────────

    def evaluate(self, athlete_id: str) -> list[dict[str, Any]]:
        """Return rollback recommendations for all calibration offsets.

        Each entry contains:
            threshold_key   — the offset key evaluated
            pre_rate        — completion rate in the 30d before calibration anchor
            post_rate       — completion rate in the 30d after (or anchor..now)
            degradation_pp  — (pre - post) * 100, or None if data insufficient
            would_revert    — True when degradation >= threshold and data sufficient
            reason          — 'insufficient_data' | 'insufficient_post_window' | None
        """
        rows = self._db.get_athlete_threshold_offsets(athlete_id)
        calibration_rows = [
            r for r in rows
            if r.get("source") == "calibration"
            and r["threshold_key"] not in HARD_STOP_THRESHOLD_KEYS
        ]

        now = datetime.now(UTC)
        recommendations: list[dict[str, Any]] = []

        for row in calibration_rows:
            key = row["threshold_key"]
            updated_at_str = row["updated_at"]

            anchor = _parse_anchor(updated_at_str)

            pre_start = (anchor - timedelta(days=30)).date().isoformat()
            pre_end = anchor.date().isoformat()
            post_start = anchor.date().isoformat()

            elapsed = now - anchor
            insufficient_post_window = elapsed < timedelta(days=30)
            post_end = (
                anchor + timedelta(days=30) if not insufficient_post_window else now
            ).date().isoformat()

            pre_rate, pre_count = self._db.get_completion_rate(
                athlete_id, pre_start, pre_end
            )
            post_rate, post_count = self._db.get_completion_rate(
                athlete_id, post_start, post_end
            )

            rec: dict[str, Any] = {
                "threshold_key": key,
                "pre_rate": pre_rate,
                "post_rate": post_rate,
                "degradation_pp": None,
                "would_revert": False,
                "reason": None,
            }

            if insufficient_post_window:
                rec["reason"] = "insufficient_post_window"

            if pre_count < CALIBRATION_MIN_OUTCOME_COUNT or post_count < CALIBRATION_MIN_OUTCOME_COUNT:
                rec["reason"] = "insufficient_data"
                recommendations.append(rec)
                continue

            degradation_pp = ((pre_rate or 0.0) - (post_rate or 0.0)) * 100
            rec["degradation_pp"] = degradation_pp
            rec["would_revert"] = (
                degradation_pp >= ROLLBACK_DEGRADATION_THRESHOLD_PP
                and not insufficient_post_window
            )

            recommendations.append(rec)

        return recommendations

    def apply(
        self, athlete_id: str, advisory: bool = True
    ) -> list[dict[str, Any]]:
        """Evaluate and optionally revert degraded calibration offsets.

        advisory=True (default): log recommendations, revert nothing.
        advisory=False: call delete_threshold_offset for each would_revert=True
                        and log each reversion.

        Returns the full recommendation list from evaluate().
        """
        recommendations = self.evaluate(athlete_id)

        _gate_event(
            "rollback_gate_evaluated",
            athlete_id=athlete_id,
            advisory=advisory,
            recommendation_count=len(recommendations),
            revert_count=sum(1 for r in recommendations if r["would_revert"]),
        )

        if advisory:
            return recommendations

        for rec in recommendations:
            if not rec["would_revert"]:
                continue
            deleted = self._db.delete_threshold_offset(athlete_id, rec["threshold_key"])
            if deleted:
                _gate_event(
                    "calibration_offset_reverted",
                    severity=EventSeverity.WARNING,
                    athlete_id=athlete_id,
                    threshold_key=rec["threshold_key"],
                    pre_rate=rec["pre_rate"],
                    post_rate=rec["post_rate"],
                    degradation_pp=rec["degradation_pp"],
                )

        return recommendations


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_anchor(updated_at: str) -> datetime:
    """Parse an ISO-8601 updated_at string to a UTC-aware datetime."""
    dt = datetime.fromisoformat(updated_at)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


__all__ = ["CalibrationRollbackGate", "MODULE_VERSION"]

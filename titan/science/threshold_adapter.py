"""
ThresholdAdapter — per-athlete additive threshold offset module.

ADR-0052: GovernanceEngine optional injection; athlete_threshold_offsets DB
table; hard-stop gates excluded from adaptation; circuit breaker at
FALSE_NEG > 20% over 30 days; damping ±5% per cycle; |δT| ≤ 20% ceiling.

ADR-0033 Layer 3 (L3-C): circuit breaker is DISABLED during athlete cold-start.
"""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.core.database import DatabaseManager

MODULE_VERSION = "1.0.0"

# ── ADR-0052 constants ────────────────────────────────────────────────────────
# ── Hard-stop gate names — NEVER adapted (H1–H5 per AGENTS.md §8.1) ──────────
# Imported from the canonical frozenset in thresholds.py (ADR-0052).
# H1 (injury_flag) is boolean — excluded by type. H2–H5 are numeric gates.
from titan.config.thresholds import (  # noqa: E402, I001
    HARD_STOP_THRESHOLD_KEYS as HARD_STOP_GATE_NAMES,
    THRESHOLD_ADAPTER_DAMPING_PCT,
    THRESHOLD_ADAPTER_FALSE_NEG_RATE_LIMIT,
    THRESHOLD_ADAPTER_FALSE_NEG_WINDOW_DAYS,
    THRESHOLD_ADAPTER_MAX_DELTA_PCT,
)


class ThresholdAdapter:
    """
    Applies per-athlete additive offset δT to soft governance thresholds.

    Usage in coaching_pipeline():
        adapter = ThresholdAdapter(athlete_id=ctx.athlete_id, db=ctx.db)
        adapter.load()
        engine = GovernanceEngine(..., threshold_adapter=adapter)

    The adapter reads from and writes to the athlete_threshold_offsets table
    using the existing DatabaseManager interface (ADR-0052 Stage 1 schema).
    Column mapping: threshold_key ↔ threshold name; delta_value ↔ δT.
    """

    def __init__(self, athlete_id: str, db: DatabaseManager) -> None:
        self._athlete_id = athlete_id
        self._db = db
        self._offsets: dict[str, float] = {}  # threshold_key → delta_value (fraction)
        self._loaded = False

    # ── Public interface ──────────────────────────────────────────────────────

    def load(self) -> None:
        """Load offsets from DB. Must be called once before get_threshold()."""
        rows = self._db.get_athlete_threshold_offsets(self._athlete_id)
        self._offsets = {}
        for row in rows:
            key = row["threshold_key"]
            try:
                delta = float(row["delta_value"])
            except (TypeError, ValueError):
                continue
            # A stored row is never trusted past the ceiling, nor for a hard-stop key, even
            # when it was written by raw SQL around save_threshold_offset (SG-08, D-112).
            if key in HARD_STOP_GATE_NAMES or not math.isfinite(delta):
                continue
            self._offsets[key] = max(-THRESHOLD_ADAPTER_MAX_DELTA_PCT, min(THRESHOLD_ADAPTER_MAX_DELTA_PCT, delta))
        self._loaded = True

    def get_threshold(self, threshold_name: str, base_value: float) -> float:
        """
        Return base_value * (1 + δT) for soft gates; base_value unchanged for
        hard-stop gates and non-finite inputs.

        Raises RuntimeError if load() has not been called.
        """
        if not self._loaded:
            raise RuntimeError(
                "ThresholdAdapter.load() must be called before get_threshold(). "
                "Call adapter.load() at coaching_pipeline() entry."
            )
        if not math.isfinite(base_value):
            return base_value  # INV-01: do not adapt non-finite values
        if threshold_name in HARD_STOP_GATE_NAMES:
            return base_value  # H2–H5 excluded from adaptation (ADR-0052)
        delta = self._offsets.get(threshold_name, 0.0)
        return base_value * (1.0 + delta)

    def propose_adaptation(
        self,
        threshold_name: str,
        direction: float,
        base_value: float,
    ) -> bool:
        """
        Propose a δT update. Returns True if the update was applied.

        direction: +1.0 = threshold too conservative (relax offset upward)
                   -1.0 = threshold too permissive (tighten offset downward)

        Refused if:
        - threshold_name is a hard-stop gate (H2–H5)
        - circuit breaker is active (and athlete is not in cold-start)
        - resulting |δT| would exceed THRESHOLD_ADAPTER_MAX_DELTA_PCT
        - direction is zero or non-finite
        """
        if threshold_name in HARD_STOP_GATE_NAMES:
            return False
        if self.is_circuit_breaker_active():
            return False
        if not math.isfinite(direction) or direction == 0.0:
            return False

        current_delta = self._offsets.get(threshold_name, 0.0)
        step = math.copysign(THRESHOLD_ADAPTER_DAMPING_PCT, direction)
        new_delta = current_delta + step

        # Enforce ±20% ceiling
        new_delta = max(
            -THRESHOLD_ADAPTER_MAX_DELTA_PCT,
            min(THRESHOLD_ADAPTER_MAX_DELTA_PCT, new_delta),
        )
        if new_delta == current_delta:
            return False  # already at ceiling; no update needed

        self._offsets[threshold_name] = new_delta
        now_iso = datetime.now(UTC).isoformat()
        self._db.save_threshold_offset(
            athlete_id=self._athlete_id,
            threshold_key=threshold_name,
            delta_value=new_delta,
            source="calibration",
            confidence=0.5,
            updated_at=now_iso,
        )
        return True

    def is_circuit_breaker_active(self) -> bool:
        """
        Return True if the false-negative rate exceeds the configured limit over
        the last THRESHOLD_ADAPTER_FALSE_NEG_WINDOW_DAYS days.

        FALSE_NEG = governance cleared training AND athlete followed the
        recommendation AND session was not completed.

        ADR-0033 L3-C: always returns False during athlete cold-start (< 10
        outcome records) — conservative adaptation is disabled until enough
        outcome history exists.
        """
        # Cold-start bypass (ADR-0033 L3-C)
        if self._db.is_athlete_cold_start(self._athlete_id):
            return False

        rate = self._db.get_false_negative_rate(
            athlete_id=self._athlete_id,
            window_days=THRESHOLD_ADAPTER_FALSE_NEG_WINDOW_DAYS,
        )
        return rate > THRESHOLD_ADAPTER_FALSE_NEG_RATE_LIMIT

    @staticmethod
    def is_hard_stop_gate(threshold_name: str) -> bool:
        """Return True if threshold_name is a hard-stop gate (H2–H5)."""
        return threshold_name in HARD_STOP_GATE_NAMES

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def loaded(self) -> bool:
        """True after load() has been called successfully."""
        return self._loaded

    @property
    def athlete_id(self) -> str:
        """The athlete identifier this adapter is bound to."""
        return self._athlete_id


# Re-export for import convenience
__all__ = ["ThresholdAdapter", "HARD_STOP_GATE_NAMES", "MODULE_VERSION"]

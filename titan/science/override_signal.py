"""Override signal contract and persistence adapter (ADR-0042)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_VALID_OVERRIDE_SOURCES: frozenset[str] = frozenset({"telegram_bot", "operator_console"})


@dataclass(frozen=True)
class OverrideSignal:
    """Structured athlete override signal captured from interaction surfaces."""

    decision_id: str
    athlete_id: str
    override_source: str
    override_reason: str
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        decision_id: str,
        athlete_id: str,
        override_source: str,
        override_reason: str,
    ) -> "OverrideSignal":
        return cls(
            decision_id=decision_id,
            athlete_id=athlete_id,
            override_source=override_source,
            override_reason=override_reason,
            created_at=datetime.now(tz=UTC).isoformat(),
        )


def record_override_signal(db: Any, signal: OverrideSignal) -> None:
    """Persist a validated override signal into durable storage."""
    if signal.override_source not in _VALID_OVERRIDE_SOURCES:
        raise ValueError(f"Unsupported override_source: {signal.override_source}")

    if not signal.override_reason.strip():
        raise ValueError("override_reason is required")

    db.record_override_signal(
        decision_id=signal.decision_id,
        athlete_id=signal.athlete_id,
        override_source=signal.override_source,
        override_reason=signal.override_reason.strip(),
        created_at=signal.created_at,
    )


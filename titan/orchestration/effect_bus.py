"""TitanEffectBus — ADR-0058 Phase B effect dispatcher.

Receives a DecisionResult and dispatches each PlannedEffect to a registered
handler.  Handlers are registered at construction time by the composition
root; the bus itself holds no coaching state.

DESIGN INVARIANT: dispatch() MUST NOT contain if/elif effect_type branches.
All dispatch goes through the handler registry (self._handlers).
Unknown effect_type → EffectDispatchError (fail-loud, not silent skip).

LIFECYCLE HOOK: before_dispatch(result) is called once before the effect
loop.  Used for degraded-mode tracker update (T2-13 / ADR-0050).
Defaults to no-op; injected by the composition root.

REFERENCES: ADR-0058 Phase B, TD-04B, contracts.EFFECT_RECORD_OUTCOME,
contracts.EFFECT_SEND_TELEGRAM
"""
from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from titan.orchestration.contracts import DecisionResult, PlannedEffect

# Type alias — a handler receives the PlannedEffect and the full
# DecisionResult and returns None.  Any exception propagates to dispatch().
EffectHandler = Callable[["PlannedEffect", "DecisionResult"], None]


class EffectDispatchError(RuntimeError):
    """Raised when dispatch() encounters an unregistered effect_type.

    Fail-loud: an unregistered effect type indicates a contract violation
    between the decision pipeline and the effect bus — silent skipping
    would produce invisible data loss (e.g. a governance decision never
    recorded to the DB).
    """


class TitanEffectBus:
    """Dispatch PlannedEffects to registered handlers (ADR-0058 Phase B).

    Construction (composition root)::

        bus = TitanEffectBus(
            handlers={
                EFFECT_RECORD_OUTCOME: _make_record_outcome_handler(outcome_tracker, trace_extractor),
                EFFECT_SEND_TELEGRAM:  _make_send_telegram_handler(telegram),
            },
            before_dispatch=_make_degraded_hook(tracker, garmin, telegram),
        )

    The bus is then injected into DailyCoach::

        coach = DailyCoach(..., effect_bus=bus)

    DailyCoach._effect_runner becomes::

        def _effect_runner(self, result: DecisionResult) -> bool:
            return self._effect_bus.dispatch(result)
    """

    def __init__(
        self,
        handlers: dict[str, EffectHandler],
        before_dispatch: Callable[[DecisionResult], None] | None = None,
    ) -> None:
        """
        Args:
            handlers: mapping of effect_type → handler callable.
                      Keys should be the EFFECT_* constants from contracts.py.
            before_dispatch: optional lifecycle hook called once before the
                             effect loop.  Used for degraded-mode tracker
                             update (T2-13 / ADR-0050).  Defaults to no-op.
        """
        self._handlers: dict[str, EffectHandler] = dict(handlers)
        self._before_dispatch: Callable[[DecisionResult], None] = (
            before_dispatch if before_dispatch is not None else lambda _: None
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def dispatch(self, result: DecisionResult) -> bool:
        """Execute all planned effects in order.

        1. Calls before_dispatch(result) once (lifecycle hook).
        2. Iterates result.planned_effects and calls the registered handler
           for each effect_type.
        3. Returns True if all effects succeeded without raising.

        Raises:
            EffectDispatchError: if an effect_type has no registered handler.
            Any exception raised by a handler propagates immediately —
            the bus does not swallow handler errors.

        Returns:
            True if all effects dispatched successfully.
            False if any effect returned a falsey result via the
            SEND_TELEGRAM handler sentinel (delivery failure, not exception).
        """
        self._before_dispatch(result)

        success = True
        for effect in result.planned_effects:
            handler = self._handlers.get(effect.effect_type)
            if handler is None:
                raise EffectDispatchError(
                    f"No handler registered for effect_type={effect.effect_type!r}. "
                    f"Registered types: {sorted(self._handlers)}. "
                    "Add a handler at construction time or add the effect_type "
                    "to contracts.py and ADR-0058."
                )
            outcome = handler(effect, result)
            # Handlers that return False signal a non-exception delivery failure
            # (e.g. Telegram returned falsey without raising).
            if outcome is False:
                success = False

        return success

    def register(self, effect_type: str, handler: EffectHandler) -> None:
        """Register or replace a handler for the given effect_type.

        Use at construction time only.  Runtime re-registration is
        permitted but should be treated as a test-only escape hatch.
        """
        self._handlers[effect_type] = handler

    # ------------------------------------------------------------------
    # Composition helpers — wired by the composition root
    # ------------------------------------------------------------------

    @staticmethod
    def make_degraded_hook(
        tracker: object,
        garmin: object,
        telegram: object,
    ) -> Callable[[DecisionResult], None]:
        """Build the before_dispatch lifecycle hook for degraded-mode tracking.

        Preserves the exact flag set and alert_fn contract from the original
        DailyCoach._effect_runner degraded-mode block (T2-13 / ADR-0050).

        Args:
            tracker:  DegradedModeTracker instance.
            garmin:   GarminSync instance (provides is_api_degraded property).
            telegram: TitanTelegramBot instance (provides send_alert method).
        """

        def hook(result: DecisionResult) -> None:
            trace = result.decision_trace
            tracker.update(  # type: ignore[union-attr]
                flags={
                    "persistence_degraded": bool(trace.get("persistence_degraded", False)),
                    "data_confidence_low": bool(trace.get("data_confidence_low", False)),
                    "garmin_data_stale": bool(trace.get("garmin_data_stale", False)),
                    "garmin_api_degraded": bool(
                        getattr(garmin, "is_api_degraded", False)
                    ),
                },
                alert_fn=lambda msg: telegram.send_alert(msg),  # type: ignore[union-attr]
            )

        return hook

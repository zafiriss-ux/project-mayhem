"""Shared ML safety controls for Phase 7 rollout.

The kill-switch is intentionally default-ON so any future athlete-facing
activation path must explicitly disable it in controlled environments.
"""

from dataclasses import dataclass

from titan.config.settings import get_settings

MODULE_VERSION = "1.0.0"


@dataclass(frozen=True)
class ExplainableOutput:
    """Deterministic explainability payload for advisory ML outputs."""

    top_feature_contributions: tuple[tuple[str, float], tuple[str, float], tuple[str, float]]
    confidence_range: tuple[float, float]
    plain_text_reason: str
    data_freshness_ok: bool


# Explicit whitelist of values that turn the kill-switch OFF (ML enabled).
# Any unrecognised value keeps the kill-switch ON — fail-safe by design.
_KILL_SWITCH_DISABLED_VALUES: frozenset[str] = frozenset({"0", "off", "false", "no"})


def is_ml_kill_switch_enabled() -> bool:
    """Return True when ML athlete-facing paths must be blocked.

    Kill-switch is ON by default (env default "1").  Only an explicit value
    from *_KILL_SWITCH_DISABLED_VALUES* turns it off.  Unknown or typo values
    leave the kill-switch ON (conservative fail-safe).
    """
    value = get_settings().TITAN_ML_KILL_SWITCH.strip().lower()
    return value not in _KILL_SWITCH_DISABLED_VALUES


def enforce_ml_kill_switch(path_name: str, athlete_facing: bool) -> None:
    """Block athlete-facing ML execution while kill-switch is enabled."""
    if athlete_facing and is_ml_kill_switch_enabled():
        raise RuntimeError(f"ML kill-switch active: athlete-facing path blocked for {path_name}")

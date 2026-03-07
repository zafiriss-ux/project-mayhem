"""Shared ML safety controls for Phase 7 rollout.

The kill-switch is intentionally default-ON so any future athlete-facing
activation path must explicitly disable it in controlled environments.
"""

import os

MODULE_VERSION = "1.0.0"


def is_ml_kill_switch_enabled() -> bool:
    """Return True when ML athlete-facing paths must be blocked."""
    value = os.getenv("TITAN_ML_KILL_SWITCH", "1").strip().lower()
    return value not in {"0", "off", "false", "no"}


def enforce_ml_kill_switch(path_name: str, athlete_facing: bool) -> None:
    """Block athlete-facing ML execution while kill-switch is enabled."""
    if athlete_facing and is_ml_kill_switch_enabled():
        raise RuntimeError(f"ML kill-switch active: athlete-facing path blocked for {path_name}")

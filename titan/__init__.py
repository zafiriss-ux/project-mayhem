"""
TITAN OS — Training Intelligence & Adaptive Networking

Closed-Loop Sovereign Training System for Endurance Athletes.

Architecture Layers:
  Core        — Database, athlete profiles, data persistence
  Science     — HRV, TSB, CS, glycogen, autonomic fusion, governance
  Integration — Garmin sync, Telegram bot, weather API
  Orchestration — Daily coach, weekly planner, optimal time calculator

The version lives only in pyproject.toml (AGENTS RE-01).
"""


def _read_version() -> str:
    """Installed package metadata first; else pyproject.toml next to the source (Docker, checkout)."""
    from importlib import metadata

    try:
        return metadata.version("project-mayhem")
    except metadata.PackageNotFoundError:
        pass
    import tomllib
    from pathlib import Path

    try:
        with (Path(__file__).resolve().parents[1] / "pyproject.toml").open("rb") as fh:
            return tomllib.load(fh)["project"]["version"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return "0+unknown"


__version__ = _read_version()

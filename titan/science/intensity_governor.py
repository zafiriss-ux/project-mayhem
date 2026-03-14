"""Intensity Governor — graduated GREEN/YELLOW/RED enforcement."""

from dataclasses import dataclass

from titan.config.thresholds import (
    INTENSITY_GOVERNOR_ACWR_RED,
    INTENSITY_GOVERNOR_ACWR_YELLOW,
    INTENSITY_GOVERNOR_DRIFT_RED,
    INTENSITY_GOVERNOR_DRIFT_YELLOW,
    INTENSITY_GOVERNOR_GLYCOGEN_RED,
    INTENSITY_GOVERNOR_GLYCOGEN_YELLOW,
    INTENSITY_GOVERNOR_READINESS_RED,
    INTENSITY_GOVERNOR_READINESS_YELLOW,
)

MODULE_VERSION = "1.0.0"


@dataclass
class GateResult:
    color: str
    max_zone: int
    volume_modifier: float
    session_override: str | None
    triggered_signals: list[str]
    audit: dict


class IntensityGovernor:
    """Aggregate advisory signals into a governance-ready gate decision."""

    def _color_drift(self, value: float) -> str:
        if value > INTENSITY_GOVERNOR_DRIFT_RED:
            return "RED"
        if value > INTENSITY_GOVERNOR_DRIFT_YELLOW:
            return "YELLOW"
        return "GREEN"

    def _color_glycogen(self, value: float) -> str:
        if value > INTENSITY_GOVERNOR_GLYCOGEN_RED:
            return "RED"
        if value >= INTENSITY_GOVERNOR_GLYCOGEN_YELLOW:
            return "YELLOW"
        return "GREEN"

    def _color_fatigue(self, value: str) -> str:
        normalized = str(value or "").upper()
        if normalized == "HIGH":
            return "RED"
        if normalized == "MEDIUM":
            return "YELLOW"
        return "GREEN"

    def _color_acwr(self, value: float) -> str:
        if value > INTENSITY_GOVERNOR_ACWR_RED:
            return "RED"
        if value > INTENSITY_GOVERNOR_ACWR_YELLOW:
            return "YELLOW"
        return "GREEN"

    def _color_readiness(self, value: float) -> str:
        if value < INTENSITY_GOVERNOR_READINESS_RED:
            return "RED"
        if value < INTENSITY_GOVERNOR_READINESS_YELLOW:
            return "YELLOW"
        return "GREEN"

    def evaluate(self, signals: dict) -> GateResult:
        signals = signals or {}
        audit: dict = {}
        triggered_signals: list[str] = []

        def evaluate_numeric(key: str, signal_key: str, yellow: float, red: float, color_fn):
            if signal_key not in signals:
                return
            value = signals.get(signal_key)
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                numeric = 0.0
            color = color_fn(numeric)
            audit[key] = {
                "value": numeric,
                "signal_color": color,
                "threshold_yellow": yellow,
                "threshold_red": red,
            }
            if color in {"YELLOW", "RED"}:
                triggered_signals.append(key)

        evaluate_numeric(
            "drift",
            "drift_pct",
            INTENSITY_GOVERNOR_DRIFT_YELLOW,
            INTENSITY_GOVERNOR_DRIFT_RED,
            self._color_drift,
        )
        evaluate_numeric(
            "glycogen_debt",
            "glycogen_debt",
            INTENSITY_GOVERNOR_GLYCOGEN_YELLOW,
            INTENSITY_GOVERNOR_GLYCOGEN_RED,
            self._color_glycogen,
        )
        evaluate_numeric(
            "acwr",
            "acwr",
            INTENSITY_GOVERNOR_ACWR_YELLOW,
            INTENSITY_GOVERNOR_ACWR_RED,
            self._color_acwr,
        )
        evaluate_numeric(
            "readiness",
            "readiness_score",
            INTENSITY_GOVERNOR_READINESS_YELLOW,
            INTENSITY_GOVERNOR_READINESS_RED,
            self._color_readiness,
        )

        if "fatigue_level" in signals:
            fatigue_value = str(signals.get("fatigue_level", "")).upper()
            fatigue_color = self._color_fatigue(fatigue_value)
            audit["fatigue"] = {
                "value": fatigue_value,
                "signal_color": fatigue_color,
                "threshold_yellow": "MEDIUM",
                "threshold_red": "HIGH",
            }
            if fatigue_color in {"YELLOW", "RED"}:
                triggered_signals.append("fatigue")

        signal_colors = [
            entry["signal_color"]
            for entry in audit.values()
            if isinstance(entry, dict) and "signal_color" in entry
        ]
        if "RED" in signal_colors:
            aggregate = "RED"
        elif "YELLOW" in signal_colors:
            aggregate = "YELLOW"
        else:
            aggregate = "GREEN"

        planned_session = str(signals.get("planned_session", "") or "").upper()
        if aggregate == "GREEN":
            max_zone = 5
            volume_modifier = 1.0
            session_override = None
        elif aggregate == "YELLOW":
            max_zone = 3
            volume_modifier = 0.8
            session_override = "TEMPO" if planned_session in {"HAMMER", "RACE"} else None
        else:
            max_zone = 2
            volume_modifier = 0.0
            session_override = "EASY"

        audit["aggregate"] = aggregate
        audit["triggered_signals"] = list(triggered_signals)
        audit["applied_constraints"] = {
            "max_zone": max_zone,
            "volume_modifier": volume_modifier,
            "session_override": session_override,
        }

        return GateResult(
            color=aggregate,
            max_zone=max_zone,
            volume_modifier=volume_modifier,
            session_override=session_override,
            triggered_signals=list(triggered_signals),
            audit=audit,
        )

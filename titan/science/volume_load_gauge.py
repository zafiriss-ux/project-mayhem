"""Volume Load Gauge (VLG) — pure aggregation over TSB, ACWR and glycogen."""

import math
from dataclasses import dataclass

from titan.config.thresholds import HARD_STOP_TSB_FLOOR

MODULE_VERSION = "1.0.0"


@dataclass(frozen=True)
class VLGState:
    """Resolved load-gauge state used by downstream planners/gates."""

    color: str
    score: int
    components: dict[str, str]
    rationale: list[str]


class VolumeLoadGauge:
    """Stateless aggregator for TSB + ACWR + glycogen debt signals."""

    @staticmethod
    def _tsb_color(tsb_value: float) -> str:
        if not math.isfinite(tsb_value):
            return "RED"
        if tsb_value <= HARD_STOP_TSB_FLOOR:
            return "RED"
        if tsb_value <= -30:
            return "YELLOW"
        return "GREEN"

    @staticmethod
    def _acwr_color(acwr: float) -> str:
        if acwr > 1.5 or acwr < 0.7:
            return "RED"
        if acwr > 1.3 or acwr < 0.8:
            return "YELLOW"
        return "GREEN"

    @staticmethod
    def _glycogen_color(glycogen_debt: float) -> str:
        if not math.isfinite(glycogen_debt):
            return "RED"
        if glycogen_debt >= 7:
            return "RED"
        if glycogen_debt >= 4:
            return "YELLOW"
        return "GREEN"

    def resolve(self, tsb_value: float, acwr: float, glycogen_debt: float) -> VLGState:
        """Aggregate three inputs into a unified VLG state (GREEN/YELLOW/RED)."""
        tsb = float(tsb_value)
        try:
            acwr_value = float(1.0 if acwr is None else acwr)
        except (TypeError, ValueError):
            acwr_value = 1.0
        glycogen = float(glycogen_debt)

        components = {
            "tsb": self._tsb_color(tsb),
            "acwr": self._acwr_color(acwr_value),
            "glycogen": self._glycogen_color(glycogen),
        }

        red_count = sum(1 for c in components.values() if c == "RED")
        yellow_count = sum(1 for c in components.values() if c == "YELLOW")

        if red_count >= 1:
            color = "RED"
        elif yellow_count >= 1:
            color = "YELLOW"
        else:
            color = "GREEN"

        score = red_count * 2 + yellow_count

        rationale: list[str] = []
        if components["tsb"] != "GREEN":
            rationale.append(f"TSB={tsb:.1f} ({components['tsb']})")
        if components["acwr"] != "GREEN":
            rationale.append(f"ACWR={acwr_value:.2f} ({components['acwr']})")
        if components["glycogen"] != "GREEN":
            rationale.append(f"Glycogen debt={glycogen:.1f} ({components['glycogen']})")
        if not rationale:
            rationale.append("All load components within green operating range")

        return VLGState(color=color, score=score, components=components, rationale=rationale)

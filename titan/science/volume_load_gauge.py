"""Volume Load Gauge (VLG) — pure aggregation over TSB, ACWR and glycogen."""

from dataclasses import dataclass
from typing import Dict, List

from titan.config.thresholds import HARD_STOP_TSB_FLOOR


@dataclass(frozen=True)
class VLGState:
    """Resolved load-gauge state used by downstream planners/gates."""

    color: str
    score: int
    components: Dict[str, str]
    rationale: List[str]


class VolumeLoadGauge:
    """Stateless aggregator for TSB + ACWR + glycogen debt signals."""

    @staticmethod
    def _tsb_color(tsb_value: float) -> str:
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
        if glycogen_debt >= 7:
            return "RED"
        if glycogen_debt >= 4:
            return "YELLOW"
        return "GREEN"

    def resolve(self, tsb_value: float, acwr: float, glycogen_debt: float) -> VLGState:
        """Aggregate three inputs into a unified VLG state (GREEN/YELLOW/RED)."""
        tsb = float(tsb_value)
        acwr_value = float(acwr)
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

        rationale: List[str] = []
        if components["tsb"] != "GREEN":
            rationale.append(f"TSB={tsb:.1f} ({components['tsb']})")
        if components["acwr"] != "GREEN":
            rationale.append(f"ACWR={acwr_value:.2f} ({components['acwr']})")
        if components["glycogen"] != "GREEN":
            rationale.append(f"Glycogen debt={glycogen:.1f} ({components['glycogen']})")
        if not rationale:
            rationale.append("All load components within green operating range")

        return VLGState(color=color, score=score, components=components, rationale=rationale)

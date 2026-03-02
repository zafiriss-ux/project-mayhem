"""Operator Console services for Phase 6 dashboard workflows."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from titan.core.database import DatabaseManager


class OperatorConsoleService:
    """Read-only aggregations used by the Web UI / Operator Console."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def readiness_load_dashboard(self, limit: int = 90) -> Dict[str, Any]:
        """Build timeline + summary payload for readiness/load dashboard widgets."""
        decisions = self.db.get_governance_decisions(limit=limit)

        timeline: List[Dict[str, Any]] = [
            {
                "date": d["date"],
                "tsb": d["tsb_value"],
                "acwr": d["acwr"],
                "readiness_score": d["readiness_score"],
                "vlg_color": d["vlg_color"],
                "phase": d["phase"],
            }
            for d in decisions
        ]

        if not timeline:
            return {
                "timeline": [],
                "summary": {
                    "samples": 0,
                    "avg_readiness": None,
                    "avg_acwr": None,
                    "latest_vlg_color": None,
                    "vlg_distribution": {},
                },
            }

        samples = len(timeline)
        avg_readiness = round(sum(p["readiness_score"] for p in timeline) / samples, 2)
        avg_acwr = round(sum(p["acwr"] for p in timeline) / samples, 3)
        vlg_counts = dict(Counter(p["vlg_color"] for p in timeline))

        summary = {
            "samples": samples,
            "avg_readiness": avg_readiness,
            "avg_acwr": avg_acwr,
            "latest_vlg_color": timeline[-1]["vlg_color"],
            "vlg_distribution": vlg_counts,
        }

        return {"timeline": timeline, "summary": summary}

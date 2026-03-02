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

    def session_explorer(self, limit: int = 50) -> Dict[str, Any]:
        """Build payload for session log review and governance decision trail."""
        decisions = self.db.get_governance_decisions(limit=limit)

        sessions: List[Dict[str, Any]] = []
        for decision in decisions:
            trail = [
                {
                    "step": "planned",
                    "session_type": decision["session_planned"],
                },
                {
                    "step": "post_governance",
                    "session_type": decision["session_post_governance"],
                    "locks_applied": decision["locks_applied"],
                    "governance_clean": decision["governance_clean"],
                },
            ]
            if decision["outcome_session_type_actual"]:
                trail.append(
                    {
                        "step": "completed",
                        "session_type": decision["outcome_session_type_actual"],
                        "completed": decision["outcome_completed"],
                        "rpe": decision["outcome_rpe"],
                    }
                )

            sessions.append(
                {
                    "date": decision["date"],
                    "phase": decision["phase"],
                    "vlg_color": decision["vlg_color"],
                    "manual_annotation": decision["outcome_notes"],
                    "decision_trail": trail,
                }
            )

        summary = {
            "samples": len(sessions),
            "annotated_sessions": sum(1 for s in sessions if s["manual_annotation"]),
            "sessions_with_locks": sum(
                1
                for s in sessions
                if any(
                    step.get("locks_applied")
                    for step in s["decision_trail"]
                    if step["step"] == "post_governance"
                )
            ),
        }

        return {"sessions": sessions, "summary": summary}

    def add_manual_annotation(self, date: str, note: str) -> bool:
        """Persist manual note for a session explorer record."""
        return self.db.annotate_governance_outcome(date=date, note=note)

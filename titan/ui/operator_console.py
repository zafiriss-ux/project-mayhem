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

    def calibration_review(self, limit: int = 365) -> Dict[str, Any]:
        """Build calibration review payload for lock rates and promotion candidates."""
        decisions = self.db.get_governance_decisions(limit=limit)

        decided = [d for d in decisions if d["outcome_completed"] is not None]
        if not decided:
            return {
                "summary": {
                    "samples": 0,
                    "governance_lock_rate": None,
                    "lock_rate_by_phase": {},
                },
                "heuristic_promotion_candidates": [],
                "moderate_promotion_candidates": [],
            }

        lock_rate_by_phase: Dict[str, float] = {}
        phases = sorted({d["phase"] for d in decided})
        for phase in phases:
            phase_rows = [d for d in decided if d["phase"] == phase]
            lock_rate_by_phase[phase] = round(
                sum(1 for d in phase_rows if not d["governance_clean"]) / len(phase_rows), 3
            )

        locks = sorted({lock for d in decided for lock in d["locks_applied"]})
        correlations: Dict[str, Dict[str, Any]] = {}
        for lock in locks:
            with_lock = [d for d in decided if lock in d["locks_applied"]]
            without_lock = [d for d in decided if lock not in d["locks_applied"]]
            if len(with_lock) < 3 or len(without_lock) < 3:
                continue

            completion_with = sum(1 for d in with_lock if d["outcome_completed"]) / len(with_lock)
            completion_without = (
                sum(1 for d in without_lock if d["outcome_completed"]) / len(without_lock)
            )
            correlations[lock] = {
                "n_with_lock": len(with_lock),
                "n_without_lock": len(without_lock),
                "completion_delta_pp": round((completion_with - completion_without) * 100, 1),
                "phases": sorted({d["phase"] for d in with_lock}),
            }

        heuristic_candidates = []
        heuristic_lock_map = {
            "READINESS_2OF4_DOWNGRADE": "SUBJECTIVE_FATIGUE_2OF4",
            "HARD_STOP_SAFETY_GATES": "HARD_STOP_TSB_FLOOR",
            "VO2_ELIGIBILITY_GATE": "VO2_READINESS_MIN",
        }
        for lock, parameter in heuristic_lock_map.items():
            metrics = correlations.get(lock)
            if not metrics:
                continue
            if (
                metrics["n_with_lock"] >= 5
                and metrics["n_without_lock"] >= 5
                and abs(metrics["completion_delta_pp"]) >= 8.0
            ):
                heuristic_candidates.append(
                    {
                        "parameter": parameter,
                        "trigger_lock": lock,
                        "n_with_lock": metrics["n_with_lock"],
                        "n_without_lock": metrics["n_without_lock"],
                        "completion_delta_pp": metrics["completion_delta_pp"],
                    }
                )

        moderate_candidates = []
        moderate_lock_map = {
            "HARD_STOP_SAFETY_GATES": "HARD_STOP_HRV_DELTA",
            "VO2_ELIGIBILITY_GATE": "VO2_GLYCOGEN_DEBT_MAX",
        }
        for lock, parameter in moderate_lock_map.items():
            metrics = correlations.get(lock)
            if not metrics:
                continue
            if (
                metrics["n_with_lock"] >= 8
                and metrics["n_without_lock"] >= 8
                and abs(metrics["completion_delta_pp"]) >= 10.0
                and len(metrics["phases"]) >= 2
            ):
                moderate_candidates.append(
                    {
                        "parameter": parameter,
                        "trigger_lock": lock,
                        "n_with_lock": metrics["n_with_lock"],
                        "n_without_lock": metrics["n_without_lock"],
                        "completion_delta_pp": metrics["completion_delta_pp"],
                        "phase_replication_count": len(metrics["phases"]),
                    }
                )

        return {
            "summary": {
                "samples": len(decided),
                "governance_lock_rate": round(
                    sum(1 for d in decided if not d["governance_clean"]) / len(decided), 3
                ),
                "lock_rate_by_phase": lock_rate_by_phase,
            },
            "heuristic_promotion_candidates": sorted(
                heuristic_candidates,
                key=lambda item: abs(item["completion_delta_pp"]),
                reverse=True,
            ),
            "moderate_promotion_candidates": sorted(
                moderate_candidates,
                key=lambda item: abs(item["completion_delta_pp"]),
                reverse=True,
            ),
        }

"""Operator Console services for Phase 6 dashboard workflows."""

from collections import Counter
from typing import Any

from titan.config.thresholds import (
    GARMIN_DATA_MAX_AGE_HOURS,
    OPERATOR_TRUST_DRIFT_WARNING_RATE_30D,
)
from titan.core.database import DatabaseManager


class OperatorConsoleService:
    """Read-only aggregations used by the Web UI / Operator Console."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    @staticmethod
    def _compute_override_metrics(decisions: list[dict[str, Any]], window_days: int = 30) -> dict[str, Any]:
        window = decisions[-window_days:] if decisions else []
        if not window:
            return {
                "window_days": window_days,
                "samples": 0,
                "override_rate_30d": 0.0,
                "trend": "stable",
                "trust_signal": "STABLE",
                "operator_trust_drift_warning": False,
            }

        overrides = [
            d
            for d in window
            if d.get("outcome_session_type_actual")
            and str(d.get("outcome_session_type_actual", "")).upper()
            != str(d.get("session_post_governance", "")).upper()
        ]
        override_rate = len(overrides) / len(window)

        split = max(1, len(window) // 2)
        early = window[:split]
        late = window[split:]

        def _rate(rows: list[dict[str, Any]]) -> float:
            if not rows:
                return 0.0
            mismatches = sum(
                1
                for d in rows
                if d.get("outcome_session_type_actual")
                and str(d.get("outcome_session_type_actual", "")).upper()
                != str(d.get("session_post_governance", "")).upper()
            )
            return mismatches / len(rows)

        early_rate = _rate(early)
        late_rate = _rate(late)
        trend_delta = round((late_rate - early_rate) * 100, 1)
        if trend_delta > 5.0:
            trend = "up"
        elif trend_delta < -5.0:
            trend = "down"
        else:
            trend = "stable"

        warning = override_rate > OPERATOR_TRUST_DRIFT_WARNING_RATE_30D
        trust_signal = "DRIFT_WARNING" if warning else "STABLE"

        return {
            "window_days": window_days,
            "samples": len(window),
            "override_rate_30d": round(override_rate, 3),
            "trend": trend,
            "trust_signal": trust_signal,
            "operator_trust_drift_warning": warning,
        }

    def readiness_load_dashboard(
        self,
        limit: int = 90,
        *,
        garmin_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build timeline + summary payload for readiness/load dashboard widgets.

        Args:
            limit: Maximum number of governance decisions to include in the timeline.
            garmin_state: Optional Garmin sync state dict for the dashboard indicator
                (ADR-0050 D2).  Expected keys: ``is_degraded`` (bool),
                ``has_baseline`` (bool), ``data_age_hours`` (float | None),
                ``trust_level`` (str), ``last_successful_sync_at`` (str | None).
                When omitted the indicator is absent (None).
        """
        decisions = self.db.get_governance_decisions(limit=limit)

        # Compute Garmin degradation indicator (ADR-0050 D2).
        garmin_degradation_indicator: str | None = None
        if garmin_state is not None:
            _ind = self.garmin_sync_indicator(
                is_degraded=bool(garmin_state.get("is_degraded", False)),
                has_baseline=bool(garmin_state.get("has_baseline", False)),
                data_age_hours=garmin_state.get("data_age_hours"),
                trust_level=str(garmin_state.get("trust_level", "TRUSTED")),
                last_successful_sync_at=garmin_state.get("last_successful_sync_at"),
            )
            if _ind["visible"]:
                garmin_degradation_indicator = _ind["message"]

        timeline: list[dict[str, Any]] = [
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
                "garmin_degradation_indicator": garmin_degradation_indicator,
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

        return {
            "timeline": timeline,
            "summary": summary,
            "garmin_degradation_indicator": garmin_degradation_indicator,
        }

    def session_explorer(self, limit: int = 50) -> dict[str, Any]:
        """Build payload for session log review and governance decision trail."""
        decisions = self.db.get_governance_decisions(limit=limit)

        sessions: list[dict[str, Any]] = []
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

            session_payload = {
                "date": decision["date"],
                "phase": decision["phase"],
                "vlg_color": decision["vlg_color"],
                "manual_annotation": decision["outcome_notes"],
                "decision_trail": trail,
                "gate_findings": [
                    {"gate": lock, "status": "TRIGGERED"} for lock in decision["locks_applied"]
                ],
            }

            explainability = decision.get("injury_risk_explainability")
            if isinstance(explainability, dict):
                session_payload["injury_risk_explainability"] = {
                    "plain_text_reason": explainability.get("plain_text_reason", ""),
                    "top_feature_contributions": explainability.get("top_feature_contributions", []),
                }

            sessions.append(session_payload)

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

    def manual_override_workflow(self, limit: int = 50, days: int = 14) -> dict[str, Any]:
        """Build payload for manual override review + audit trail visibility."""
        overrides = self.db.get_override_log(limit=limit)

        summary = {
            "samples": len(overrides),
            "override_ratio_window_days": days,
            "override_ratio": self.db.get_override_ratio(days=days),
        }
        if overrides:
            summary["latest_override_date"] = overrides[-1]["date"]
        else:
            summary["latest_override_date"] = None

        decisions = self.db.get_governance_decisions(limit=max(days * 4, 120))
        override_metrics = self._compute_override_metrics(decisions, window_days=30)

        return {
            "summary": summary,
            "overrides": overrides,
            "override_metrics": override_metrics,
        }

    def record_manual_override(
        self,
        date: str,
        prescribed_type: str,
        actual_type: str,
        reason: str = "",
    ) -> bool:
        """Persist a manual override row for the operator audit trail."""
        self.db.log_override(
            date=date,
            prescribed=prescribed_type,
            actual=actual_type,
            reason=reason,
        )
        return True

    @staticmethod
    def garmin_sync_indicator(
        *,
        is_degraded: bool,
        has_baseline: bool,
        data_age_hours: float | None,
        trust_level: str,
        last_successful_sync_at: str | None,
        trusted_age_threshold_hours: float = GARMIN_DATA_MAX_AGE_HOURS,
    ) -> dict[str, Any]:
        """Build the Garmin sync indicator payload for the coach dashboard.

        Implements the three-state indicator wording from ADR-0050 D2.

        Appearance condition (indicator shown when either holds):
          - ``is_degraded`` is True (active garmin_api_degraded event)
          - ``trust_level`` is ``"SUSPECT"`` or ``"INVALID"``

        Clear condition (all three required):
          1. ``is_degraded`` is False
          2. ``trust_level`` is ``"TRUSTED"``
          3. ``data_age_hours`` is within ``trusted_age_threshold_hours``

        Returns a dict with ``visible`` (bool) and ``message`` (str | None).
        """
        age_stale = data_age_hours is None or data_age_hours > trusted_age_threshold_hours
        trust_degraded = trust_level in ("SUSPECT", "INVALID")

        # Clear condition: all three must hold simultaneously.
        all_clear = (
            not is_degraded
            and not trust_degraded
            and not age_stale
        )
        if all_clear:
            return {"visible": False, "message": None}

        # Select wording state per ADR-0050 D2.
        if is_degraded:
            if has_baseline and last_successful_sync_at is not None and data_age_hours is not None:
                age_h = round(data_age_hours, 1)
                message = f"Garmin sync degraded — last valid data: {age_h}h ago."
            else:
                message = "Garmin sync degraded — no valid Garmin baseline available."
        elif trust_level == "INVALID":
            message = "Garmin data invalid/stale — conservative coaching mode expected."
        else:
            # trust_level == "SUSPECT" or age stale
            message = "Garmin data stale — operating with caution."

        return {"visible": True, "message": message}

    def calibration_review(self, limit: int = 365) -> dict[str, Any]:
        """Build calibration review payload for lock rates and promotion candidates."""
        ml_promotion_readiness = {
            "stage_target": "Stage 1+",
            "status": "REVIEW_REQUIRED",
            "engines": [
                {
                    "engine": "LoadPredictionShadowModel",
                    "promotion_gate": "at least 30 predictions with RMSE < 10% of actual",
                },
                {
                    "engine": "InjuryRiskEnsembleModel",
                    "promotion_gate": "recall >= 0.80 and false_positive_rate < 0.30 on holdout",
                },
                {
                    "engine": "AutomatedPeriodizationEngine",
                    "promotion_gate": "at least 10 confirmed suggestions with adoption_rate >= 0.80",
                },
            ],
            "required_controls": [
                "ADR updated with evidence_label upgrade HEURISTIC -> MODERATE",
                "deployment docs set TITAN_ML_KILL_SWITCH=0 explicitly",
                "Operator Console calibration review marked promotion-ready",
            ],
        }

        decisions = self.db.get_governance_decisions(limit=limit)

        decided = [d for d in decisions if d["outcome_completed"] is not None]
        if not decided:
            return {
                "summary": {
                    "samples": 0,
                    "governance_lock_rate": None,
                    "lock_rate_by_phase": {},
                },
                "ml_promotion_readiness": ml_promotion_readiness,
                "heuristic_promotion_candidates": [],
                "moderate_promotion_candidates": [],
            }

        lock_rate_by_phase: dict[str, float] = {}
        phases = sorted({d["phase"] for d in decided})
        for phase in phases:
            phase_rows = [d for d in decided if d["phase"] == phase]
            lock_rate_by_phase[phase] = round(
                sum(1 for d in phase_rows if not d["governance_clean"]) / len(phase_rows), 3
            )

        locks = sorted({lock for d in decided for lock in d["locks_applied"]})
        correlations: dict[str, dict[str, Any]] = {}
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
            "ml_promotion_readiness": ml_promotion_readiness,
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

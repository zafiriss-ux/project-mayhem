# ARCHITECTURE LOCK — see ADR-0009 before modifying
"""Governance Engine — intensity, readiness downgrade, and safety gates."""

import json
import logging
from dataclasses import asdict, is_dataclass
from typing import Any

from titan.config.thresholds import (
    HARD_STOP_HRV_DELTA,
    HARD_STOP_RHR_DELTA,
    HARD_STOP_TSB_FLOOR,
    SUBJECTIVE_FATIGUE_2OF4,
    SUBJECTIVE_FATIGUE_EXTREME,
    VO2_ACWR_MAX,
    VO2_ACWR_MIN,
    VO2_GLYCOGEN_DEBT_MAX,
    VO2_MIN_DAYS_SINCE_LAST,
    VO2_READINESS_MIN,
)
from titan.science.governance_contracts import validate_vo2_eligibility

_log = logging.getLogger(__name__)


def _gate_event(gate: str, action: str, **fields: Any) -> None:
    """Emit a structured governance gate event as a single log line."""
    _log.info(json.dumps({"governance_gate": gate, "action": action, **fields}, default=str))


class GovernanceEngine:
    OVERRIDE_LOCKDOWN_THRESHOLD: float = 0.80
    CS_CONFIDENCE_THRESHOLD: float = 0.70

    _QUALITY_SESSIONS = frozenset({"INTERVALS", "TEMPO", "RACE", "HAMMER"})
    _VO2_SESSIONS = frozenset({"HAMMER", "RACE"})

    _DOWNGRADE_MAP_2OF4 = {
        "INTERVALS": "TEMPO",
        "TEMPO": "EASY",
        "HAMMER": "EASY",
        "RACE": "TEMPO",
        "PROGRESSIVE": "EASY",
        "EASY": "EASY",
        "REST": "REST",
    }

    def check_override_lockdown(self, db: Any, threshold: float | None = None) -> dict:
        effective_threshold = (
            threshold if threshold is not None else self.OVERRIDE_LOCKDOWN_THRESHOLD
        )

        def _fail_safe(error_code: str, exc: BaseException) -> dict:
            _gate_event(
                "OVERRIDE_LOCKDOWN",
                "FAIL_SAFE_LOCK",
                cause="SYSTEM_ERROR",
                failure_class=error_code,
                error_class=exc.__class__.__name__,
                error_message=str(exc),
                component="check_override_lockdown",
                reason="Override lockdown read failure — applying conservative lockdown",
            )
            return {
                "locked": True,
                "ratio": None,
                "reason": (
                    "Override lockdown failure fallback (fail-safe): "
                    f"{error_code}. Zone 2 only until data path is healthy."
                ),
                "max_zone": 2,
                "disabled_sessions": list(self._QUALITY_SESSIONS),
                "action": "ZONE_2_ONLY",
                "error_code": error_code,
            }

        try:
            raw_ratio = db.get_override_ratio(days=14)
        except (AttributeError, LookupError, OSError, RuntimeError) as exc:
            error_code = "SCHEMA_MISMATCH" if "no such table" in str(exc).lower() else "DB_READ_ERROR"
            return _fail_safe(error_code, exc)

        try:
            ratio = float(raw_ratio)
        except (AttributeError, TypeError, ValueError, ZeroDivisionError) as exc:
            return _fail_safe("COMPUTATION_ERROR", exc)

        if ratio > effective_threshold:
            return {
                "locked": True,
                "ratio": ratio,
                "reason": (
                    f"Override ratio {ratio:.0%} (14d) > {effective_threshold:.0%} "
                    f"threshold — periodization integrity compromised"
                ),
                "max_zone": 2,
                "disabled_sessions": list(self._QUALITY_SESSIONS),
                "action": "ZONE_2_ONLY",
            }
        return {"locked": False, "ratio": ratio, "max_zone": 5, "disabled_sessions": []}

    def check_cs_confidence_lock(self, cs_tracker: Any, threshold: float | None = None) -> dict:
        effective_threshold = threshold if threshold is not None else self.CS_CONFIDENCE_THRESHOLD
        confidence = getattr(cs_tracker, "confidence", 1.0)
        if confidence < effective_threshold:
            return {
                "locked": True,
                "confidence": confidence,
                "reason": (
                    f"CS confidence {confidence:.0%} < {effective_threshold:.0%} — "
                    f"calibration time-trial required before race simulation"
                ),
                "required_session": "CS_CALIBRATION",
                "disabled": ["RACE_SIMULATION", "TTE_PREDICTION"],
            }
        return {"locked": False, "confidence": confidence}

    @staticmethod
    def _to_dict_maybe(value: Any) -> dict:
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        if is_dataclass(value):
            return asdict(value)
        return {
            "color": getattr(value, "color", "GREEN"),
            "max_zone": getattr(value, "max_zone", 5),
            "volume_modifier": getattr(value, "volume_modifier", 1.0),
            "session_override": getattr(value, "session_override", None),
            "triggered_signals": list(getattr(value, "triggered_signals", [])),
            "audit": getattr(value, "audit", {}),
        }

    def _evaluate_2of4_indicators(self, context: dict) -> tuple[int, list[str]]:
        indicators: list[str] = []

        today_hrv = context.get("today_hrv")
        baseline_hrv = context.get("baseline_hrv")
        hrv_std_dev = context.get("hrv_std_dev")
        hrv_soft = False
        if today_hrv is not None and baseline_hrv is not None and hrv_std_dev is not None:
            try:
                hrv_soft = float(today_hrv) < (float(baseline_hrv) - float(hrv_std_dev))
            except (TypeError, ValueError):
                hrv_soft = False
        else:
            hrv_soft = bool(context.get("hrv_soft_trigger", False))
        if hrv_soft:
            indicators.append("I1_hrv_soft")

        try:
            sleep_score = float(context.get("sleep_score", 100))
        except (TypeError, ValueError):
            sleep_score = 100
        if sleep_score < 60:
            indicators.append("I2_sleep")

        try:
            readiness_score = float(context.get("readiness_score", 100))
        except (TypeError, ValueError):
            readiness_score = 100
        if readiness_score < 50:
            indicators.append("I3_readiness")

        try:
            subjective_fatigue = int(context.get("subjective_fatigue_score", 0))
        except (TypeError, ValueError):
            subjective_fatigue = 0
        if subjective_fatigue >= SUBJECTIVE_FATIGUE_2OF4:
            indicators.append("I4_subjective")

        return len(indicators), indicators

    def _check_hard_stops(self, session_plan: dict, context: dict) -> list[dict]:
        """Evaluate hard-stop safety gates in DECISION_MODEL canonical order.

        Gate order (per DECISION_MODEL §4):
          H1 — Injury / Medical Flag (Gate 1: highest priority, non-bypassable)
          H2 — HRV Collapse (Gate 2a: independently sufficient for REST)
          H3 — RHR Spike   (Gate 2b: independently sufficient for REST)
          H4 — TSB Critical Floor (Gate 4: mandatory load reduction)
          H5 — Extreme Subjective Fatigue (Gate 3/aggregate contribution)

        H2 and H3 use OR semantics per DECISION_MODEL Gate 2:
          IF hrv_collapse OR rhr_collapse → RED hard stop
        Either signal alone is sufficient; dual collapse fires both.
        """
        reasons: list[dict] = []

        # H1 — Injury / Medical Flag (Gate 1: evaluated first, before all others)
        if bool(context.get("injury_flag", False)):
            session_plan["session_type"] = "REST"
            session_plan["max_zone"] = 1
            reason = "Active injury flag: no training permitted until cleared"
            session_plan["governance_override"] = reason
            reasons.append({"gate": "H1", "reason": reason})
            _gate_event("H1", "REST", reason=reason, cause="TRAINING_LOGIC")

        # H2 — HRV Collapse (Gate 2a: HRV drop alone sufficient — OR semantics)
        # Fires when drop >= HARD_STOP_HRV_DELTA (inclusive boundary).
        try:
            h2_trigger = (
                float(context.get("today_hrv"))
                <= float(context.get("baseline_hrv")) - HARD_STOP_HRV_DELTA
            )
        except (TypeError, ValueError):
            h2_trigger = False
        if h2_trigger:
            session_plan["session_type"] = "REST"
            session_plan["max_zone"] = 1
            reason = "HRV collapse: autonomic stress — hard stop"
            session_plan["governance_override"] = reason
            reasons.append({"gate": "H2", "reason": reason})
            _gate_event(
                "H2",
                "REST",
                reason=reason,
                cause="TRAINING_LOGIC",
                today_hrv=context.get("today_hrv"),
                baseline_hrv=context.get("baseline_hrv"),
            )

        # H3 — RHR Spike (Gate 2b: RHR spike alone sufficient — OR semantics)
        # Fires when rise >= HARD_STOP_RHR_DELTA (inclusive boundary).
        try:
            h3_trigger = (
                float(context.get("today_rhr"))
                >= float(context.get("baseline_rhr")) + HARD_STOP_RHR_DELTA
            )
        except (TypeError, ValueError):
            h3_trigger = False
        if h3_trigger:
            session_plan["session_type"] = "REST"
            session_plan["max_zone"] = 1
            reason = "RHR spike: autonomic stress — hard stop"
            session_plan["governance_override"] = reason
            reasons.append({"gate": "H3", "reason": reason})
            _gate_event(
                "H3",
                "REST",
                reason=reason,
                cause="TRAINING_LOGIC",
                today_rhr=context.get("today_rhr"),
                baseline_rhr=context.get("baseline_rhr"),
            )

        # Dual collapse: both H2 and H3 fired — set combined override message.
        if h2_trigger and h3_trigger:
            reason = "HRV/RHR dual collapse: autonomic stress — hard stop"
            session_plan["governance_override"] = reason
            _gate_event("H2+H3", "REST", reason=reason, cause="TRAINING_LOGIC")

        # H4 — TSB Critical Floor (Gate 4: load gate)
        try:
            tsb_value = float(context.get("tsb_value"))
        except (TypeError, ValueError):
            tsb_value = None
        if tsb_value is not None and tsb_value <= HARD_STOP_TSB_FLOOR:
            if str(session_plan.get("session_type", "EASY")).upper() in self._QUALITY_SESSIONS:
                session_plan["session_type"] = "EASY"
            reason = "TSB at overtraining threshold: mandatory load reduction"
            session_plan["governance_override"] = reason
            session_plan["max_zone"] = min(int(session_plan.get("max_zone", 5)), 2)
            reasons.append({"gate": "H4", "reason": reason})
            _gate_event("H4", "EASY", reason=reason, cause="TRAINING_LOGIC", tsb_value=tsb_value)

        # H5 — Extreme Subjective Fatigue
        try:
            subjective_fatigue = int(context.get("subjective_fatigue_score", 0))
        except (TypeError, ValueError):
            subjective_fatigue = 0
        if subjective_fatigue >= SUBJECTIVE_FATIGUE_EXTREME:
            if str(session_plan.get("session_type", "EASY")).upper() != "REST":
                session_plan["session_type"] = "EASY"
                session_plan["max_zone"] = min(int(session_plan.get("max_zone", 5)), 2)
            reason = "Athlete-reported extreme fatigue: session downgraded"
            session_plan["governance_override"] = reason
            reasons.append({"gate": "H5", "reason": reason})
            _gate_event(
                "H5",
                "EASY",
                reason=reason,
                cause="TRAINING_LOGIC",
                subjective_fatigue=subjective_fatigue,
            )

        return reasons

    def _check_vo2_eligibility(self, session_plan: dict, context: dict) -> dict | None:
        session_type = str(session_plan.get("session_type", "")).upper()
        zone = int(session_plan.get("zone", session_plan.get("max_zone", 0)) or 0)
        is_vo2_session = session_type in self._VO2_SESSIONS or (
            session_type == "INTERVALS" and zone == 5
        )
        if not is_vo2_session:
            return None

        acwr_raw = context.get("acwr", 1.0)
        readiness_raw = context.get("readiness_score", 100)
        glycogen_debt_raw = context.get("glycogen_debt", 0.0)
        fatigue_level_raw = context.get("fatigue_level", "LOW")
        days_since_last_vo2 = context.get("days_since_last_vo2")

        acwr_invalid = False
        try:
            acwr = float(1.0 if acwr_raw is None else acwr_raw)
        except (TypeError, ValueError):
            acwr = None
            acwr_invalid = True

        readiness_invalid = False
        try:
            readiness = float(100 if readiness_raw is None else readiness_raw)
        except (TypeError, ValueError):
            readiness = None
            readiness_invalid = True

        glycogen_debt_invalid = False
        try:
            glycogen_debt = float(0.0 if glycogen_debt_raw is None else glycogen_debt_raw)
        except (TypeError, ValueError):
            glycogen_debt = None
            glycogen_debt_invalid = True

        fatigue_level = str(fatigue_level_raw or "LOW").upper()
        valid_fatigue_levels = {"LOW", "MEDIUM", "HIGH"}
        fatigue_level_invalid = fatigue_level not in valid_fatigue_levels

        failed: list[str] = []
        reasons: list[str] = []
        details: list[dict[str, Any]] = []

        # V1: ACWR in [VO2_ACWR_MIN, VO2_ACWR_MAX]
        if acwr_invalid:
            failed.append("V1")
            reasons.append(f"ACWR must be numeric (actual: {acwr_raw!r})")
            details.append(
                {"code": "V1", "metric": "acwr", "operator": "numeric", "actual": acwr_raw}
            )
        elif not (VO2_ACWR_MIN <= acwr <= VO2_ACWR_MAX):
            failed.append("V1")
            reasons.append(f"ACWR in [{VO2_ACWR_MIN:.1f},{VO2_ACWR_MAX:.1f}] (actual: {acwr:.2f})")
            details.append(
                {
                    "code": "V1",
                    "metric": "acwr",
                    "operator": "between",
                    "min": VO2_ACWR_MIN,
                    "max": VO2_ACWR_MAX,
                    "actual": round(acwr, 2),
                }
            )

        # V2: readiness >= VO2_READINESS_MIN
        if readiness_invalid:
            failed.append("V2")
            reasons.append(f"readiness must be numeric (actual: {readiness_raw!r})")
            details.append(
                {
                    "code": "V2",
                    "metric": "readiness_score",
                    "operator": "numeric",
                    "actual": readiness_raw,
                }
            )
        elif readiness < VO2_READINESS_MIN:
            failed.append("V2")
            reasons.append(f"readiness >= {VO2_READINESS_MIN:.0f} (actual: {readiness:.0f})")
            details.append(
                {
                    "code": "V2",
                    "metric": "readiness_score",
                    "operator": ">=",
                    "threshold": VO2_READINESS_MIN,
                    "actual": round(readiness, 0),
                }
            )

        # V3: glycogen_debt < VO2_GLYCOGEN_DEBT_MAX
        if glycogen_debt_invalid:
            failed.append("V3")
            reasons.append(f"glycogen_debt must be numeric (actual: {glycogen_debt_raw!r})")
            details.append(
                {
                    "code": "V3",
                    "metric": "glycogen_debt",
                    "operator": "numeric",
                    "actual": glycogen_debt_raw,
                }
            )
        elif glycogen_debt >= VO2_GLYCOGEN_DEBT_MAX:
            failed.append("V3")
            reasons.append(
                f"glycogen_debt < {VO2_GLYCOGEN_DEBT_MAX:.1f} (actual: {glycogen_debt:.1f})"
            )
            details.append(
                {
                    "code": "V3",
                    "metric": "glycogen_debt",
                    "operator": "<",
                    "threshold": VO2_GLYCOGEN_DEBT_MAX,
                    "actual": round(glycogen_debt, 1),
                }
            )

        # V4: fatigue_level not HIGH
        if fatigue_level_invalid:
            failed.append("V4")
            reasons.append(
                f"fatigue_level must be one of LOW/MEDIUM/HIGH (actual: {fatigue_level_raw!r})"
            )
            details.append(
                {
                    "code": "V4",
                    "metric": "fatigue_level",
                    "operator": "in",
                    "allowed": ["LOW", "MEDIUM", "HIGH"],
                    "actual": fatigue_level_raw,
                }
            )
        elif fatigue_level == "HIGH":
            failed.append("V4")
            reasons.append(f"fatigue != HIGH (actual: {fatigue_level})")
            details.append(
                {
                    "code": "V4",
                    "metric": "fatigue_level",
                    "operator": "!=",
                    "threshold": "HIGH",
                    "actual": fatigue_level,
                }
            )

        # V5: days_since_last_vo2 >= VO2_MIN_DAYS_SINCE_LAST (only if provided)
        if days_since_last_vo2 is not None:
            try:
                days_val = int(days_since_last_vo2)
                days_invalid = False
            except (TypeError, ValueError):
                days_val = None
                days_invalid = True
            if days_invalid:
                failed.append("V5")
                reasons.append(
                    f"days_since_last_vo2 must be numeric (actual: {days_since_last_vo2!r})"
                )
                details.append(
                    {
                        "code": "V5",
                        "metric": "days_since_last_vo2",
                        "operator": "numeric",
                        "actual": days_since_last_vo2,
                    }
                )
            elif days_val < VO2_MIN_DAYS_SINCE_LAST:
                failed.append("V5")
                reasons.append(
                    f"days_since_last_vo2 >= {VO2_MIN_DAYS_SINCE_LAST} (actual: {days_val})"
                )
                details.append(
                    {
                        "code": "V5",
                        "metric": "days_since_last_vo2",
                        "operator": ">=",
                        "threshold": VO2_MIN_DAYS_SINCE_LAST,
                        "actual": days_val,
                    }
                )

        original = "INTERVALS_Z5" if session_type == "INTERVALS" and zone == 5 else session_type

        if failed:
            order = {"V1": 1, "V2": 2, "V3": 3, "V4": 4, "V5": 5}
            details = sorted(details, key=lambda item: order.get(str(item.get("code")), 999))
            failed = [item["code"] for item in details]
            session_plan["session_type"] = "TEMPO"
            result: dict[str, Any] = {
                "eligible": False,
                "failed_conditions": failed,
                "original_session": original,
                "downgraded_to": "TEMPO",
                "detailed_failed_conditions": details,
                "reason": "VO2max session requires: " + ", ".join(reasons),
            }
            _has_invalid_input = (
                acwr_invalid or readiness_invalid or glycogen_debt_invalid or fatigue_level_invalid
            )
            _gate_event(
                "VO2_ELIGIBILITY",
                "DOWNGRADE",
                original_session=original,
                downgraded_to="TEMPO",
                failed_conditions=failed,
                cause="DATA_PROBLEM" if _has_invalid_input else "TRAINING_LOGIC",
                input_flags={
                    "acwr_invalid": acwr_invalid,
                    "readiness_invalid": readiness_invalid,
                    "glycogen_debt_invalid": glycogen_debt_invalid,
                    "fatigue_level_invalid": fatigue_level_invalid,
                },
            )
            return result

        result = {
            "eligible": True,
            "failed_conditions": [],
            "original_session": original,
            "downgraded_to": None,
            "detailed_failed_conditions": [],
            "reason": "All VO2 eligibility conditions satisfied",
        }
        _gate_event("VO2_ELIGIBILITY", "PASS", original_session=original)
        return result

    def _check_fueling_gate(self, session_plan: dict, context: dict) -> dict | None:
        session_type = str(session_plan.get("session_type", "")).upper()
        duration = int(
            session_plan.get("duration_min", context.get("planned_duration_min", 0)) or 0
        )
        fueling_confirmed = bool(context.get("fueling_confirmed", False))

        if fueling_confirmed:
            return None

        if session_type in {"HAMMER", "RACE"}:
            session_plan["session_type"] = "TEMPO"
            result: dict[str, Any] = {
                "action": "LOCK",
                "phase": 3,
                "reason": f"{session_type} session without confirmed fueling: unsafe glycogen depletion risk",
                "original_session": session_type,
                "locked_to": "TEMPO",
            }
            _gate_event(
                "FUELING",
                "LOCK",
                phase=3,
                original_session=session_type,
                locked_to="TEMPO",
                duration_min=duration,
            )
            return result

        if session_type in {"TEMPO", "INTERVALS"} and duration >= 90:
            session_plan["session_type"] = "EASY"
            result = {
                "action": "LOCK",
                "phase": 2,
                "reason": f"Quality session {duration} min without confirmed fueling: mandatory fueling not met",
                "original_session": session_type,
                "locked_to": "EASY",
            }
            _gate_event(
                "FUELING",
                "LOCK",
                phase=2,
                original_session=session_type,
                locked_to="EASY",
                duration_min=duration,
            )
            return result

        if session_type == "LONG_RUN" and duration >= 90:
            session_plan["session_type"] = "PROGRESSIVE"
            result = {
                "action": "LOCK",
                "phase": 4,
                "reason": f"LONG_RUN {duration} min without confirmed fueling: long-run fueling is required",
                "original_session": "LONG_RUN",
                "locked_to": "PROGRESSIVE",
            }
            _gate_event(
                "FUELING",
                "LOCK",
                phase=4,
                original_session="LONG_RUN",
                locked_to="PROGRESSIVE",
                duration_min=duration,
            )
            return result

        if 60 <= duration <= 89 and session_type in {"TEMPO", "INTERVALS"}:
            result = {
                "action": "FLAG",
                "phase": 2,
                "reason": f"Quality session {duration} min without confirmed fueling: performance risk",
                "session_unchanged": True,
            }
            _gate_event(
                "FUELING", "FLAG", phase=2, session_type=session_type, duration_min=duration
            )
            return result

        if 60 <= duration <= 89 and session_type in {"EASY", "PROGRESSIVE"}:
            result = {
                "action": "FLAG",
                "phase": 1,
                "reason": f"{session_type} {duration} min without confirmed fueling: recommended but optional",
                "session_unchanged": True,
            }
            _gate_event(
                "FUELING", "FLAG", phase=1, session_type=session_type, duration_min=duration
            )
            return result

        return None

    def apply_constraints(self, session_plan: dict, context: dict) -> dict:
        db = context.get("db")
        cs_tracker = context.get("cs_tracker")
        afi_constr = context.get("afi_constraints", {})
        applied_locks: list[str] = []

        # APL injections — adaptive thresholds and gate priority vector.
        # If APL was not invoked upstream, these default to {} and all gate
        # checks fall back to their static class-level constants (no behaviour change).
        lock_thresholds = context.get("lock_thresholds", {})
        priority_vector = context.get("priority_vector", {})

        intensity_gate = self._to_dict_maybe(context.get("intensity_gate_result"))
        if intensity_gate:
            session_plan["intensity_gate_result"] = intensity_gate
            color = str(intensity_gate.get("color", "GREEN")).upper()
            session_plan["max_zone"] = min(
                int(session_plan.get("max_zone", 5) or 5),
                int(intensity_gate.get("max_zone", 5) or 5),
            )
            session_plan["volume_modifier"] = float(
                intensity_gate.get("volume_modifier", 1.0) or 1.0
            )
            override = intensity_gate.get("session_override")
            if override:
                session_plan["session_type"] = override
            if color == "RED":
                applied_locks.append("INTENSITY_GATE_RED")
            elif color == "YELLOW":
                applied_locks.append("INTENSITY_GATE_YELLOW")

        count_2of4, indicators = self._evaluate_2of4_indicators(context)
        if count_2of4 >= 2:
            original = str(session_plan.get("session_type", "EASY")).upper()
            downgraded = self._DOWNGRADE_MAP_2OF4.get(original, "EASY")
            session_plan["session_type"] = downgraded
            session_plan["downgrade_2of4"] = {
                "downgrade_2of4": True,
                "count": count_2of4,
                "indicators_triggered": indicators,
                "original_session": original,
                "downgraded_to": downgraded,
            }
            applied_locks.append("READINESS_2OF4_DOWNGRADE")
            _gate_event(
                "2OF4",
                "DOWNGRADE",
                cause="TRAINING_LOGIC",
                count=count_2of4,
                indicators=indicators,
                original=original,
                downgraded_to=downgraded,
            )

        hard_stop_reasons = self._check_hard_stops(session_plan, context)
        if hard_stop_reasons:
            session_plan["hard_stop_reasons"] = hard_stop_reasons
            applied_locks.append("HARD_STOP_SAFETY_GATES")

        vo2_result = self._check_vo2_eligibility(session_plan, context)
        if vo2_result is not None:
            violation = validate_vo2_eligibility(vo2_result)
            if violation:
                _log.error(
                    json.dumps(
                        {"governance_contract_violation": "vo2_eligibility", "detail": violation},
                        default=str,
                    )
                )
            session_plan["vo2_eligibility"] = vo2_result
            if not vo2_result.get("eligible", True):
                applied_locks.append("VO2_ELIGIBILITY_GATE")

        fueling_result = self._check_fueling_gate(session_plan, context)
        if fueling_result is not None:
            session_plan["fueling_gate"] = fueling_result
            if fueling_result.get("action") == "LOCK":
                applied_locks.append("FUELING_GATE_LOCK")
            else:
                applied_locks.append("FUELING_GATE_FLAG")

        para_guard = afi_constr.get("parasympathetic_guard", {})

        gate_order = {
            "PARASYMPATHETIC_GUARD": int(priority_vector.get("PARASYMPATHETIC_GUARD", 1) or 1),
            "OVERRIDE_LOCKDOWN": int(priority_vector.get("OVERRIDE_LOCKDOWN", 2) or 2),
            "CS_CONFIDENCE_LOCK": int(priority_vector.get("CS_CONFIDENCE_LOCK", 3) or 3),
        }

        for gate_name, _rank in sorted(gate_order.items(), key=lambda x: x[1]):
            if gate_name == "PARASYMPATHETIC_GUARD":
                if para_guard.get("triggered"):
                    session_plan["session_type"] = "EASY"
                    session_plan["max_zone"] = 2
                    session_plan["governance_override"] = para_guard["reason"]
                    applied_locks.append("PARASYMPATHETIC_GUARD")
                    _gate_event("PARASYMPATHETIC_GUARD", "EASY", reason=para_guard.get("reason"))
                continue

            if gate_name == "OVERRIDE_LOCKDOWN":
                if not db:
                    continue
                override_threshold = lock_thresholds.get("override_ratio_ceiling") or None
                lock = self.check_override_lockdown(db, threshold=override_threshold)
                if lock["locked"] and session_plan.get("session_type") in lock["disabled_sessions"]:
                    session_plan["session_type"] = "EASY"
                    session_plan["max_zone"] = lock["max_zone"]
                    session_plan["governance_override"] = lock["reason"]
                    applied_locks.append("OVERRIDE_LOCKDOWN")
                    _gate_event(
                        "OVERRIDE_LOCKDOWN",
                        "ZONE_2_ONLY",
                        cause="TRAINING_LOGIC",
                        ratio=lock.get("ratio"),
                        apl_threshold_override=override_threshold,
                    )
                continue

            if gate_name == "CS_CONFIDENCE_LOCK":
                if not cs_tracker:
                    continue
                cs_threshold = lock_thresholds.get("cs_min_confidence") or None
                cs_lock = self.check_cs_confidence_lock(cs_tracker, threshold=cs_threshold)
                if cs_lock["locked"]:
                    session_plan["cs_prediction_disabled"] = True
                    session_plan["required_calibration"] = True
                    session_plan["cs_lock_reason"] = cs_lock["reason"]
                    applied_locks.append("CS_CONFIDENCE_LOCK")
                    _gate_event(
                        "CS_CONFIDENCE_LOCK",
                        "CALIBRATION_REQUIRED",
                        cause="DATA_PROBLEM",
                        confidence=cs_lock.get("confidence"),
                        apl_threshold_override=cs_threshold,
                    )

        if bool(context.get("data_confidence_low", False)):
            current_session = str(session_plan.get("session_type", "EASY")).upper()
            if current_session not in {"REST", "EASY"}:
                session_plan["session_type"] = "EASY"
            session_plan["max_zone"] = min(int(session_plan.get("max_zone", 5) or 5), 2)
            applied_locks.append("STARTUP_DATA_CONFIDENCE_CEILING")
            _gate_event(
                "STARTUP_DATA_CONFIDENCE",
                "EASY_CEILING",
                cause="DATA_PROBLEM",
                original_session=current_session,
                downgraded_to=session_plan.get("session_type", "EASY"),
            )

        if bool(context.get("persistence_degraded", False)):
            current_session = str(session_plan.get("session_type", "EASY")).upper()
            if current_session not in {"REST", "EASY"}:
                session_plan["session_type"] = "EASY"
            session_plan["max_zone"] = min(int(session_plan.get("max_zone", 5) or 5), 2)
            applied_locks.append("PERSISTENCE_DEGRADED_CEILING")
            _gate_event(
                "PERSISTENCE_DEGRADED",
                "EASY_CEILING",
                cause="DATA_PROBLEM",
                original_session=current_session,
                downgraded_to=session_plan.get("session_type", "EASY"),
            )

        session_plan["governance_locks_applied"] = applied_locks
        session_plan["governance_clean"] = len(applied_locks) == 0

        _gate_event(
            "APPLY_CONSTRAINTS",
            "COMPLETE",
            final_session=session_plan.get("session_type"),
            locks_applied=applied_locks,
            governance_clean=session_plan["governance_clean"],
            priority_vector=priority_vector or None,
            apl_active=bool(priority_vector),
        )
        return session_plan

    def get_governance_report(
        self,
        db: Any | None = None,
        cs_tracker: Any | None = None,
        afi_constraints: dict | None = None,
    ) -> dict:
        return {
            "override_lockdown": self.check_override_lockdown(db) if db else {"locked": False},
            "cs_confidence_lock": self.check_cs_confidence_lock(cs_tracker)
            if cs_tracker
            else {"locked": False},
            "parasympathetic_guard": (afi_constraints or {}).get(
                "parasympathetic_guard", {"triggered": False}
            ),
        }

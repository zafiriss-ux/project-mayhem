# Gate parameters: see thresholds.py + evidence_registry.py.
# To change gate logic: (1) write ADR entry, (2) update evidence_registry.py,
# (3) update tests/test_governance_mutation.py. All three are required.
"""Governance Engine — intensity, readiness downgrade, and safety gates."""
from __future__ import annotations

import json
import logging
import math
from dataclasses import asdict, dataclass, is_dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from titan.science.threshold_adapter import ThresholdAdapter

from titan.config.thresholds import (
    CANONICAL_LOCK_CODES,
    DATA_VOID_THRESHOLD_HOURS,
    DATA_VOID_ZONE_CAP,
    GOVERNANCE_CS_CONFIDENCE_THRESHOLD,
    GOVERNANCE_DOWNGRADE_MAX_DURATION_MIN,
    GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD,
    HARD_STOP_HRV_DELTA,
    HARD_STOP_HRV_DROP_PCT,
    HARD_STOP_RHR_DELTA,
    HARD_STOP_TSB_FLOOR,
    ILLNESS_PATTERN_HRV_DELTA,
    ILLNESS_PATTERN_RHR_DELTA,
    INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE,
    SUBJECTIVE_FATIGUE_2OF4,
    SUBJECTIVE_FATIGUE_EXTREME,
    VO2_ACWR_MAX,
    VO2_ACWR_MIN,
    VO2_GLYCOGEN_DEBT_MAX,
    VO2_MIN_DAYS_SINCE_LAST,
    VO2_READINESS_MIN,
)
from titan.science.governance_contracts import validate_vo2_eligibility
from titan.science.override_signal import record_override_signal

MODULE_VERSION = "1.0.0"

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class GateFinding:
    gate: str
    status: str
    actual_value: float | str | None
    threshold_value: float | str | None
    margin: float | None
    reason: str


@dataclass(frozen=True)
class DecisionRationale:
    primary_reason: str
    actionable_guidance: str
    gate_findings: list[GateFinding]


GATE_RATIONALE_TEMPLATES: dict[str, str] = {
    "H1": "Injury flag active: full rest is required.",
    "H2": "HRV collapse crossed safety threshold ({actual} vs {threshold}, margin {margin}).",
    "H3": "RHR spike crossed safety threshold ({actual} vs {threshold}, margin {margin}).",
    "H4": "TSB dropped below critical floor ({actual} vs {threshold}, margin {margin}).",
    "H5": "Subjective fatigue reached extreme level ({actual} vs {threshold}, margin {margin}).",
    "READINESS_2OF4_DOWNGRADE": "At least 2 of 4 readiness indicators triggered; conservative downgrade applied.",
    "OVERRIDE_LOCKDOWN": "Manual override ratio exceeded safe ceiling; quality sessions are locked.",
    "CS_CONFIDENCE_LOCK": "Critical speed confidence below threshold; recalibration required.",
    "PARASYMPATHETIC_GUARD": "Parasympathetic guard triggered; high-intensity work blocked.",
    "VO2_ELIGIBILITY_GATE": "VO2 eligibility checks failed; intensity downgraded.",
    "FUELING_GATE_LOCK": "Fueling gate lock applied; session intensity reduced.",
    "FUELING_GATE_FLAG": "Fueling warning raised; proceed conservatively.",
    "STARTUP_DATA_CONFIDENCE_CEILING": "Startup confidence low; easy-ceiling safety mode applied.",
    "PERSISTENCE_DEGRADED_CEILING": "Persistence degraded; easy-ceiling safety mode applied.",
}

OVERRIDE_HANDLERS: dict[str, Any] = dict.fromkeys(CANONICAL_LOCK_CODES, record_override_signal)


def _gate_event(gate: str, action: str, **fields: Any) -> None:
    """Emit a structured governance gate event as a single log line."""
    _log.info(json.dumps({"governance_gate": gate, "action": action, **fields}, default=str))


class GovernanceEngine:
    OVERRIDE_LOCKDOWN_THRESHOLD: float = GOVERNANCE_OVERRIDE_LOCKDOWN_THRESHOLD
    CS_CONFIDENCE_THRESHOLD: float = GOVERNANCE_CS_CONFIDENCE_THRESHOLD

    _QUALITY_SESSIONS = frozenset({"INTERVALS", "TEMPO", "RACE", "HAMMER"})
    _VO2_SESSIONS = frozenset({"HAMMER", "RACE"})
    _REST_HARD_STOPS = frozenset({"H1", "H2", "H3", "H2_H3_NON_TRAINING_STRESS"})

    _DOWNGRADE_MAP_2OF4 = {
        "INTERVALS": "TEMPO",
        "TEMPO": "EASY",
        "HAMMER": "EASY",
        "RACE": "TEMPO",
        "PROGRESSIVE": "EASY",
        "EASY": "EASY",
        "REST": "REST",
    }

    def __init__(
        self,
        threshold_adapter: ThresholdAdapter | None = None,
        db: Any | None = None,
        athlete_id: str | None = None,
    ) -> None:
        """Initialise GovernanceEngine.

        Args:
            threshold_adapter: Optional per-athlete ThresholdAdapter injected by
                the coaching pipeline (ADR-0052). When None, all gate thresholds
                use unmodified constants from thresholds.py.
            db: Optional DatabaseManager for methods that need direct DB access
                (e.g. apply_override_lockdown). When None, those methods are no-ops.
            athlete_id: The athlete whose override ratio the lockdown reads when the
                context carries none (ADR-0068). Without one the lockdown fails closed.
        """
        self._threshold_adapter = threshold_adapter
        self._db = db
        self._athlete_id = athlete_id

    def _resolve_athlete_id(self, context: dict | None = None) -> str | None:
        """The context's athlete_id, else the engine's; None when neither is a non-empty str."""
        for candidate in ((context or {}).get("athlete_id"), self._athlete_id):
            if isinstance(candidate, str) and candidate.strip():
                return candidate
        return None

    def _get_soft_threshold(self, threshold_name: str, base_value: float) -> float:
        """Return the (possibly adapted) threshold value for soft gates.

        Hard-stop gates (H2–H5) must NEVER be routed through this helper —
        call the raw constant directly. This helper is safe only for soft gates
        (readiness floors, VO2 eligibility bounds, intensity governor bands, etc.).

        If no ThresholdAdapter is injected, returns base_value unchanged.
        """
        if self._threshold_adapter is not None:
            return self._threshold_adapter.get_threshold(threshold_name, base_value)
        return base_value

    def check_override_lockdown(
        self, db: Any, threshold: float | None = None, athlete_id: str | None = None,
    ) -> dict:
        """The athlete's own 14-day override lockdown (ADR-0068: no athlete_id → locked)."""
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

        if not (isinstance(athlete_id, str) and athlete_id.strip()):
            # ADR-0068 (SG-02): without an athlete the ratio would be the owner's
            # (repository default) — never read someone else's ratio, lock instead.
            return _fail_safe("ATHLETE_ID_MISSING", LookupError("governance context has no athlete_id"))

        try:
            raw_ratio = db.get_override_ratio(athlete_id=athlete_id, days=14)
        except (AttributeError, LookupError, OSError, RuntimeError, TypeError) as exc:
            error_code = "SCHEMA_MISMATCH" if "no such table" in str(exc).lower() else "DB_READ_ERROR"
            return _fail_safe(error_code, exc)

        if raw_ratio is None:
            # No outcome history — cold start. Default-deny: require calibration
            # before override-heavy behaviour (TD-03).
            _gate_event(
                "OVERRIDE_LOCKDOWN",
                "OVERRIDE_LOCKDOWN",
                cause="COLD_START",
                reason="no_outcome_history",
                gate_action="default_locked",
            )
            return {
                "locked": True,
                "ratio": None,
                "reason": "cold_start_no_history",
                "max_zone": 2,
                "disabled_sessions": list(self._QUALITY_SESSIONS),
                "action": "ZONE_2_ONLY",
            }

        try:
            ratio = float(raw_ratio)
        except (AttributeError, TypeError, ValueError, ZeroDivisionError) as exc:
            return _fail_safe("COMPUTATION_ERROR", exc)
        if not math.isfinite(ratio):
            return _fail_safe("COMPUTATION_ERROR", ValueError(f"non-finite override ratio {ratio!r}"))

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
        confidence = getattr(cs_tracker, "confidence", 0.0)
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

    def apply_override_lockdown(self, context: dict) -> None:
        """Evaluate override lockdown and mutate context with fail-closed None handling.

        Sets context["override_locked"] = True on cold start (ratio is None) or
        when ratio exceeds OVERRIDE_LOCKDOWN_THRESHOLD. Uses self._db set at construction.
        """
        session_plan = context.get("session_plan", {})
        db = self._db
        if db is None:
            return
        athlete_id = self._resolve_athlete_id(context)
        if athlete_id is None:
            # ADR-0068 (SG-02): no athlete → never the owner's ratio; fail closed.
            session_plan["lock_applied"] = True
            context["override_locked"] = True
            return
        try:
            ratio = db.get_override_ratio(athlete_id=athlete_id, days=14)
        except Exception:
            session_plan["lock_applied"] = True
            context["override_locked"] = True
            return
        if ratio is None:
            # Cold start — no calibration data.
            # Fail closed: treat as if lockdown threshold exceeded.
            _gate_event(
                "OVERRIDE_LOCKDOWN",
                "COLD_START_LOCKDOWN",
                reason="no_calibration_data",
            )
            session_plan["lock_applied"] = True
            context["override_locked"] = True
            return
        _ratio = float(ratio)
        if not math.isfinite(_ratio) or _ratio > self.OVERRIDE_LOCKDOWN_THRESHOLD:
            session_plan["lock_applied"] = True
            context["override_locked"] = True

    @staticmethod
    def _bounded_zone(value: Any, *, missing: int) -> int:
        """A zone in 1..5 (ADR-0068): None → ``missing``; non-numeric or non-finite → 2."""
        if value is None:
            return missing
        try:
            zone = float(value)
        except (TypeError, ValueError):
            return 2
        if not math.isfinite(zone):
            return 2
        return int(min(max(zone, 1.0), 5.0))

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
            sleep_score = float(context.get("sleep_score", 40))
            if not math.isfinite(sleep_score):
                sleep_score = 40
        except (TypeError, ValueError):
            sleep_score = 40
        if sleep_score < 60:
            indicators.append("I2_sleep")

        try:
            readiness_score = float(context.get("readiness_score", 40))
            if not math.isfinite(readiness_score):
                readiness_score = 40
        except (TypeError, ValueError):
            readiness_score = 40
        if readiness_score < 50:
            indicators.append("I3_readiness")

        try:
            subjective_fatigue = int(context.get("subjective_fatigue_score", 0))
        except (TypeError, ValueError, OverflowError):
            # Non-finite/non-numeric fatigue: H5_MISSING applies the ceiling (ADR-0068).
            subjective_fatigue = 0
        if subjective_fatigue >= SUBJECTIVE_FATIGUE_2OF4:
            indicators.append("I4_subjective")

        return len(indicators), indicators



    @staticmethod
    def h2_drop_threshold_ms(baseline_hrv: float) -> float:
        """The HRV drop in ms that fires H2: 15 ms or 30% of the baseline, whichever is smaller.

        ADR-0064 (SV-10). A non-positive baseline keeps the absolute 15 ms.
        """
        if baseline_hrv > 0:
            return min(HARD_STOP_HRV_DELTA, HARD_STOP_HRV_DROP_PCT * baseline_hrv)
        return HARD_STOP_HRV_DELTA

    @staticmethod
    def classify_hrv_stress_context(context: dict) -> str:
        """Classify H2/H3 stress source for explicit non-training safety handling."""
        try:
            _bhrv = float(context.get("baseline_hrv"))
            _thrv = float(context.get("today_hrv"))
            if not (math.isfinite(_bhrv) and math.isfinite(_thrv)):
                _gate_event("HRV_STRESS_CONTEXT", "NAN_REJECTED", reason="non-finite HRV input (INV-01)")
                hrv_delta = 0.0
            else:
                hrv_delta = _bhrv - _thrv
        except (TypeError, ValueError):
            _bhrv = 0.0
            hrv_delta = 0.0

        try:
            _trhr = float(context.get("today_rhr"))
            _brhr = float(context.get("baseline_rhr"))
            if not (math.isfinite(_trhr) and math.isfinite(_brhr)):
                _gate_event("HRV_STRESS_CONTEXT", "NAN_REJECTED", reason="non-finite RHR input (INV-01)")
                rhr_delta = 0.0
            else:
                rhr_delta = _trhr - _brhr
        except (TypeError, ValueError):
            rhr_delta = 0.0

        # ADR-0051: None/absent ACWR is missing safety-critical data — conservative fail.
        raw_acwr = context.get("acwr")
        if raw_acwr is None:
            return "UNKNOWN_ACWR"
        try:
            acwr = float(raw_acwr)
        except (TypeError, ValueError):
            return "UNKNOWN_ACWR"
        if not math.isfinite(acwr):
            _gate_event("HRV_STRESS_CONTEXT", "NAN_REJECTED", reason="non-finite ACWR input (INV-01)")
            return "UNKNOWN_ACWR"

        if acwr > VO2_ACWR_MAX:
            return "TRAINING_EXPLAINED"

        if hrv_delta >= ILLNESS_PATTERN_HRV_DELTA and rhr_delta >= ILLNESS_PATTERN_RHR_DELTA:
            return "ILLNESS_PATTERN"

        if hrv_delta >= GovernanceEngine.h2_drop_threshold_ms(_bhrv):
            return "UNEXPLAINED_MODERATE"

        return "TRAINING_EXPLAINED"

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
        _garmin_age = context.get("garmin_data_age_hours")
        _garmin_trust = context.get("garmin_data_trust_level", "UNKNOWN")

        # H1 — Injury / Medical Flag (Gate 1: evaluated first, before all others)
        if bool(context.get("injury_flag", False)):
            session_plan["session_type"] = "REST"
            session_plan["max_zone"] = 1
            reason = "Active injury flag: no training permitted until cleared"
            session_plan["governance_override"] = reason
            reasons.append({"gate": "H1", "reason": reason})
            _gate_event(
                "H1", "REST", reason=reason, cause="TRAINING_LOGIC",
                garmin_data_age_hours=_garmin_age, garmin_data_trust_level=_garmin_trust,
            )

        # H2 — HRV Collapse (Gate 2a: HRV drop alone sufficient — OR semantics)
        # Fires when drop >= 15 ms or 30% of baseline, whichever is smaller (inclusive; ADR-0064).
        h2_trigger = False
        _h2_missing = False
        try:
            _h2_today = float(context.get("today_hrv"))
            _h2_base = float(context.get("baseline_hrv"))
            if not (math.isfinite(_h2_today) and math.isfinite(_h2_base)):
                _gate_event("H2", "NAN_REJECTED",
                            reason="non-finite HRV input rejected (INV-01)",
                            garmin_data_age_hours=_garmin_age,
                            garmin_data_trust_level=_garmin_trust)
                # ADR-0068 (SG-07): non-finite HRV is missing HRV → H2_MISSING ceiling.
                _h2_missing = True
            elif _h2_base <= 0:
                # ADR-0068: a baseline of 0 or less is no baseline; it must not disable H2.
                _h2_missing = True
            else:
                h2_trigger = _h2_base - _h2_today >= self.h2_drop_threshold_ms(_h2_base)
        except (TypeError, ValueError):
            # ADR-0051: keys present but non-castable → conservative fail.
            # Absent keys mean the caller does not supply HRV; treat as no-op.
            _h2_missing = "today_hrv" in context or "baseline_hrv" in context
        if _h2_missing:
            _gate_event(
                "H2_HRV",
                "EASY_ceiling_applied",
                reason="governance_data_missing_conservative",
                severity="WARNING",
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
            )
            # ADR-0051: missing HRV data → conservative fail
            context["data_confidence_low"] = True
            # Apply EASY ceiling immediately; signal apply_constraints to emit lock code.
            if str(session_plan.get("session_type", "EASY")).upper() not in {"REST", "EASY"}:
                session_plan["session_type"] = "EASY"
            context["_h2_data_missing"] = True
            reasons.append({
                "gate": "H2_MISSING",
                "reason": (
                    "HRV data missing, non-finite or without a positive baseline — "
                    "EASY ceiling applied (ADR-0051, ADR-0068)"
                ),
            })
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
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
            )

        # H3 — RHR Spike (Gate 2b: RHR spike alone sufficient — OR semantics)
        # Fires when rise >= HARD_STOP_RHR_DELTA (inclusive boundary).
        h3_trigger = False
        _h3_missing = False
        try:
            _h3_today = float(context.get("today_rhr"))
            _h3_base = float(context.get("baseline_rhr"))
            if not (math.isfinite(_h3_today) and math.isfinite(_h3_base)):
                _gate_event("H3", "NAN_REJECTED",
                            reason="non-finite RHR input rejected (INV-01)",
                            garmin_data_age_hours=_garmin_age,
                            garmin_data_trust_level=_garmin_trust)
                # ADR-0068 (SG-07): non-finite RHR is missing RHR → H3_MISSING ceiling.
                _h3_missing = True
            else:
                h3_trigger = _h3_today >= _h3_base + HARD_STOP_RHR_DELTA
        except (TypeError, ValueError):
            # ADR-0051: keys present but non-castable → conservative fail.
            # Absent keys mean the caller does not supply RHR; treat as no-op.
            _h3_missing = "today_rhr" in context or "baseline_rhr" in context
        if _h3_missing:
            _gate_event(
                "H3_RHR",
                "EASY_ceiling_applied",
                reason="governance_data_missing_conservative",
                severity="WARNING",
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
            )
            # ADR-0051: missing RHR data → conservative fail
            context["data_confidence_low"] = True
            # Apply EASY ceiling immediately; signal apply_constraints to emit lock code.
            if str(session_plan.get("session_type", "EASY")).upper() not in {"REST", "EASY"}:
                session_plan["session_type"] = "EASY"
            context["_h3_data_missing"] = True
            reasons.append({
                "gate": "H3_MISSING",
                "reason": "RHR data missing or non-finite — EASY ceiling applied (ADR-0051, ADR-0068)",
            })
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
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
            )

        if h2_trigger or h3_trigger:
            hrv_stress_context = self.classify_hrv_stress_context(context)
            session_plan["hrv_stress_context"] = hrv_stress_context
            _gate_event(
                "HRV_STRESS_CONTEXT",
                "CLASSIFIED",
                cause="TRAINING_LOGIC",
                stress_context=hrv_stress_context,
                h2_trigger=h2_trigger,
                h3_trigger=h3_trigger,
                acwr=context.get("acwr"),
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
            )

            if hrv_stress_context == "ILLNESS_PATTERN":
                reason = "Non-training stress protocol: illness-pattern autonomic strain — full rest"
                session_plan["session_type"] = "REST"
                session_plan["max_zone"] = 1
                session_plan["governance_override"] = reason
                reasons.append({"gate": "H2_H3_NON_TRAINING_STRESS", "reason": reason})
                _gate_event(
                    "H2_H3_NON_TRAINING_STRESS",
                    "REST",
                    reason=reason,
                    cause="TRAINING_LOGIC",
                    stress_context=hrv_stress_context,
                    garmin_data_age_hours=_garmin_age,
                    garmin_data_trust_level=_garmin_trust,
                )

        # Dual collapse: both H2 and H3 fired — set combined override message.
        if h2_trigger and h3_trigger and session_plan.get("hrv_stress_context") != "ILLNESS_PATTERN":
            reason = "HRV/RHR dual collapse: autonomic stress — hard stop"
            session_plan["governance_override"] = reason
            _gate_event(
                "H2+H3", "REST", reason=reason, cause="TRAINING_LOGIC",
                garmin_data_age_hours=_garmin_age, garmin_data_trust_level=_garmin_trust,
            )

        # H4 — TSB Critical Floor (Gate 4: load gate)
        try:
            tsb_value = float(context.get("tsb_value"))
            if not math.isfinite(tsb_value):
                _gate_event("H4", "NAN_REJECTED",
                            reason="non-finite TSB input rejected (INV-01)",
                            garmin_data_age_hours=_garmin_age,
                            garmin_data_trust_level=_garmin_trust)
                # ADR-0051: non-finite TSB → conservative fail
                context["data_confidence_low"] = True
                if str(session_plan.get("session_type", "EASY")).upper() not in {"REST", "EASY"}:
                    session_plan["session_type"] = "EASY"
                context["_h4_data_missing"] = True
                reasons.append({
                    "gate": "H4_MISSING",
                    "reason": "TSB data non-finite — EASY ceiling applied (ADR-0051)",
                })
                tsb_value = None
        except (TypeError, ValueError):
            # ADR-0051: key present but non-castable → conservative fail.
            if "tsb_value" in context:
                _gate_event(
                    "H4_TSB",
                    "EASY_ceiling_applied",
                    reason="governance_data_missing_conservative",
                    severity="WARNING",
                    garmin_data_age_hours=_garmin_age,
                    garmin_data_trust_level=_garmin_trust,
                )
                context["data_confidence_low"] = True
                if str(session_plan.get("session_type", "EASY")).upper() not in {"REST", "EASY"}:
                    session_plan["session_type"] = "EASY"
                context["_h4_data_missing"] = True
                reasons.append({
                    "gate": "H4_MISSING",
                    "reason": "TSB data missing or non-numeric — EASY ceiling applied (ADR-0051)",
                })
            tsb_value = None
        if tsb_value is not None and tsb_value <= HARD_STOP_TSB_FLOOR:
            # ADR-0068 (SG-09): every session above EASY (LONG_RUN, PROGRESSIVE too) becomes
            # EASY, and apply_constraints gives every non-REST H4 day the ADR-0065 volume cap.
            if str(session_plan.get("session_type", "EASY")).upper() not in {"REST", "EASY"}:
                session_plan["session_type"] = "EASY"
            context["_h4_load_reduction"] = True
            reason = "TSB at overtraining threshold: mandatory load reduction"
            session_plan["governance_override"] = reason
            session_plan["max_zone"] = min(int(session_plan.get("max_zone", 5)), 2)
            reasons.append({"gate": "H4", "reason": reason})
            _gate_event(
                "H4", "EASY", reason=reason, cause="TRAINING_LOGIC", tsb_value=tsb_value,
                garmin_data_age_hours=_garmin_age, garmin_data_trust_level=_garmin_trust,
            )

        # H5 — Extreme Subjective Fatigue
        _h5_missing = "subjective_fatigue_score" not in context
        subjective_fatigue = 0
        if not _h5_missing:
            try:
                _h5_raw = float(context.get("subjective_fatigue_score", 0))
                if not math.isfinite(_h5_raw):
                    _gate_event("H5", "NAN_REJECTED",
                                reason="non-finite fatigue input rejected (INV-01)",
                                garmin_data_age_hours=_garmin_age,
                                garmin_data_trust_level=_garmin_trust)
                    # ADR-0068 (SG-07): non-finite fatigue is missing fatigue → H5_MISSING ceiling.
                    _h5_missing = True
                else:
                    subjective_fatigue = int(_h5_raw)
            except (TypeError, ValueError):
                # ADR-0068: a present but non-numeric score is missing, as for H2/H3.
                _h5_missing = True
        if _h5_missing:
            # ADR-0051: absent fatigue key → conservative soft downgrade (not hard stop).
            # H5 is a soft gate — does NOT set data_confidence_low (that would escalate
            # to STARTUP_DATA_CONFIDENCE_CEILING, an unintended hard downgrade).
            _gate_event(
                "H5_FATIGUE",
                "MODERATE_ceiling_applied",
                reason="governance_data_missing_conservative",
                severity="WARNING",
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
            )
            session_plan["max_zone"] = min(int(session_plan.get("max_zone", 5)), 3)
            context["_h5_data_missing"] = True
            reasons.append({
                "gate": "H5_MISSING",
                "reason": "Subjective fatigue data absent or non-numeric — MODERATE ceiling applied (ADR-0051)",
            })
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
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
            )

        # ── H6: Data-void conservative gate (ADR-0053) ──────────
        try:
            garmin_age = context.get("garmin_data_age_hours")
            if (
                garmin_age is not None
                and math.isfinite(float(garmin_age))
                and float(garmin_age) > DATA_VOID_THRESHOLD_HOURS
            ):
                context["_h6_data_void"] = True
                _gate_event(
                    "H6_DATA_VOID",
                    "DATA_VOID_CONSERVATIVE",
                    garmin_data_age_hours=garmin_age,
                    threshold_hours=DATA_VOID_THRESHOLD_HOURS,
                    severity="WARNING",
                )
        except (TypeError, ValueError):
            _log.debug(
                "H6 gate skipped: garmin_data_age_hours "
                "is not numeric: %r", garmin_age
            )

        return reasons

    def _check_vo2_eligibility(self, session_plan: dict, context: dict) -> dict | None:
        _garmin_age = context.get("garmin_data_age_hours")
        _garmin_trust = context.get("garmin_data_trust_level", "UNKNOWN")
        session_type = str(session_plan.get("session_type", "")).upper()
        zone_raw = session_plan.get("zone", session_plan.get("max_zone", 0))
        zone_invalid = False
        try:
            zone = int(zone_raw or 0)
        except (TypeError, ValueError):
            zone = 5
            zone_invalid = True
        is_vo2_session = session_type in self._VO2_SESSIONS or (
            session_type == "INTERVALS" and zone == 5
        )
        if not is_vo2_session:
            return None

        acwr_raw = context.get("acwr")
        readiness_raw = context.get("readiness_score")
        glycogen_debt_raw = context.get("glycogen_debt", 0.0)
        fatigue_level_raw = context.get("fatigue_level", "LOW")
        esi_level_raw = context.get("esi_level", "LOW")
        days_since_last_vo2 = context.get("days_since_last_vo2")

        acwr_invalid = False
        if acwr_raw is None:
            acwr = None
            acwr_invalid = True
        else:
            try:
                acwr = float(acwr_raw)
                if not math.isfinite(acwr):
                    _gate_event("VO2_ELIGIBILITY", "NAN_REJECTED",
                                reason="non-finite ACWR input rejected (INV-01)")
                    acwr = None
                    acwr_invalid = True
            except (TypeError, ValueError):
                acwr = None
                acwr_invalid = True

        readiness_invalid = False
        if readiness_raw is None:
            readiness = None
            readiness_invalid = True
        else:
            try:
                readiness = float(readiness_raw)
                if not math.isfinite(readiness):
                    _gate_event("VO2_ELIGIBILITY", "NAN_REJECTED",
                                reason="non-finite readiness input rejected (INV-01)")
                    readiness = None
                    readiness_invalid = True
            except (TypeError, ValueError):
                readiness = None
                readiness_invalid = True

        glycogen_debt_invalid = False
        try:
            glycogen_debt = float(0.0 if glycogen_debt_raw is None else glycogen_debt_raw)
            if not math.isfinite(glycogen_debt):
                _gate_event("VO2_ELIGIBILITY", "NAN_REJECTED",
                            reason="non-finite glycogen_debt input rejected (INV-01)")
                glycogen_debt = None
                glycogen_debt_invalid = True
        except (TypeError, ValueError):
            glycogen_debt = None
            glycogen_debt_invalid = True

        fatigue_level = str(fatigue_level_raw or "LOW").upper()
        esi_level = str(esi_level_raw or "LOW").upper()
        valid_fatigue_levels = {"LOW", "MEDIUM", "HIGH"}
        fatigue_level_invalid = fatigue_level not in valid_fatigue_levels

        failed: list[str] = []
        reasons: list[str] = []
        details: list[dict[str, Any]] = []

        if zone_invalid:
            failed.append("V1")
            reasons.append(f"zone must be numeric (actual: {zone_raw!r})")
            details.append(
                {
                    "code": "V1",
                    "metric": "zone",
                    "operator": "numeric",
                    "actual": zone_raw,
                }
            )

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

        if esi_level == "EXTREME" and "V4" not in failed:
            failed.append("V4")
            reasons.append("esi_level must not be EXTREME")
            details.append(
                {
                    "code": "V4",
                    "metric": "esi_level",
                    "operator": "!=",
                    "threshold": "EXTREME",
                    "actual": esi_level,
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
                zone_invalid
                or acwr_invalid
                or readiness_invalid
                or glycogen_debt_invalid
                or fatigue_level_invalid
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
                    "zone_invalid": zone_invalid,
                },
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
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
        _gate_event(
            "VO2_ELIGIBILITY", "PASS", original_session=original,
            garmin_data_age_hours=_garmin_age, garmin_data_trust_level=_garmin_trust,
        )
        return result

    def _check_fueling_gate(self, session_plan: dict, context: dict) -> dict | None:
        _garmin_age = context.get("garmin_data_age_hours")
        _garmin_trust = context.get("garmin_data_trust_level", "UNKNOWN")
        session_type = str(session_plan.get("session_type", "")).upper()
        duration_raw = session_plan.get("duration_min", context.get("planned_duration_min", 0))
        try:
            _dur_f = float(duration_raw or 0)
            if not math.isfinite(_dur_f):
                _gate_event(
                    "FUELING", "NAN_REJECTED",
                    reason="non-finite duration rejected (INV-01)",
                    garmin_data_age_hours=_garmin_age,
                    garmin_data_trust_level=_garmin_trust,
                )
                return None
            duration = int(_dur_f)
        except (TypeError, ValueError):
            duration = 90
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
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
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
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
            )
            return result

        if session_type == "LONG_RUN" and duration >= 90:
            # ADR-0063: the long run stays; the morning message reminds the athlete to
            # carry food or gels. Locking it to PROGRESSIVE made the session harder (SV-05).
            result = {
                "action": "FLAG",
                "phase": 4,
                "reason": f"LONG_RUN {duration} min without confirmed fueling: carry food or gels",
                "session_unchanged": True,
            }
            _gate_event(
                "FUELING", "FLAG", phase=4, session_type="LONG_RUN", duration_min=duration,
                garmin_data_age_hours=_garmin_age, garmin_data_trust_level=_garmin_trust,
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
                "FUELING", "FLAG", phase=2, session_type=session_type, duration_min=duration,
                garmin_data_age_hours=_garmin_age, garmin_data_trust_level=_garmin_trust,
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
                "FUELING", "FLAG", phase=1, session_type=session_type, duration_min=duration,
                garmin_data_age_hours=_garmin_age, garmin_data_trust_level=_garmin_trust,
            )
            return result

        return None

    @staticmethod
    def _format_template(template_key: str, *, actual: Any = None, threshold: Any = None, margin: Any = None) -> str:
        template = GATE_RATIONALE_TEMPLATES.get(template_key, template_key)
        return template.format(actual=actual, threshold=threshold, margin=margin)

    @staticmethod
    def _guidance_for_gate(gate: str) -> str:
        guidance_map = {
            "H1": "Prioritize recovery and seek medical clearance before training.",
            "H2": "Replace intensity with rest and reassess HRV tomorrow morning.",
            "H3": "Keep effort low, hydrate, and reassess resting HR tomorrow.",
            "H4": "Shift to easy aerobic work until freshness rebounds above threshold.",
            "H5": "Use easy recovery training and monitor subjective fatigue daily.",
            "READINESS_2OF4_DOWNGRADE": "Keep intensity reduced until at least 3 indicators normalize.",
            "OVERRIDE_LOCKDOWN": "Pause manual overrides and rebuild plan adherence for 14 days.",
            "CS_CONFIDENCE_LOCK": "Run the required CS calibration session before race simulation.",
            "VO2_ELIGIBILITY_GATE": "Complete prerequisites (recovery, fueling, readiness) before VO2 work.",
            "FUELING_GATE_LOCK": "Confirm fueling plan before scheduling quality or long sessions.",
            "STARTUP_DATA_CONFIDENCE_CEILING": "Resolve missing startup inputs and rerun hydration checks.",
            "PERSISTENCE_DEGRADED_CEILING": "Restore persistence path health before lifting safety ceilings.",
        }
        return guidance_map.get(gate, "Continue with conservative training and monitor recovery signals.")

    @staticmethod
    def _margin_ge(actual: float | None, threshold: float) -> float | None:
        if actual is None:
            return None
        return round(actual - threshold, 2)

    @staticmethod
    def _margin_le(actual: float | None, threshold: float) -> float | None:
        if actual is None:
            return None
        return round(threshold - actual, 2)

    def _build_decision_rationale(self, context: dict, session_plan: dict, applied_locks: list[str]) -> DecisionRationale:
        findings: list[GateFinding] = []

        injury_flag = bool(context.get("injury_flag", False))
        findings.append(
            GateFinding(
                gate="H1",
                status="TRIGGERED" if injury_flag else "CLEAR",
                actual_value=injury_flag,
                threshold_value=True,
                margin=None,
                reason=self._format_template("H1"),
            )
        )

        try:
            _baseline_hrv = float(context.get("baseline_hrv"))
            hrv_delta = _baseline_hrv - float(context.get("today_hrv"))
        except (TypeError, ValueError):
            _baseline_hrv = 0.0
            hrv_delta = None
        h2_threshold = self.h2_drop_threshold_ms(_baseline_hrv)
        h2_trigger = bool(hrv_delta is not None and hrv_delta >= h2_threshold)
        findings.append(
            GateFinding(
                gate="H2",
                status="TRIGGERED" if h2_trigger else "CLEAR",
                actual_value=hrv_delta,
                threshold_value=h2_threshold,
                margin=self._margin_ge(hrv_delta, h2_threshold),
                reason=self._format_template(
                    "H2",
                    actual=hrv_delta,
                    threshold=h2_threshold,
                    margin=self._margin_ge(hrv_delta, h2_threshold),
                ),
            )
        )

        try:
            rhr_delta = float(context.get("today_rhr")) - float(context.get("baseline_rhr"))
        except (TypeError, ValueError):
            rhr_delta = None
        h3_trigger = bool(rhr_delta is not None and rhr_delta >= HARD_STOP_RHR_DELTA)
        findings.append(
            GateFinding(
                gate="H3",
                status="TRIGGERED" if h3_trigger else "CLEAR",
                actual_value=rhr_delta,
                threshold_value=HARD_STOP_RHR_DELTA,
                margin=self._margin_ge(rhr_delta, HARD_STOP_RHR_DELTA),
                reason=self._format_template(
                    "H3",
                    actual=rhr_delta,
                    threshold=HARD_STOP_RHR_DELTA,
                    margin=self._margin_ge(rhr_delta, HARD_STOP_RHR_DELTA),
                ),
            )
        )

        try:
            tsb_value = float(context.get("tsb_value"))
        except (TypeError, ValueError):
            tsb_value = None
        h4_trigger = bool(tsb_value is not None and tsb_value <= HARD_STOP_TSB_FLOOR)
        findings.append(
            GateFinding(
                gate="H4",
                status="TRIGGERED" if h4_trigger else "CLEAR",
                actual_value=tsb_value,
                threshold_value=HARD_STOP_TSB_FLOOR,
                margin=self._margin_le(tsb_value, HARD_STOP_TSB_FLOOR),
                reason=self._format_template(
                    "H4",
                    actual=tsb_value,
                    threshold=HARD_STOP_TSB_FLOOR,
                    margin=self._margin_le(tsb_value, HARD_STOP_TSB_FLOOR),
                ),
            )
        )

        try:
            subjective_fatigue = int(context.get("subjective_fatigue_score", 0))
        except (TypeError, ValueError, OverflowError):
            subjective_fatigue = 0
        h5_trigger = subjective_fatigue >= SUBJECTIVE_FATIGUE_EXTREME
        findings.append(
            GateFinding(
                gate="H5",
                status="TRIGGERED" if h5_trigger else "CLEAR",
                actual_value=subjective_fatigue,
                threshold_value=SUBJECTIVE_FATIGUE_EXTREME,
                margin=self._margin_ge(float(subjective_fatigue), float(SUBJECTIVE_FATIGUE_EXTREME)),
                reason=self._format_template(
                    "H5",
                    actual=subjective_fatigue,
                    threshold=SUBJECTIVE_FATIGUE_EXTREME,
                    margin=self._margin_ge(float(subjective_fatigue), float(SUBJECTIVE_FATIGUE_EXTREME)),
                ),
            )
        )

        for lock_code in applied_locks:
            findings.append(
                GateFinding(
                    gate=lock_code,
                    status="TRIGGERED",
                    actual_value=None,
                    threshold_value=None,
                    margin=None,
                    reason=self._format_template(lock_code),
                )
            )

        primary = next((f for f in findings if f.status == "TRIGGERED"), None)
        if primary is None:
            primary_reason = "No governance lock triggered: training proceeds as planned."
            actionable_guidance = "Execute planned session and continue normal monitoring."
        else:
            primary_reason = primary.reason
            actionable_guidance = self._guidance_for_gate(primary.gate)

        return DecisionRationale(
            primary_reason=primary_reason,
            actionable_guidance=actionable_guidance,
            gate_findings=findings,
        )

    def _fail_closed_requires_rest(self, session_plan: dict, context: dict) -> bool:
        """True when REST is already set or a hard stop H1–H3 fires on the inputs (ADR-0068)."""
        if str(session_plan.get("session_type", "")).upper() == "REST":
            return True
        try:
            if bool(context.get("injury_flag", False)):
                return True
            probe = self._check_hard_stops(dict(session_plan), dict(context))
        except Exception:
            # The hard stops themselves cannot be evaluated: EASY/zone 2 is the fallback.
            return False
        return any(r.get("gate") in self._REST_HARD_STOPS for r in probe)

    def apply_constraints(self, session_plan: dict, context: dict) -> dict:
        # Outside the try so the fail-closed path keeps the locks already applied (ADR-0068).
        applied_locks: list[str] = []
        try:
            _garmin_age = context.get("garmin_data_age_hours")
            _garmin_trust = context.get("garmin_data_trust_level", "UNKNOWN")
            db = context.get("db")
            cs_tracker = context.get("cs_tracker")
            afi_constr = context.get("afi_constraints", {})

            # APL injections — adaptive thresholds and gate priority vector.
            # If APL was not invoked upstream, these default to {} and all gate
            # checks fall back to their static class-level constants (no behaviour change).
            lock_thresholds = context.get("lock_thresholds", {})
            priority_vector = context.get("priority_vector", {})

            intensity_gate = self._to_dict_maybe(context.get("intensity_gate_result"))
            if intensity_gate:
                session_plan["intensity_gate_result"] = intensity_gate
                color = str(intensity_gate.get("color", "GREEN")).upper()
                # ADR-0068 (SG-10): a non-numeric zone gives the EASY ceiling, an out-of-range
                # one is clamped to 1..5 (max_zone 0 is zone 1, never 5).
                session_plan["max_zone"] = min(
                    self._bounded_zone(session_plan.get("max_zone"), missing=5),
                    self._bounded_zone(intensity_gate.get("max_zone"), missing=5),
                )
                # ADR-0062: the conservative modifier replaces a missing value only; 0.0 stays 0.0.
                _raw_vol_mod = intensity_gate.get("volume_modifier")
                try:
                    _vol_mod = float(INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE if _raw_vol_mod is None else _raw_vol_mod)
                except (TypeError, ValueError):
                    _vol_mod = math.nan
                if not math.isfinite(_vol_mod):
                    _gate_event(
                        "INTENSITY_GATE", "NAN_REJECTED",
                        reason="non-finite volume_modifier rejected (INV-01)",
                        garmin_data_age_hours=_garmin_age,
                        garmin_data_trust_level=_garmin_trust,
                    )
                    # ADR-0068 (SG-10): a bad modifier takes the conservative value, not 1.0.
                    _vol_mod = INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE
                session_plan["volume_modifier"] = min(max(_vol_mod, 0.0), 1.0)
                override = intensity_gate.get("session_override")
                if override:
                    session_plan["session_type"] = override
                if color == "RED":
                    applied_locks.append("INTENSITY_GATE_RED")
                elif color == "YELLOW":
                    applied_locks.append("INTENSITY_GATE_YELLOW")

            _type_after_intensity_gate = str(session_plan.get("session_type", "")).upper()
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
                    garmin_data_age_hours=_garmin_age,
                    garmin_data_trust_level=_garmin_trust,
                )

            hard_stop_reasons = self._check_hard_stops(session_plan, context)
            if hard_stop_reasons:
                session_plan["hard_stop_reasons"] = hard_stop_reasons
                applied_locks.append("HARD_STOP_SAFETY_GATES")
            # ADR-0051: conservative missing-data lock codes signalled by _check_hard_stops.
            if context.get("_h2_data_missing"):
                applied_locks.append("DATA_MISSING_CONSERVATIVE_H2")
            if context.get("_h3_data_missing"):
                applied_locks.append("DATA_MISSING_CONSERVATIVE_H3")
            if context.get("_h4_data_missing"):
                applied_locks.append("DATA_MISSING_CONSERVATIVE_H4")
            if context.get("_h5_data_missing"):
                applied_locks.append("DATA_MISSING_CONSERVATIVE_H5")

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
                if not vo2_result.get("eligible", False):
                    applied_locks.append("VO2_ELIGIBILITY_GATE")

            fueling_result = self._check_fueling_gate(session_plan, context)
            if fueling_result is not None:
                session_plan["fueling_gate"] = fueling_result
                if fueling_result.get("action") == "LOCK":
                    applied_locks.append("FUELING_GATE_LOCK")
                else:
                    applied_locks.append("FUELING_GATE_FLAG")

            # ADR-0065 (SV-04): 2of4, the hard stops, VO2 and fueling have no volume modifier,
            # so a session they downgrade keeps 70% of its volume and at most 60 minutes.
            # ADR-0068 (SG-09): an H4 day that is not REST gets the same cap even when its type
            # did not change (EASY stays EASY but still loses volume).
            _downgraded_to = str(session_plan.get("session_type", "")).upper()
            if _downgraded_to != "REST" and (
                _downgraded_to != _type_after_intensity_gate or context.get("_h4_load_reduction")
            ):
                _current_mod = session_plan.get("volume_modifier")
                _downgrade_mod = INTENSITY_GATE_VOLUME_MODIFIER_CONSERVATIVE
                if _current_mod is not None:
                    _downgrade_mod = min(float(_current_mod), _downgrade_mod)
                session_plan["volume_modifier"] = _downgrade_mod
                session_plan["max_duration_min"] = GOVERNANCE_DOWNGRADE_MAX_DURATION_MIN
                _gate_event(
                    "DOWNGRADE_VOLUME", "REDUCED",
                    original_session=_type_after_intensity_gate, downgraded_to=_downgraded_to,
                    volume_modifier=_downgrade_mod, max_duration_min=GOVERNANCE_DOWNGRADE_MAX_DURATION_MIN,
                    garmin_data_age_hours=_garmin_age, garmin_data_trust_level=_garmin_trust,
                )

            # H6 data-void cap (ADR-0053)
            if context.get("_h6_data_void"):
                if session_plan.get("max_zone", 5) > DATA_VOID_ZONE_CAP:
                    session_plan["max_zone"] = DATA_VOID_ZONE_CAP
                applied_locks.append("DATA_VOID_CONSERVATIVE")

            para_guard = afi_constr.get("parasympathetic_guard", {})

            gate_order = {
                "PARASYMPATHETIC_GUARD": int(priority_vector.get("PARASYMPATHETIC_GUARD", 1) or 1),
                "OVERRIDE_LOCKDOWN": int(priority_vector.get("OVERRIDE_LOCKDOWN", 2) or 2),
                "CS_CONFIDENCE_LOCK": int(priority_vector.get("CS_CONFIDENCE_LOCK", 3) or 3),
            }

            for gate_name, _rank in sorted(gate_order.items(), key=lambda x: x[1]):
                if gate_name == "PARASYMPATHETIC_GUARD":
                    if para_guard.get("triggered"):
                        # ADR-0068 (SG-03): a lock never raises intensity — min(current, EASY).
                        # A REST from a hard stop stays REST and keeps its reason.
                        if str(session_plan.get("session_type", "EASY")).upper() != "REST":
                            session_plan["session_type"] = "EASY"
                            session_plan["governance_override"] = para_guard["reason"]
                        session_plan["max_zone"] = min(
                            self._bounded_zone(session_plan.get("max_zone"), missing=5), 2,
                        )
                        applied_locks.append("PARASYMPATHETIC_GUARD")
                        _gate_event(
                            "PARASYMPATHETIC_GUARD", str(session_plan.get("session_type", "EASY")).upper(),
                            reason=para_guard.get("reason"),
                            garmin_data_age_hours=_garmin_age, garmin_data_trust_level=_garmin_trust,
                        )
                    continue

                if gate_name == "OVERRIDE_LOCKDOWN":
                    if not db:
                        continue
                    override_threshold = lock_thresholds.get("override_ratio_ceiling") or None
                    lock = self.check_override_lockdown(
                        db, threshold=override_threshold, athlete_id=self._resolve_athlete_id(context),
                    )
                    if lock["locked"] and session_plan.get("session_type") in lock["disabled_sessions"]:
                        session_plan["session_type"] = "EASY"
                        session_plan["max_zone"] = min(
                            self._bounded_zone(session_plan.get("max_zone"), missing=5), lock["max_zone"],
                        )
                        session_plan["governance_override"] = lock["reason"]
                        applied_locks.append("OVERRIDE_LOCKDOWN")
                        _gate_event(
                            "OVERRIDE_LOCKDOWN",
                            "ZONE_2_ONLY",
                            cause="TRAINING_LOGIC",
                            ratio=lock.get("ratio"),
                            apl_threshold_override=override_threshold,
                            garmin_data_age_hours=_garmin_age,
                            garmin_data_trust_level=_garmin_trust,
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
                            garmin_data_age_hours=_garmin_age,
                            garmin_data_trust_level=_garmin_trust,
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
                    garmin_data_age_hours=_garmin_age,
                    garmin_data_trust_level=_garmin_trust,
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
                    garmin_data_age_hours=_garmin_age,
                    garmin_data_trust_level=_garmin_trust,
                )

            session_plan["governance_locks_applied"] = applied_locks
            session_plan["governance_clean"] = len(applied_locks) == 0
            decision_rationale = self._build_decision_rationale(context, session_plan, applied_locks)
            session_plan["decision_rationale"] = asdict(decision_rationale)

            _gate_event(
                "APPLY_CONSTRAINTS",
                "COMPLETE",
                final_session=session_plan.get("session_type"),
                locks_applied=applied_locks,
                governance_clean=session_plan["governance_clean"],
                priority_vector=priority_vector or None,
                apl_active=bool(priority_vector),
                garmin_data_age_hours=_garmin_age,
                garmin_data_trust_level=_garmin_trust,
            )
        except Exception as exc:
            _log.critical(json.dumps({
                "flow": "governance",
                "action": "apply_constraints_exception_fail_closed",
                "error_class": type(exc).__name__,
                "error_message": str(exc),
                "invariant": "INV-12",
                "outcome": "FORCED_EASY_ZONE_2",
            }, default=str))
            _gate_event(
                "GOVERNANCE_EXCEPTION", "FAIL_CLOSED", cause="SYSTEM_ERROR",
                error_class=type(exc).__name__, error_message=str(exc),
                invariant="INV-12",
                reason="apply_constraints raised — forcing EASY/zone-2 (fail-closed)",
            )
            # ADR-0068 (SG-05): fail closed never loosens — REST (already set, or a hard-stop
            # input present) stays REST; otherwise min(current, EASY) with zone ≤ 2.
            if self._fail_closed_requires_rest(session_plan, context):
                session_plan["session_type"] = "REST"
                session_plan["max_zone"] = 1
            else:
                session_plan["session_type"] = "EASY"
                session_plan["max_zone"] = min(self._bounded_zone(session_plan.get("max_zone"), missing=2), 2)
            session_plan["governance_exception_fail_closed"] = True
            # use the SAME key the normal path writes locks into, keeping the locks applied so far:
            locks_key = "governance_locks_applied"
            _prior_locks = session_plan.get(locks_key)
            if not isinstance(_prior_locks, list):
                _prior_locks = []
            for _lock in applied_locks:
                if _lock not in _prior_locks:
                    _prior_locks.append(_lock)
            _prior_locks.append("GOVERNANCE_EXCEPTION_FAIL_CLOSED")
            session_plan[locks_key] = _prior_locks
            return session_plan
        else:
            return session_plan

    def get_governance_report(
        self,
        db: Any | None = None,
        cs_tracker: Any | None = None,
        afi_constraints: dict | None = None,
        athlete_id: str | None = None,
    ) -> dict:
        _athlete_id = self._resolve_athlete_id({"athlete_id": athlete_id})
        return {
            "override_lockdown": (
                self.check_override_lockdown(db, athlete_id=_athlete_id) if db else {"locked": False}
            ),
            "cs_confidence_lock": self.check_cs_confidence_lock(cs_tracker)
            if cs_tracker
            else {"locked": False},
            "parasympathetic_guard": (afi_constraints or {}).get(
                "parasympathetic_guard", {"triggered": False}
            ),
        }

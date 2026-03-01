"""Governance Engine — intensity, readiness downgrade, and safety gates."""

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional, Tuple

from titan.config.thresholds import (
    HARD_STOP_HRV_DELTA,
    HARD_STOP_RHR_DELTA,
    HARD_STOP_TSB_FLOOR,
    SUBJECTIVE_FATIGUE_2OF4,
    SUBJECTIVE_FATIGUE_EXTREME,
)


class GovernanceEngine:
    OVERRIDE_LOCKDOWN_THRESHOLD: float = 0.80
    CS_CONFIDENCE_THRESHOLD: float = 0.70

    _QUALITY_SESSIONS = frozenset({'INTERVALS', 'TEMPO', 'RACE', 'HAMMER'})
    _VO2_SESSIONS = frozenset({'HAMMER', 'RACE'})

    _DOWNGRADE_MAP_2OF4 = {
        'INTERVALS': 'TEMPO',
        'TEMPO': 'EASY',
        'HAMMER': 'EASY',
        'RACE': 'TEMPO',
        'PROGRESSIVE': 'EASY',
        'EASY': 'EASY',
        'REST': 'REST',
    }

    def check_override_lockdown(self, db: Any) -> Dict:
        try:
            ratio = db.get_override_ratio(days=14)
        except Exception:
            ratio = 0.0

        if ratio > self.OVERRIDE_LOCKDOWN_THRESHOLD:
            return {
                'locked': True,
                'ratio': ratio,
                'reason': (
                    f'Override ratio {ratio:.0%} (14d) > {self.OVERRIDE_LOCKDOWN_THRESHOLD:.0%} '
                    f'threshold — periodization integrity compromised'
                ),
                'max_zone': 2,
                'disabled_sessions': list(self._QUALITY_SESSIONS),
                'action': 'ZONE_2_ONLY',
            }
        return {'locked': False, 'ratio': ratio, 'max_zone': 5, 'disabled_sessions': []}

    def check_cs_confidence_lock(self, cs_tracker: Any) -> Dict:
        confidence = getattr(cs_tracker, 'confidence', 1.0)
        if confidence < self.CS_CONFIDENCE_THRESHOLD:
            return {
                'locked': True,
                'confidence': confidence,
                'reason': (
                    f'CS confidence {confidence:.0%} < {self.CS_CONFIDENCE_THRESHOLD:.0%} — '
                    f'calibration time-trial required before race simulation'
                ),
                'required_session': 'CS_CALIBRATION',
                'disabled': ['RACE_SIMULATION', 'TTE_PREDICTION'],
            }
        return {'locked': False, 'confidence': confidence}

    @staticmethod
    def _to_dict_maybe(value: Any) -> Dict:
        if isinstance(value, dict):
            return value
        if value is None:
            return {}
        if is_dataclass(value):
            return asdict(value)
        return {
            'color': getattr(value, 'color', 'GREEN'),
            'max_zone': getattr(value, 'max_zone', 5),
            'volume_modifier': getattr(value, 'volume_modifier', 1.0),
            'session_override': getattr(value, 'session_override', None),
            'triggered_signals': list(getattr(value, 'triggered_signals', [])),
            'audit': getattr(value, 'audit', {}),
        }

    def _evaluate_2of4_indicators(self, context: Dict) -> Tuple[int, List[str]]:
        indicators: List[str] = []

        today_hrv = context.get('today_hrv')
        baseline_hrv = context.get('baseline_hrv')
        hrv_std_dev = context.get('hrv_std_dev')
        hrv_soft = False
        if today_hrv is not None and baseline_hrv is not None and hrv_std_dev is not None:
            try:
                hrv_soft = float(today_hrv) < (float(baseline_hrv) - float(hrv_std_dev))
            except (TypeError, ValueError):
                hrv_soft = False
        else:
            hrv_soft = bool(context.get('hrv_soft_trigger', False))
        if hrv_soft:
            indicators.append('I1_hrv_soft')

        try:
            sleep_score = float(context.get('sleep_score', 100))
        except (TypeError, ValueError):
            sleep_score = 100
        if sleep_score < 60:
            indicators.append('I2_sleep')

        try:
            readiness_score = float(context.get('readiness_score', 100))
        except (TypeError, ValueError):
            readiness_score = 100
        if readiness_score < 50:
            indicators.append('I3_readiness')

        try:
            subjective_fatigue = int(context.get('subjective_fatigue_score', 0))
        except (TypeError, ValueError):
            subjective_fatigue = 0
        if subjective_fatigue >= SUBJECTIVE_FATIGUE_2OF4:
            indicators.append('I4_subjective')

        return len(indicators), indicators

    def _check_hard_stops(self, session_plan: Dict, context: Dict) -> List[Dict]:
        reasons: List[Dict] = []

        session_type = str(session_plan.get('session_type', 'EASY')).upper()

        try:
            today_hrv = float(context.get('today_hrv'))
            baseline_hrv = float(context.get('baseline_hrv'))
            today_rhr = float(context.get('today_rhr'))
            baseline_rhr = float(context.get('baseline_rhr'))
            h1_trigger = (
                today_hrv < baseline_hrv - HARD_STOP_HRV_DELTA
                and today_rhr > baseline_rhr + HARD_STOP_RHR_DELTA
            )
        except (TypeError, ValueError):
            h1_trigger = False

        if h1_trigger:
            session_plan['session_type'] = 'REST'
            session_plan['max_zone'] = 1
            reason = 'HRV/RHR dual collapse: autonomous nervous system under acute stress'
            session_plan['governance_override'] = reason
            reasons.append({'gate': 'H1', 'reason': reason})

        try:
            tsb_value = float(context.get('tsb_value'))
        except (TypeError, ValueError):
            tsb_value = None
        if tsb_value is not None and tsb_value <= HARD_STOP_TSB_FLOOR:
            if str(session_plan.get('session_type', session_type)).upper() in self._QUALITY_SESSIONS:
                session_plan['session_type'] = 'EASY'
            reason = 'TSB at overtraining threshold: mandatory load reduction'
            session_plan['governance_override'] = reason
            session_plan['max_zone'] = min(int(session_plan.get('max_zone', 5)), 2)
            reasons.append({'gate': 'H2', 'reason': reason})

        if bool(context.get('injury_flag', False)):
            session_plan['session_type'] = 'REST'
            session_plan['max_zone'] = 1
            reason = 'Active injury flag: no training permitted until cleared'
            session_plan['governance_override'] = reason
            reasons.append({'gate': 'H3', 'reason': reason})

        try:
            subjective_fatigue = int(context.get('subjective_fatigue_score', 0))
        except (TypeError, ValueError):
            subjective_fatigue = 0
        if subjective_fatigue >= SUBJECTIVE_FATIGUE_EXTREME:
            if str(session_plan.get('session_type', 'EASY')).upper() != 'REST':
                session_plan['session_type'] = 'EASY'
                session_plan['max_zone'] = min(int(session_plan.get('max_zone', 5)), 2)
            reason = 'Athlete-reported extreme fatigue: session downgraded'
            session_plan['governance_override'] = reason
            reasons.append({'gate': 'H4', 'reason': reason})

        return reasons

    def _check_vo2_eligibility(self, session_plan: Dict, context: Dict) -> Optional[Dict]:
        session_type = str(session_plan.get('session_type', '')).upper()
        zone = int(session_plan.get('zone', session_plan.get('max_zone', 0)) or 0)
        is_vo2_session = session_type in self._VO2_SESSIONS or (session_type == 'INTERVALS' and zone == 5)
        if not is_vo2_session:
            return None

        acwr_raw = context.get('acwr', 1.0)
        readiness_raw = context.get('readiness_score', 100)
        try:
            acwr = float(1.0 if acwr_raw is None else acwr_raw)
        except (TypeError, ValueError):
            acwr = 1.0
        try:
            readiness = float(100 if readiness_raw is None else readiness_raw)
        except (TypeError, ValueError):
            readiness = 100
        glycogen_debt = float(context.get('glycogen_debt', 0.0) or 0.0)
        fatigue_level = str(context.get('fatigue_level', 'LOW') or 'LOW').upper()
        days_since_last_vo2 = context.get('days_since_last_vo2', None)

        failed: List[str] = []
        reasons: List[str] = []
        if not (0.8 <= acwr <= 1.5):
            failed.append('V1')
            reasons.append(f'ACWR in [0.8,1.5] (actual: {acwr:.2f})')
        if readiness < 60:
            failed.append('V2')
            reasons.append(f'readiness >= 60 (actual: {readiness:.0f})')
        if glycogen_debt >= 7:
            failed.append('V3')
            reasons.append(f'glycogen_debt < 7 (actual: {glycogen_debt:.1f})')
        if fatigue_level == 'HIGH':
            failed.append('V4')
            reasons.append(f'fatigue != HIGH (actual: {fatigue_level})')

        if days_since_last_vo2 is not None:
            try:
                days_val = int(days_since_last_vo2)
            except (TypeError, ValueError):
                days_val = 999
            if days_val < 2:
                failed.append('V5')
                reasons.append(f'days_since_last_vo2 >= 2 (actual: {days_val})')

        original = 'INTERVALS_Z5' if session_type == 'INTERVALS' and zone == 5 else session_type
        if failed:
            session_plan['session_type'] = 'TEMPO'
            return {
                'eligible': False,
                'failed_conditions': failed,
                'original_session': original,
                'downgraded_to': 'TEMPO',
                'reason': 'VO2max session requires: ' + ', '.join(reasons),
            }
        return {
            'eligible': True,
            'failed_conditions': [],
            'original_session': original,
            'downgraded_to': None,
            'reason': 'All VO2 eligibility conditions satisfied',
        }

    def _check_fueling_gate(self, session_plan: Dict, context: Dict) -> Optional[Dict]:
        session_type = str(session_plan.get('session_type', '')).upper()
        duration = int(session_plan.get('duration_min', context.get('planned_duration_min', 0)) or 0)
        fueling_confirmed = bool(context.get('fueling_confirmed', False))

        if fueling_confirmed:
            return None

        if session_type in {'HAMMER', 'RACE'}:
            session_plan['session_type'] = 'TEMPO'
            return {
                'action': 'LOCK',
                'phase': 3,
                'reason': f'{session_type} session without confirmed fueling: unsafe glycogen depletion risk',
                'original_session': session_type,
                'locked_to': 'TEMPO',
            }

        if session_type in {'TEMPO', 'INTERVALS'} and duration >= 90:
            session_plan['session_type'] = 'EASY'
            return {
                'action': 'LOCK',
                'phase': 2,
                'reason': f'Quality session {duration} min without confirmed fueling: mandatory fueling not met',
                'original_session': session_type,
                'locked_to': 'EASY',
            }

        if session_type == 'LONG_RUN' and duration >= 90:
            session_plan['session_type'] = 'PROGRESSIVE'
            return {
                'action': 'LOCK',
                'phase': 4,
                'reason': f'LONG_RUN {duration} min without confirmed fueling: long-run fueling is required',
                'original_session': 'LONG_RUN',
                'locked_to': 'PROGRESSIVE',
            }

        if 60 <= duration <= 89 and session_type in {'TEMPO', 'INTERVALS'}:
            return {
                'action': 'FLAG',
                'phase': 2,
                'reason': f'Quality session {duration} min without confirmed fueling: performance risk',
                'session_unchanged': True,
            }

        if 60 <= duration <= 89 and session_type in {'EASY', 'PROGRESSIVE'}:
            return {
                'action': 'FLAG',
                'phase': 1,
                'reason': f'{session_type} {duration} min without confirmed fueling: recommended but optional',
                'session_unchanged': True,
            }

        return None

    def apply_constraints(self, session_plan: Dict, context: Dict) -> Dict:
        db = context.get('db')
        cs_tracker = context.get('cs_tracker')
        afi_constr = context.get('afi_constraints', {})
        applied_locks: List[str] = []

        intensity_gate = self._to_dict_maybe(context.get('intensity_gate_result'))
        if intensity_gate:
            session_plan['intensity_gate_result'] = intensity_gate
            color = str(intensity_gate.get('color', 'GREEN')).upper()
            session_plan['max_zone'] = min(int(session_plan.get('max_zone', 5) or 5), int(intensity_gate.get('max_zone', 5) or 5))
            session_plan['volume_modifier'] = float(intensity_gate.get('volume_modifier', 1.0) or 1.0)
            override = intensity_gate.get('session_override')
            if override:
                session_plan['session_type'] = override
            if color == 'RED':
                applied_locks.append('INTENSITY_GATE_RED')
            elif color == 'YELLOW':
                applied_locks.append('INTENSITY_GATE_YELLOW')

        count_2of4, indicators = self._evaluate_2of4_indicators(context)
        if count_2of4 >= 2:
            original = str(session_plan.get('session_type', 'EASY')).upper()
            downgraded = self._DOWNGRADE_MAP_2OF4.get(original, 'EASY')
            session_plan['session_type'] = downgraded
            session_plan['downgrade_2of4'] = {
                'downgrade_2of4': True,
                'count': count_2of4,
                'indicators_triggered': indicators,
                'original_session': original,
                'downgraded_to': downgraded,
            }
            applied_locks.append('READINESS_2OF4_DOWNGRADE')

        hard_stop_reasons = self._check_hard_stops(session_plan, context)
        if hard_stop_reasons:
            session_plan['hard_stop_reasons'] = hard_stop_reasons
            applied_locks.append('HARD_STOP_SAFETY_GATES')

        vo2_result = self._check_vo2_eligibility(session_plan, context)
        if vo2_result is not None:
            session_plan['vo2_eligibility'] = vo2_result
            if not vo2_result.get('eligible', True):
                applied_locks.append('VO2_ELIGIBILITY_GATE')

        fueling_result = self._check_fueling_gate(session_plan, context)
        if fueling_result is not None:
            session_plan['fueling_gate'] = fueling_result
            if fueling_result.get('action') == 'LOCK':
                applied_locks.append('FUELING_GATE_LOCK')
            else:
                applied_locks.append('FUELING_GATE_FLAG')

        para_guard = afi_constr.get('parasympathetic_guard', {})
        if para_guard.get('triggered'):
            session_plan['session_type'] = 'EASY'
            session_plan['max_zone'] = 2
            session_plan['governance_override'] = para_guard['reason']
            applied_locks.append('PARASYMPATHETIC_GUARD')

        if db:
            lock = self.check_override_lockdown(db)
            if lock['locked'] and session_plan.get('session_type') in lock['disabled_sessions']:
                session_plan['session_type'] = 'EASY'
                session_plan['max_zone'] = lock['max_zone']
                session_plan['governance_override'] = lock['reason']
                applied_locks.append('OVERRIDE_LOCKDOWN')

        if cs_tracker:
            cs_lock = self.check_cs_confidence_lock(cs_tracker)
            if cs_lock['locked']:
                session_plan['cs_prediction_disabled'] = True
                session_plan['required_calibration'] = True
                session_plan['cs_lock_reason'] = cs_lock['reason']
                applied_locks.append('CS_CONFIDENCE_LOCK')

        session_plan['governance_locks_applied'] = applied_locks
        session_plan['governance_clean'] = len(applied_locks) == 0
        return session_plan

    def get_governance_report(
        self,
        db: Optional[Any] = None,
        cs_tracker: Optional[Any] = None,
        afi_constraints: Optional[Dict] = None,
    ) -> Dict:
        return {
            'override_lockdown': self.check_override_lockdown(db) if db else {'locked': False},
            'cs_confidence_lock': self.check_cs_confidence_lock(cs_tracker) if cs_tracker else {'locked': False},
            'parasympathetic_guard': (afi_constraints or {}).get('parasympathetic_guard', {'triggered': False}),
        }

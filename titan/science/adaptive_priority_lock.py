"""
Adaptive Priority Lock (APL) — pre-governance gate priority resolver.

Answers a single question before GovernanceEngine runs:
  Given the current training phase, volume load, and autonomic state, in what
  order should the three governance gates be evaluated, and what adaptive
  thresholds should apply to each?

Design principles (from ADR-0008 / docs/specs/adaptive_priority_lock.md):
- GovernanceEngine gates are NOT touched. APL injects a priority_vector into
  the context dict; GovernanceEngine reads it and adjusts evaluation order.
- Stateless per call: no rolling history, no DB access, no side effects.
- PARASYMPATHETIC_GUARD is always rank 1. Non-negotiable.
- Layer purity: lives in titan/science/ because it performs physiological
  reasoning, not sequencing (orchestration) or utility math.
"""

import json
import logging
from typing import Dict, Optional

from titan.science.volume_load_gauge import VLGState

_log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Default thresholds — mirrors GovernanceEngine static class constants.
# APL may tighten or relax these per phase × load context.
# ──────────────────────────────────────────────────────────────────────────────
_DEFAULT_THRESHOLDS: Dict[str, float] = {
    'acwr_ceiling':      1.30,   # VO2_ACWR_MAX from thresholds.py
    'tsb_floor':         -50.0,  # HARD_STOP_TSB_FLOOR from thresholds.py
    'cs_min_confidence': 0.70,   # GovernanceEngine.CS_CONFIDENCE_THRESHOLD
}

# Per-spec threshold overrides (Section 5.3 of adaptive_priority_lock.md)
_THRESHOLD_OVERRIDES: Dict[str, Dict[str, float]] = {
    'PEAK':         {'acwr_ceiling': 1.10, 'tsb_floor': -20.0, 'cs_min_confidence': 0.85},
    'BUILD_OVERLOAD': {'acwr_ceiling': 1.15, 'tsb_floor': -40.0, 'cs_min_confidence': 0.60},
    'TAPER':        {'acwr_ceiling': 1.25, 'tsb_floor': -15.0, 'cs_min_confidence': 0.80},
}

# ──────────────────────────────────────────────────────────────────────────────
# Phase × load_band → (rank-2 gate, rank-3 gate, r2 rationale, r3 rationale)
# PARASYMPATHETIC_GUARD is rank 1 in every row (not stored; hardcoded below).
# Source: Section 5.2 of docs/specs/adaptive_priority_lock.md
# ──────────────────────────────────────────────────────────────────────────────
_PHASE_LOAD_MATRIX: Dict[tuple, tuple] = {
    # PEAK — CS model accuracy paramount for race-quality sessions
    ('PEAK', 'CRITICAL'): (
        'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN',
        'Race-quality sessions require a verified CS model regardless of load',
        'Load risk is secondary to CS accuracy during race preparation',
    ),
    ('PEAK', 'OVERLOAD'): (
        'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN',
        'Race-quality sessions require a verified CS model regardless of load',
        'Load risk is secondary to CS accuracy during race preparation',
    ),
    ('PEAK', 'OPTIMAL'): (
        'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN',
        'Race-quality sessions require a verified CS model',
        'Volume is under control — CS accuracy is the binding constraint',
    ),
    ('PEAK', 'UNDERLOAD'): (
        'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN',
        'Race-quality sessions require a verified CS model',
        'Volume is under control — CS accuracy is the binding constraint',
    ),

    # BUILD with high load — protect adaptation, block excess volume first
    ('BUILD', 'CRITICAL'): (
        'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
        'Protect adaptation: block excess volume before CS refinement',
        'CS refinement deferred when load is at critical level',
    ),
    ('BUILD', 'OVERLOAD'): (
        'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
        'Protect adaptation: block excess volume under overload',
        'CS refinement deferred while load is elevated',
    ),
    # BUILD with normal load — CS accuracy drives quality session quality
    ('BUILD', 'OPTIMAL'): (
        'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN',
        'CS model accuracy required for quality session prescription',
        'Volume is intact — CS model is the binding quality gate',
    ),
    ('BUILD', 'UNDERLOAD'): (
        'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN',
        'CS model accuracy required for quality session prescription',
        'Volume is below baseline — CS accuracy drives prescription quality',
    ),

    # BASE — volume integrity critical, CS model still accumulating
    ('BASE', 'CRITICAL'): (
        'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
        'Volume integrity is critical at BASE phase',
        'CS model still calibrating — volume protection takes priority',
    ),
    ('BASE', 'OVERLOAD'): (
        'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
        'Volume integrity critical at BASE phase',
        'CS model still calibrating — override risk contained first',
    ),
    ('BASE', 'OPTIMAL'): (
        'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
        'Volume integrity paramount during aerobic base building',
        'CS model accumulating data — override consistency enforced first',
    ),
    ('BASE', 'UNDERLOAD'): (
        'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
        'Volume integrity paramount during aerobic base building',
        'Underload means volume needs protection, not CS accuracy',
    ),

    # TAPER — CS model locks race-pace accuracy; volume naturally drops
    ('TAPER', 'CRITICAL'): (
        'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN',
        'CS model must lock race-pace accuracy for taper',
        'Volume naturally drops in taper — CS accuracy is the priority gate',
    ),
    ('TAPER', 'OVERLOAD'): (
        'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN',
        'CS model must lock race-pace accuracy for taper',
        'Volume naturally drops in taper — CS accuracy is the priority gate',
    ),
    ('TAPER', 'OPTIMAL'): (
        'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN',
        'CS model locks race-pace accuracy ahead of race day',
        'Volume is controlled — CS is the primary gate in taper',
    ),
    ('TAPER', 'UNDERLOAD'): (
        'CS_CONFIDENCE_LOCK', 'OVERRIDE_LOCKDOWN',
        'CS model locks race-pace accuracy ahead of race day',
        'Underload expected in taper — CS gate confirms readiness',
    ),

    # POST_RACE — recovery load protection above all else
    ('POST_RACE', 'CRITICAL'): (
        'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
        'Load must stay well below threshold during post-race recovery',
        'CS predictions deferred during post-race recovery phase',
    ),
    ('POST_RACE', 'OVERLOAD'): (
        'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
        'Load must stay below threshold during post-race recovery',
        'CS predictions deferred post-race',
    ),
    ('POST_RACE', 'OPTIMAL'): (
        'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
        'Post-race recovery — override integrity enforced',
        'CS predictions deferred post-race',
    ),
    ('POST_RACE', 'UNDERLOAD'): (
        'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK',
        'Post-race recovery — load protection active',
        'CS predictions deferred post-race',
    ),
}

_KNOWN_PHASES = {'BASE', 'BUILD', 'PEAK', 'TAPER', 'POST_RACE'}


def _vlg_to_load_band(vlg_state: VLGState) -> str:
    """
    Map the simplified VLGState (color + score) to the load_band string
    used in the APL phase × load matrix.

    VLGState.color is RED / YELLOW / GREEN.
    VLGState.score counts: RED components × 2 + YELLOW components.
    """
    color = str(getattr(vlg_state, 'color', 'GREEN')).upper()
    score = int(getattr(vlg_state, 'score', 0))
    if color == 'RED':
        # score ≥ 4 means multiple RED components — treat as truly critical
        return 'CRITICAL' if score >= 4 else 'OVERLOAD'
    if color == 'YELLOW':
        return 'OVERLOAD'
    return 'OPTIMAL'


class AdaptivePriorityLock:
    """
    Pre-governance priority resolver.

    Reads VLGState, AFI constraints, training phase, and CS confidence.
    Produces a priority_vector and adaptive lock_thresholds injected into
    GovernanceEngine.apply_constraints() via the context dict.

    Stateless: no instance state is mutated between calls.
    No DB access. No side effects.

    Output dict keys:
      priority_vector  — {gate_name: int rank}
                         PARASYMPATHETIC_GUARD is always rank 1.
      lock_thresholds  — {threshold_name: float}
                         Override static defaults in GovernanceEngine when present.
      apl_rationale    — {gate_name: str human-readable justification}
    """

    _SAFETY_GATE = 'PARASYMPATHETIC_GUARD'

    def resolve(
        self,
        vlg_state: VLGState,
        afi_constraints: dict,
        phase: str,
        cs_confidence: float,
    ) -> dict:
        """
        Resolve gate priority order and adaptive thresholds for the current context.

        Args:
            vlg_state:       Aggregated load state from VolumeLoadGauge.resolve().
            afi_constraints: Output of AutonomicFusionEngine.get_readiness_constraints().
            phase:           Current periodization phase
                             (BASE / BUILD / PEAK / TAPER / POST_RACE).
            cs_confidence:   CriticalSpeedTracker.confidence, float 0.0–1.0.

        Returns:
            dict with keys: priority_vector, lock_thresholds, apl_rationale.
        """
        phase_norm = str(phase or 'BASE').upper()
        if phase_norm not in _KNOWN_PHASES:
            _log.warning(
                'AdaptivePriorityLock: unknown phase %r — defaulting to BASE', phase_norm
            )
            phase_norm = 'BASE'

        load_band = _vlg_to_load_band(vlg_state)
        key = (phase_norm, load_band)

        row = _PHASE_LOAD_MATRIX.get(key)
        if row is None:
            # Should not happen given the matrix covers all phases × bands,
            # but guard defensively.
            rank2, rank3 = 'OVERRIDE_LOCKDOWN', 'CS_CONFIDENCE_LOCK'
            r2_rationale = f'Fallback default (no matrix entry for {key})'
            r3_rationale = 'Fallback default ordering'
        else:
            rank2, rank3, r2_rationale, r3_rationale = row

        priority_vector = {
            self._SAFETY_GATE: 1,
            rank2: 2,
            rank3: 3,
        }

        # ── Adaptive thresholds ──────────────────────────────────────────────
        thresholds = dict(_DEFAULT_THRESHOLDS)

        if phase_norm == 'BUILD' and load_band in ('OVERLOAD', 'CRITICAL'):
            thresholds.update(_THRESHOLD_OVERRIDES['BUILD_OVERLOAD'])
        elif phase_norm in _THRESHOLD_OVERRIDES:
            thresholds.update(_THRESHOLD_OVERRIDES[phase_norm])

        # Further tighten cs_min_confidence when calibration data is very sparse
        try:
            cs_conf = float(cs_confidence)
        except (TypeError, ValueError):
            cs_conf = 0.0

        if cs_conf < 0.50:
            # CS model has almost no data — raise the bar to force calibration
            thresholds['cs_min_confidence'] = max(
                thresholds['cs_min_confidence'], 0.85
            )

        # ── Rationale ────────────────────────────────────────────────────────
        para_triggered = bool(
            (afi_constraints or {})
            .get('parasympathetic_guard', {})
            .get('triggered', False)
        )
        safety_rationale = 'Safety gate — always rank 1, non-negotiable'
        if para_triggered:
            safety_rationale += ' (ACTIVE: parasympathetic guard triggered)'

        apl_rationale = {
            self._SAFETY_GATE: safety_rationale,
            rank2: r2_rationale,
            rank3: r3_rationale,
        }

        result = {
            'priority_vector': priority_vector,
            'lock_thresholds': thresholds,
            'apl_rationale': apl_rationale,
        }

        _log.info(json.dumps({
            'apl_resolve': True,
            'phase': phase_norm,
            'load_band': load_band,
            'vlg_color': getattr(vlg_state, 'color', 'UNKNOWN'),
            'vlg_score': getattr(vlg_state, 'score', 0),
            'cs_confidence': round(cs_conf, 3),
            'para_triggered': para_triggered,
            'priority_vector': priority_vector,
            'lock_thresholds': thresholds,
        }, default=str))

        return result

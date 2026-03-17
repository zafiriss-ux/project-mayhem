from titan.config.thresholds import GOVERNANCE_CS_CONFIDENCE_THRESHOLD
from titan.science.adaptive_priority_lock import AdaptivePriorityLock
from titan.science.volume_load_gauge import VLGState


def _vlg_state(color: str = "GREEN", score: int = 0) -> VLGState:
    return VLGState(color=color, score=score, components={}, rationale=[])


def test_default_cs_confidence_threshold_uses_canonical_constant_source():
    import titan.science.adaptive_priority_lock as apl_module

    assert (
        apl_module._DEFAULT_THRESHOLDS["cs_min_confidence"]
        == apl_module.GOVERNANCE_CS_CONFIDENCE_THRESHOLD
    )


def test_resolve_peak_phase_override_keeps_inline_cs_confidence_literal():
    result = AdaptivePriorityLock().resolve(
        vlg_state=_vlg_state(),
        afi_constraints={},
        phase="PEAK",
        cs_confidence=0.9,
    )

    assert result["lock_thresholds"]["cs_min_confidence"] == 0.85
    assert GOVERNANCE_CS_CONFIDENCE_THRESHOLD == 0.70

import pytest

from titan.config.thresholds import (
    DURABILITY_INDEX_COMPETITIVE_MIN,
    DURABILITY_INDEX_DEVELOPING_MIN,
    DURABILITY_INDEX_ELITE_MIN,
    DURABILITY_INDEX_WORLD_CLASS_MIN,
    DURABILITY_PACE_DECAY_EXCELLENT_MAX,
    DURABILITY_PACE_DECAY_GOOD_MAX,
    DURABILITY_PACE_DECAY_MODERATE_MAX,
    DURABILITY_PROTOCOL_BASE_BUILD_MAX,
    DURABILITY_PROTOCOL_MAINTENANCE_MAX,
    DURABILITY_PROTOCOL_STRONG_MAX,
)
from titan.science.durability_engine import DurabilityEngine


@pytest.mark.unit
def test_assess_pace_durability_covers_good_and_moderate_thresholds() -> None:
    # 12 km run → first_third=[300]*4
    km_splits_good = [300.0] * 8 + [312.0] * 4  # +4.0% decay (>=2 and <5)
    decay_good, status_good, recommendation_good = DurabilityEngine.assess_pace_durability(
        km_splits_good, target_pace_sec=300.0
    )

    assert decay_good == 4.0
    assert status_good == "✓ GOOD durability (<5% fade)"
    assert recommendation_good == "Solid - acceptable for most races"

    km_splits_moderate = [300.0] * 8 + [321.0] * 4  # +7.0% decay (>=5 and <8)
    decay_moderate, status_moderate, recommendation_moderate = (
        DurabilityEngine.assess_pace_durability(km_splits_moderate, target_pace_sec=300.0)
    )

    assert decay_moderate == 7.0
    assert status_moderate == "→ MODERATE fade (<8%)"
    assert recommendation_moderate == "Work on aerobic base & long runs"


@pytest.mark.unit
def test_durability_training_protocol_uses_93_boundary_path() -> None:
    # Exactly 93 should skip <93 branch and enter <96 branch
    protocols = DurabilityEngine.durability_training_protocol(current_di=93.0)

    assert protocols == [
        "✓ Durability strong - maintain current approach",
        "Occasional durability check: Long run with fast finish",
        "Focus can shift to speed/power work",
    ]


@pytest.mark.unit
def test_durability_training_protocol_covers_below_93_branch() -> None:
    protocols = DurabilityEngine.durability_training_protocol(current_di=92.9)

    assert protocols == [
        "Maintain weekly long run (2h+)",
        "Add 'fatigued intervals': Easy run → then intervals",
        "Monthly: Tempo after easy mileage (durability stimulus)",
        "One long run per month: Progressive with Hammer finish",
    ]


@pytest.mark.unit
def test_assess_pace_durability_returns_invalid_for_zero_first_third_average() -> None:
    km_splits = [0.0] * 4 + [300.0] * 8

    result = DurabilityEngine.assess_pace_durability(km_splits, target_pace_sec=300.0)

    assert result == (None, "Invalid pace data for durability assessment", None)


@pytest.mark.unit
def test_assess_pace_durability_returns_invalid_for_negative_first_third_average() -> None:
    km_splits = [-10.0] * 4 + [300.0] * 8

    result = DurabilityEngine.assess_pace_durability(km_splits, target_pace_sec=300.0)

    assert result == (None, "Invalid pace data for durability assessment", None)


@pytest.mark.unit
def test_calculate_durability_index_uses_threshold_constants() -> None:
    di_world_class = DurabilityEngine.calculate_durability_index(
        fresh_performance=100.0,
        fatigued_performance=(100.0 * 100.0 / DURABILITY_INDEX_WORLD_CLASS_MIN),
    )
    di_elite = DurabilityEngine.calculate_durability_index(
        fresh_performance=100.0,
        fatigued_performance=(100.0 * 100.0 / DURABILITY_INDEX_ELITE_MIN),
    )
    di_competitive = DurabilityEngine.calculate_durability_index(
        fresh_performance=100.0,
        fatigued_performance=(100.0 * 100.0 / DURABILITY_INDEX_COMPETITIVE_MIN),
    )
    di_developing = DurabilityEngine.calculate_durability_index(
        fresh_performance=100.0,
        fatigued_performance=(100.0 * 100.0 / DURABILITY_INDEX_DEVELOPING_MIN),
    )

    assert di_world_class == (98.0, "✓ ELITE durability (98%+)", "WORLD CLASS")
    assert di_elite == (95.0, "✓ EXCELLENT durability (95-98%)", "ELITE")
    assert di_competitive == (90.0, "✓ GOOD durability (90-95%)", "COMPETITIVE")
    assert di_developing == (85.0, "→ MODERATE durability (85-90%)", "DEVELOPING")


@pytest.mark.unit
def test_assess_pace_durability_uses_threshold_constants_for_good_and_moderate() -> None:
    km_splits_good = [300.0] * 8 + [
        300.0 * (1 + DURABILITY_PACE_DECAY_GOOD_MAX / 100.0)
    ] * 4
    good = DurabilityEngine.assess_pace_durability(km_splits_good, target_pace_sec=300.0)

    km_splits_moderate = [300.0] * 8 + [
        300.0 * (1 + DURABILITY_PACE_DECAY_MODERATE_MAX / 100.0)
    ] * 4
    moderate = DurabilityEngine.assess_pace_durability(km_splits_moderate, target_pace_sec=300.0)

    assert good == (
        DURABILITY_PACE_DECAY_GOOD_MAX,
        "→ MODERATE fade (<8%)",
        "Work on aerobic base & long runs",
    )
    assert moderate == (
        DURABILITY_PACE_DECAY_MODERATE_MAX,
        "⚠️ POOR durability (>8% fade)",
        "Priority: Build aerobic base, add volume",
    )


@pytest.mark.unit
def test_durability_training_protocol_uses_threshold_constants() -> None:
    base_build = DurabilityEngine.durability_training_protocol(
        current_di=(DURABILITY_PROTOCOL_BASE_BUILD_MAX - 0.1)
    )
    maintenance = DurabilityEngine.durability_training_protocol(
        current_di=(DURABILITY_PROTOCOL_MAINTENANCE_MAX - 0.1)
    )
    strong = DurabilityEngine.durability_training_protocol(
        current_di=(DURABILITY_PROTOCOL_STRONG_MAX - 0.1)
    )

    assert base_build[0] == "⚠️ PRIORITY 1: Build aerobic base (80% of runs easy)"
    assert maintenance[0] == "Maintain weekly long run (2h+)"
    assert strong[0] == "✓ Durability strong - maintain current approach"


@pytest.mark.unit
def test_assess_pace_durability_excellent_boundary_uses_threshold_constant() -> None:
    km_splits_excellent = [300.0] * 8 + [
        300.0 * (1 + DURABILITY_PACE_DECAY_EXCELLENT_MAX / 100.0)
    ] * 4

    result = DurabilityEngine.assess_pace_durability(km_splits_excellent, target_pace_sec=300.0)

    assert result == (
        DURABILITY_PACE_DECAY_EXCELLENT_MAX,
        "✓ GOOD durability (<5% fade)",
        "Solid - acceptable for most races",
    )

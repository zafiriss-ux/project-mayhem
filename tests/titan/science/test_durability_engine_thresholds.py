from titan.science.durability_engine import DurabilityEngine


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


def test_durability_training_protocol_uses_93_boundary_path() -> None:
    # Exactly 93 should skip <93 branch and enter <96 branch
    protocols = DurabilityEngine.durability_training_protocol(current_di=93.0)

    assert protocols == [
        "✓ Durability strong - maintain current approach",
        "Occasional durability check: Long run with fast finish",
        "Focus can shift to speed/power work",
    ]


def test_durability_training_protocol_covers_below_93_branch() -> None:
    protocols = DurabilityEngine.durability_training_protocol(current_di=92.9)

    assert protocols == [
        "Maintain weekly long run (2h+)",
        "Add 'fatigued intervals': Easy run → then intervals",
        "Monthly: Tempo after easy mileage (durability stimulus)",
        "One long run per month: Progressive with Hammer finish",
    ]

from titan.science.readiness_engine import ReadinessEngine


def test_analyze_readiness_covers_hrv_minus10_sleep_fair_and_soreness_moderate() -> None:
    # hrv_diff=-6 (between -8 and -5), sleep=65 (60-69), soreness=6 (>5)
    result = ReadinessEngine.analyze_readiness(
        today_hrv=44.0,
        baseline_hrv=50.0,
        today_rhr=50.0,
        baseline_rhr=50.0,
        sleep_score=65,
        soreness=6,
    )

    # 100 -10 (hrv) -8 (sleep) -10 (soreness) = 72
    assert result["score"] == 72
    assert result["status"] == "👍 GOOD"


def test_analyze_readiness_soreness_exactly_five_has_no_soreness_deduction() -> None:
    # Boundary check: soreness == 5 should not trigger >5 deduction branch
    result = ReadinessEngine.analyze_readiness(
        today_hrv=50.0,
        baseline_hrv=50.0,
        today_rhr=50.0,
        baseline_rhr=50.0,
        sleep_score=85,
        soreness=5,
    )

    # baseline 100 +5 sleep bonus = 105 clamped to 100
    assert result["score"] == 100
    assert result["status"] == "✅ EXCELLENT"

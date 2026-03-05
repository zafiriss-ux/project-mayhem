from pathlib import Path


def test_daily_coach_has_no_print_calls() -> None:
    source = Path("titan/orchestration/daily_coach.py").read_text(encoding="utf-8")
    assert "print(" not in source

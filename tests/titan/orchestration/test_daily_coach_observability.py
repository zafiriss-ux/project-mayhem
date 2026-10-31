from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.unit
def test_daily_coach_has_no_print_calls() -> None:
    source = (REPO_ROOT / "titan/orchestration/daily_coach.py").read_text(encoding="utf-8")
    assert "print(" not in source

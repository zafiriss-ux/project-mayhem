"""
Tests for physiological bounds validation — ADR-0023 / T1-18.

Covers:
- Happy-path: in-bounds values pass through unchanged
- Clamping: values slightly outside bounds are clamped
- Nulling: values wildly outside bounds are set to None
- hrv_ms = 0 special case: always nulled
- CTL/ATL/TSB division safety via DatabaseManager
- Integration: get_hrv_history() and get_baseline_rhr() apply bounds
"""

from __future__ import annotations

import math

import pytest

import titan.core.repositories.training as training_repository_module
from titan.science.physiological_bounds import (
    BOUNDS,
    BoundsViolation,
    validate_and_clamp,
    validate_single,
)


def _days_ago(n: int) -> str:
    """A date inside the "last N days" window of the history reads (F5, D-072)."""
    from datetime import UTC, datetime, timedelta

    return (datetime.now(UTC) - timedelta(days=n)).strftime("%Y-%m-%d")

# ─── validate_and_clamp: happy path ──────────────────────────────────────────


@pytest.mark.integration
def test_in_bounds_values_unchanged():
    data = {
        "hrv_ms": 55.0,
        "rhr_bpm": 48.0,
        "ctl": 75.0,
        "atl": 90.0,
        "glycogen_debt": 3.0,
        "temperature_c": 22.0,
    }
    result, violations = validate_and_clamp(data, "test")
    assert violations == []
    for field, value in data.items():
        assert result[field] == value


@pytest.mark.integration
def test_unknown_fields_pass_through():
    data = {"unknown_field": 999.9, "hrv_ms": 60.0}
    result, violations = validate_and_clamp(data, "test")
    assert result["unknown_field"] == 999.9
    assert violations == []


@pytest.mark.integration
def test_none_values_pass_through():
    data = {"hrv_ms": None, "rhr_bpm": None}
    result, violations = validate_and_clamp(data, "test")
    assert result["hrv_ms"] is None
    assert result["rhr_bpm"] is None
    assert violations == []


# ─── hrv_ms = 0: always nulled ───────────────────────────────────────────────


@pytest.mark.integration
def test_hrv_zero_always_nulled():
    result, violations = validate_and_clamp({"hrv_ms": 0.0}, "test")
    assert result["hrv_ms"] is None
    assert len(violations) == 1
    assert violations[0].action == "nulled"
    assert violations[0].field == "hrv_ms"


@pytest.mark.integration
def test_hrv_near_zero_but_not_zero_is_clamped_or_valid():
    # 0.05 is below lo=0.1 but within 1× span (299.9) so should clamp
    result, violations = validate_and_clamp({"hrv_ms": 0.05}, "test")
    assert result["hrv_ms"] == pytest.approx(0.1)
    assert violations[0].action == "clamped"


# ─── clamping: within 2× span ────────────────────────────────────────────────


@pytest.mark.integration
def test_value_slightly_above_hi_clamped():
    hi = BOUNDS["rhr_bpm"][1]  # 120.0
    result, violations = validate_and_clamp({"rhr_bpm": 125.0}, "test")
    assert result["rhr_bpm"] == hi
    assert violations[0].action == "clamped"


@pytest.mark.integration
def test_value_slightly_below_lo_clamped():
    lo = BOUNDS["rhr_bpm"][0]  # 25.0
    result, violations = validate_and_clamp({"rhr_bpm": 22.0}, "test")
    assert result["rhr_bpm"] == lo
    assert violations[0].action == "clamped"


@pytest.mark.integration
def test_glycogen_debt_negative_clamped_to_zero():
    lo = BOUNDS["glycogen_debt"][0]  # 0.0
    result, violations = validate_and_clamp({"glycogen_debt": -1.0}, "test")
    assert result["glycogen_debt"] == lo
    assert violations[0].action == "clamped"


# ─── nulling: beyond 2× span ─────────────────────────────────────────────────


@pytest.mark.integration
def test_rhr_artefact_nulled():
    # 200 bpm: (200-120)=80 excess; span=95 → 80 <= 95 → clamped, not nulled
    # But 300 bpm: (300-120)=180 excess; span=95 → 180 > 95 → nulled
    result, violations = validate_and_clamp({"rhr_bpm": 300.0}, "test")
    assert result["rhr_bpm"] is None
    assert violations[0].action == "nulled"


@pytest.mark.integration
def test_hrv_extreme_artefact_nulled():
    # hrv_ms = 800: (800-300)=500 excess; span=299.9 → 500 > 299.9 → nulled
    result, violations = validate_and_clamp({"hrv_ms": 800.0}, "test")
    assert result["hrv_ms"] is None
    assert violations[0].action == "nulled"


@pytest.mark.integration
def test_temperature_extreme_nulled():
    # -100°C: (-40 - -100)=60 excess; span=95 → 60 <= 95 → clamped
    result_clamp, v_clamp = validate_and_clamp({"temperature_c": -100.0}, "test")
    assert v_clamp[0].action == "clamped"
    # -200°C: (-40 - -200)=160 excess; span=95 → 160 > 95 → nulled
    result_null, v_null = validate_and_clamp({"temperature_c": -200.0}, "test")
    assert result_null["temperature_c"] is None
    assert v_null[0].action == "nulled"


# ─── validate_single convenience wrapper ─────────────────────────────────────


@pytest.mark.integration
def test_validate_single_valid():
    assert validate_single("hrv_ms", 55.0, "test") == 55.0


@pytest.mark.integration
def test_validate_single_none_passthrough():
    assert validate_single("hrv_ms", None, "test") is None


@pytest.mark.integration
def test_validate_single_clamped():
    result = validate_single("rhr_bpm", 125.0, "test")
    assert result == BOUNDS["rhr_bpm"][1]


@pytest.mark.integration
def test_validate_single_nulled():
    result = validate_single("rhr_bpm", 300.0, "test")
    assert result is None


# ─── BoundsViolation dataclass ────────────────────────────────────────────────


@pytest.mark.integration
def test_bounds_violation_fields():
    _, violations = validate_and_clamp({"hrv_ms": 0.0}, "ctx")
    v = violations[0]
    assert isinstance(v, BoundsViolation)
    assert v.field == "hrv_ms"
    assert v.value == 0.0
    assert v.lo == BOUNDS["hrv_ms"][0]
    assert v.hi == BOUNDS["hrv_ms"][1]
    assert v.action == "nulled"


# ─── multiple fields in one call ─────────────────────────────────────────────


@pytest.mark.integration
def test_mixed_valid_and_invalid_fields():
    data = {
        "hrv_ms": 55.0,        # valid
        "rhr_bpm": 300.0,      # nulled (extreme artefact)
        "glycogen_debt": -1.0, # clamped (negative impossible)
        "ctl": 80.0,           # valid
    }
    result, violations = validate_and_clamp(data, "test")
    assert result["hrv_ms"] == 55.0
    assert result["rhr_bpm"] is None
    assert result["glycogen_debt"] == 0.0
    assert result["ctl"] == 80.0
    assert len(violations) == 2


# ─── BOUNDS dict completeness ─────────────────────────────────────────────────


@pytest.mark.integration
def test_bounds_covers_required_fields():
    required = {
        "hrv_ms",
        "rhr_bpm",
        "ctl",
        "atl",
        "acwr",
        "glycogen_debt",
        "temperature_c",
        "dew_point_c",
        "weight_kg",
        "sleep_hours",
        "training_load",
    }
    assert required.issubset(set(BOUNDS.keys()))


@pytest.mark.integration
def test_bounds_lo_lt_hi_for_all_fields():
    for field, (lo, hi) in BOUNDS.items():
        assert lo < hi, f"BOUNDS[{field!r}]: lo ({lo}) must be < hi ({hi})"


# ─── Database integration: get_hrv_history filters artefacts ─────────────────


@pytest.mark.integration
def test_get_hrv_history_filters_artefact_values(tmp_path):
    """Sensor-artefact HRV values are excluded from get_hrv_history() output."""
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_bounds.db", db_dir=tmp_path)

    # Save one valid HRV and one artefact HRV
    db.save_daily_metric(date=_days_ago(2), hrv=55.0)
    db.save_daily_metric(date=_days_ago(1), hrv=850.0)  # extreme artefact → nulled

    rows = db.get_hrv_history(days=30)
    dates = [r[0] for r in rows]

    assert _days_ago(2) in dates
    assert _days_ago(1) not in dates  # artefact row excluded

    db.close()


@pytest.mark.integration
def test_get_hrv_history_clamps_mild_outlier(tmp_path):
    """Mildly out-of-bounds HRV is clamped and returned (not excluded)."""
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_bounds_clamp.db", db_dir=tmp_path)

    # 310 ms: (310-300)=10 excess; span=299.9 → 10 <= 299.9 → clamped to 300.0
    db.save_daily_metric(date=_days_ago(2), hrv=310.0)

    rows = db.get_hrv_history(days=30)
    assert len(rows) == 1
    assert rows[0][1] == pytest.approx(300.0)  # clamped to hi bound

    db.close()


# ─── Database integration: get_baseline_rhr validates output ─────────────────


@pytest.mark.integration
def test_get_baseline_rhr_clamps_high_value(tmp_path):
    """Mildly elevated RHR is clamped to the bound ceiling."""
    import datetime

    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_rhr_clamp.db", db_dir=tmp_path)

    # Use today's date so it falls within the 7-day window
    today = datetime.date.today().isoformat()
    # rhr=125: (125-120)=5 excess; span=95 → 5 <= 95 → clamped to 120
    db.save_daily_metric(date=today, rhr=125)
    result = db.get_baseline_rhr(days=7)
    assert result == pytest.approx(BOUNDS["rhr_bpm"][1])  # 120.0

    db.close()


# ─── Database integration: get_ctl_atl_tsb returns safe values ───────────────


@pytest.mark.integration
def test_get_ctl_atl_tsb_zero_load_returns_zeros(tmp_path):
    """New athlete with no training history: CTL=0, ATL=0, TSB=0 (no NaN/Inf)."""
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_ctl_zero.db", db_dir=tmp_path)

    ctl, atl, tsb = db.get_ctl_atl_tsb()
    assert ctl == 0.0
    assert atl == 0.0
    assert tsb == 0.0
    assert not math.isnan(ctl)
    assert not math.isnan(atl)

    db.close()




@pytest.mark.integration
def test_get_ctl_atl_tsb_matches_explicit_decay_constants(tmp_path):
    """Happy path: DB CTL/ATL uses centralized decay constants by default."""
    from titan.config.thresholds import ATL_DECAY_DAYS, CTL_DECAY_DAYS
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_ctl_canonical_defaults.db", db_dir=tmp_path)

    for i in range(21):
        db.save_session(
            date=f"2026-02-{i + 1:02d}",
            session_type="EASY",
            distance_km=8.0 + (i % 5),
            duration_sec=2800 + (i * 30),
            rpe=4 + (i % 3),
        )

    default_ctl, default_atl, _ = db.get_ctl_atl_tsb()

    loads = db.get_training_load_history(CTL_DECAY_DAYS)
    chronological_loads = list(reversed(loads))

    ctl = 0.0
    ctl_alpha = 2 / (CTL_DECAY_DAYS + 1)
    for _date, load in chronological_loads:
        ctl = (load * ctl_alpha) + (ctl * (1 - ctl_alpha))

    atl = 0.0
    atl_alpha = 2 / (ATL_DECAY_DAYS + 1)
    for load in [load for _d, load in chronological_loads][-ATL_DECAY_DAYS:]:
        atl = (load * atl_alpha) + (atl * (1 - atl_alpha))

    assert default_ctl == round(ctl, 1)
    assert default_atl == round(atl, 1)

    db.close()


@pytest.mark.integration
def test_get_ctl_atl_tsb_changes_when_canonical_decay_constants_change(tmp_path, monkeypatch):
    """Boundary path: changing canonical constants shifts DB CTL/ATL output."""
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_ctl_canonical_boundary.db", db_dir=tmp_path)

    import datetime
    today = datetime.date.today()
    for i in range(28):
        d = today - datetime.timedelta(days=27 - i)
        db.save_session(
            date=d.isoformat(),
            session_type="TEMPO",
            distance_km=6.0 + (i % 7),
            duration_sec=2400 + (i * 45),
            rpe=5 + (i % 4),
        )

    baseline_ctl, baseline_atl, _ = db.get_ctl_atl_tsb()

    # Plan #18: the SQLite load-history SQL reads the constants from the repository.
    monkeypatch.setattr(training_repository_module, "CTL_DECAY_DAYS", 14)
    monkeypatch.setattr(training_repository_module, "ATL_DECAY_DAYS", 4)

    shifted_ctl, shifted_atl, _ = db.get_ctl_atl_tsb()

    assert shifted_ctl != baseline_ctl
    assert shifted_atl != baseline_atl

    db.close()

@pytest.mark.integration
def test_get_ctl_atl_tsb_with_normal_load(tmp_path):
    """Normal training history: CTL and ATL within BOUNDS."""
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_ctl_normal.db", db_dir=tmp_path)

    for i in range(14):
        db.save_session(
            date=f"2026-01-{i + 1:02d}",
            session_type="EASY",
            distance_km=10.0,
            duration_sec=3600,
            rpe=5,
        )

    ctl, atl, tsb = db.get_ctl_atl_tsb()
    assert BOUNDS["ctl"][0] <= ctl <= BOUNDS["ctl"][1]
    assert BOUNDS["atl"][0] <= atl <= BOUNDS["atl"][1]

    db.close()


@pytest.mark.integration
def test_get_weight_history_filters_extreme_artefact_values(tmp_path):
    """Extreme weight artefacts are nulled and removed from DB read path output."""
    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_weight_bounds.db", db_dir=tmp_path)

    db.save_daily_metric(date=_days_ago(2), weight=72.0)
    db.save_daily_metric(date=_days_ago(1), weight=900.0)  # extreme artefact

    rows = db.get_weight_history(days=30)
    dates = [r[0] for r in rows]

    assert _days_ago(2) in dates
    assert _days_ago(1) not in dates

    db.close()


@pytest.mark.integration
def test_get_training_load_history_clamps_mild_outlier(tmp_path):
    """Slightly out-of-bounds training load is clamped and retained."""
    import datetime

    from titan.core.database import DatabaseManager

    db = DatabaseManager(db_name="test_training_load_bounds.db", db_dir=tmp_path)

    today = datetime.date.today().isoformat()
    db.save_session(
        date=today,
        session_type="RACE",
        distance_km=42.2,
        duration_sec=18000,
        rpe=9,
    )

    rows = db.get_training_load_history(days=30)
    assert len(rows) == 1
    assert rows[0][1] == pytest.approx(BOUNDS["training_load"][1])

    db.close()

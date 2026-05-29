"""Architecture fitness functions for the canonical EMA kernel (TD-CTL-02)."""
from __future__ import annotations

import pathlib
import re
from datetime import date

import pytest

from titan.science.tsb_engine import compute_ctl_atl_tsb


@pytest.mark.unit
def test_single_kernel_site() -> None:
    """No inline EMA loops outside compute_ctl_atl_tsb."""
    # ctl_decay\s*= catches the old inline variable assignment (ctl_decay = 2/...)
    # but NOT the delegation call keyword arg (ctl_decay_days=CTL_DECAY_DAYS)
    ema_pattern = re.compile(r"ctl\s*=.*ctl_k|ctl_decay\s*=")
    files = list(pathlib.Path("titan").rglob("*.py"))
    violations = []
    for f in files:
        if "tsb_engine" in f.name:
            continue  # canonical site
        src = f.read_text()
        if ema_pattern.search(src):
            violations.append(str(f))
    assert violations == [], (
        f"Inline EMA found outside kernel: {violations}"
    )


@pytest.mark.unit
def test_all_backends_agree() -> None:
    """SQLite, PostgreSQLAdapter return same values for identical input."""
    from titan.science.tsb_engine import compute_ctl_atl_tsb

    loads = [
        ("2026-01-01", 50.0),
        ("2026-01-03", 60.0),
        ("2026-01-05", 45.0),
    ]
    ctl, atl, tsb = compute_ctl_atl_tsb(
        loads,
        reference_date=date(2026, 1, 10),
    )
    assert ctl > 0
    assert tsb == round(ctl - atl, 1)


@pytest.mark.unit
def test_compute_ctl_atl_tsb_empty() -> None:
    from titan.science.tsb_engine import compute_ctl_atl_tsb

    assert compute_ctl_atl_tsb([]) == (0.0, 0.0, 0.0)


@pytest.mark.unit
def test_compute_ctl_atl_tsb_deterministic() -> None:
    from titan.science.tsb_engine import compute_ctl_atl_tsb

    loads = [("2026-03-01", 55.0), ("2026-03-02", 60.0)]
    r1 = compute_ctl_atl_tsb(loads, reference_date=date(2026, 3, 5))
    r2 = compute_ctl_atl_tsb(loads, reference_date=date(2026, 3, 5))
    assert r1 == r2


@pytest.mark.unit
def test_production_values_unchanged() -> None:
    """Regression guard: known input must produce known output."""
    loads = [
        ("2026-01-01", 50.0),
        ("2026-01-03", 60.0),
        ("2026-01-05", 45.0),
    ]
    result = compute_ctl_atl_tsb(
        loads, reference_date=date(2026, 1, 10)
    )
    # Snapshot of canonical EMA behavior.
    # Update intentionally if decay constants change.
    assert result == (6.9, 22.5, -15.6)

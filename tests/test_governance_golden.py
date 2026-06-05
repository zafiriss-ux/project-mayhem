"""
Governance decision regression snapshot.

If this test fails: governance output changed. Verify the change is intentional,
then run: pytest --update-golden
Commit the updated golden file with ADR reference in commit message.

Golden path: healthy INTERVALS athlete — all gates pass, governance_clean=True.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from titan.science.governance_engine import GovernanceEngine

GOLDEN_PATH = Path("tests/fixtures/governance_golden.json")


# ── Stubs ──────────────────────────────────────────────────────────────────────


class _NeutralDB:
    """DB stub: 0% override ratio — no lockdown."""

    def get_override_ratio(self, **_kwargs: object) -> float:
        return 0.0


class _FullCSTracker:
    """CS tracker stub at full confidence — no CS lock."""

    confidence = 1.0


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def governance_engine_no_adapter() -> GovernanceEngine:
    """GovernanceEngine with no ThresholdAdapter — deterministic threshold behaviour."""
    return GovernanceEngine()


@pytest.fixture(scope="module")
def canonical_governance_inputs() -> tuple[dict, dict]:
    """Canonical healthy-athlete INTERVALS scenario: all gates pass."""
    plan: dict = {"session_type": "INTERVALS", "max_zone": 5}
    ctx: dict = {
        "today_hrv": 60.0,
        "baseline_hrv": 60.0,
        "hrv_std_dev": 5.0,
        "today_rhr": 50,
        "baseline_rhr": 50.0,
        "tsb_value": 0.0,
        "subjective_fatigue_score": 0,
        "injury_flag": False,
        "sleep_score": 80,
        "readiness_score": 75.0,
        "acwr": 1.1,
        "glycogen_debt": 2.0,
        "days_since_last_vo2": 3,
        "fueling_confirmed": True,
        "db": _NeutralDB(),
        "cs_tracker": _FullCSTracker(),
        "afi_constraints": {},
        "intensity_gate_result": None,
    }
    return plan, ctx


# ── Helpers ────────────────────────────────────────────────────────────────────


def _to_serializable(obj: object) -> object:
    """Strip non-JSON types: NaN/Inf → None; everything else recurses."""
    if isinstance(obj, dict):
        return {k: _to_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_serializable(v) for v in obj]
    if isinstance(obj, float):
        return None if (math.isnan(obj) or math.isinf(obj)) else obj
    if isinstance(obj, (int, str, bool, type(None))):
        return obj
    return str(obj)


# ── Test ───────────────────────────────────────────────────────────────────────


@pytest.mark.unit
@pytest.mark.governance
def test_governance_output_matches_golden(
    governance_engine_no_adapter: GovernanceEngine,
    canonical_governance_inputs: tuple[dict, dict],
    request: pytest.FixtureRequest,
) -> None:
    """Regression guard: governance canonical output must match stored golden file."""
    plan, ctx = canonical_governance_inputs
    # apply_constraints mutates plan in-place; work on a copy so the fixture stays clean
    import copy
    result = governance_engine_no_adapter.apply_constraints(copy.deepcopy(plan), ctx)
    serializable = _to_serializable(result)

    if request.config.getoption("--update-golden"):
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(json.dumps(serializable, indent=2, sort_keys=True))
        pytest.skip("Golden file updated — commit with ADR reference.")

    assert GOLDEN_PATH.exists(), (
        "tests/fixtures/governance_golden.json missing. "
        "Run: pytest --update-golden to generate."
    )
    golden = json.loads(GOLDEN_PATH.read_text())
    assert serializable == golden, (
        "Governance output changed unexpectedly.\n"
        "If intentional: pytest --update-golden + commit with ADR reference.\n"
        f"Diff keys: {set(str(serializable)) ^ set(str(golden))}"
    )

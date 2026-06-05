"""
T5-68: ESI dew_point fallback must be a named constant, not a magic literal.

Acceptance criteria:
  1. 12.0 no longer appears as a dew_point literal in daily_coach.py.
  2. thresholds.py has ESI_DEW_POINT_FALLBACK_C.
  3. evidence_registry.py has an entry for ESI_DEW_POINT_FALLBACK_C.
  4. ESI_DEW_POINT_FALLBACK_C >= 18.0 (conservative per ADR-0034 / ADR-0051).
"""

import ast
import pathlib

import pytest

from titan.config.evidence_registry import EVIDENCE_REGISTRY
from titan.config.thresholds import ESI_DEW_POINT_FALLBACK_C

DAILY_COACH_PATH = pathlib.Path("titan/orchestration/daily_coach.py")
THRESHOLDS_PATH = pathlib.Path("titan/config/thresholds.py")


class TestEsiDewPointFallbackConstant:

    @pytest.mark.unit
    @pytest.mark.governance
    def test_constant_exists_in_thresholds(self):
        """ESI_DEW_POINT_FALLBACK_C is importable from thresholds."""
        assert isinstance(ESI_DEW_POINT_FALLBACK_C, float)

    @pytest.mark.unit
    @pytest.mark.governance
    def test_constant_is_conservative(self):
        """ESI_DEW_POINT_FALLBACK_C must be >= 18.0°C (ADR-0034 / ADR-0051)."""
        assert ESI_DEW_POINT_FALLBACK_C >= 18.0, (
            f"ESI_DEW_POINT_FALLBACK_C={ESI_DEW_POINT_FALLBACK_C} is below 18.0°C; "
            "12.0°C (comfortable) would underestimate thermal stress when data is absent."
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_evidence_registry_has_entry(self):
        """ESI_DEW_POINT_FALLBACK_C must have a provenance entry in evidence_registry."""
        assert "ESI_DEW_POINT_FALLBACK_C" in EVIDENCE_REGISTRY, (
            "ESI_DEW_POINT_FALLBACK_C missing from EVIDENCE_REGISTRY"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_evidence_registry_value_matches_constant(self):
        """Registry value must mirror the live constant value."""
        entry = EVIDENCE_REGISTRY["ESI_DEW_POINT_FALLBACK_C"]
        assert entry.value == pytest.approx(ESI_DEW_POINT_FALLBACK_C), (
            f"Registry value {entry.value} != constant {ESI_DEW_POINT_FALLBACK_C}"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_hardcoded_12_not_present_as_dew_point_literal_in_daily_coach(self):
        """12.0 must not appear as a dew_point default literal in daily_coach.py.

        Parses the AST to find Call nodes where the keyword 'dew_point_c' is
        passed a literal numeric value of 12.0.
        """
        source = DAILY_COACH_PATH.read_text()
        tree = ast.parse(source)

        violations = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if (
                    kw.arg == "dew_point_c"
                    and isinstance(kw.value, ast.Constant)
                    and kw.value.value == 12.0
                ):
                    violations.append(
                        f"line {kw.value.lineno}: dew_point_c={kw.value.value!r}"
                    )

        assert not violations, (
            f"Hardcoded 12.0 still present as dew_point_c literal in daily_coach.py: "
            f"{violations}"
        )

    @pytest.mark.unit
    @pytest.mark.governance
    def test_daily_coach_imports_esi_dew_point_fallback(self):
        """daily_coach.py must import ESI_DEW_POINT_FALLBACK_C from thresholds."""
        source = DAILY_COACH_PATH.read_text()
        assert "ESI_DEW_POINT_FALLBACK_C" in source, (
            "ESI_DEW_POINT_FALLBACK_C not referenced in daily_coach.py"
        )

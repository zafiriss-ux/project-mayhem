#!/usr/bin/env bash
# TITAN OS — Gate Coverage Matrix (D-21 / T5-96)
# Reports coverage across 4 dimensions per governance gate:
#   (a) boundary trigger test
#   (b) boundary non-trigger test
#   (c) NaN/None input test
#   (d) combined-gate interaction test
#
# Usage: bash scripts/gate_coverage_matrix.sh
# Output: 9×4 matrix showing COVERED/MISSING per cell

set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo ""
echo "═══ TITAN OS Gate Coverage Matrix (D-21) ═══"
echo "Governance gates: H1-H5, FUELING, INTENSITY, 2-of-4, VO2"
echo "Dimensions: (a) trigger boundary, (b) non-trigger boundary,"
echo "            (c) NaN/None input, (d) combined-gate interaction"
echo ""

python3 - <<'PYEOF'
import re
from pathlib import Path

GATE_TEST_PATTERNS = {
    "H1_OVERRIDE_LOCKDOWN": {
        "a_trigger":    ["override_lockdown", "OVERRIDE_LOCKDOWN", r"lockdown.*trigger"],
        "b_nontrigger": [r"override.*below", r"no.*lockdown", r"lockdown.*not.*fire"],
        "c_nan_none":   [r"lockdown.*None", r"lockdown.*nan", r"None.*lockdown"],
        "d_combined":   [r"lockdown.*and.*h2", r"combined.*lockdown", r"lockdown.*interaction"],
    },
    "H2_HRV_DELTA": {
        "a_trigger":    [r"h2.*trigger", r"hrv.*delta.*fire", r"HRV_DELTA.*hard.stop", "HARD_STOP_HRV"],
        "b_nontrigger": [r"h2.*not.*fire", r"hrv.*below.*threshold", r"no.*h2"],
        "c_nan_none":   [r"hrv.*None", r"None.*hrv", "DATA_MISSING_CONSERVATIVE_H2"],
        "d_combined":   [r"h2.*and.*h3", r"combined.*hrv", r"h2.*interaction"],
    },
    "H3_RHR_SPIKE": {
        "a_trigger":    [r"h3.*trigger", r"rhr.*spike.*fire", "RHR_SPIKE", "HARD_STOP_RHR"],
        "b_nontrigger": [r"h3.*not.*fire", r"rhr.*below", r"no.*h3"],
        "c_nan_none":   [r"rhr.*None", r"None.*rhr", "DATA_MISSING_CONSERVATIVE_H3"],
        "d_combined":   [r"h3.*and.*h2", r"combined.*rhr", r"h3.*interaction"],
    },
    "H4_ACWR": {
        "a_trigger":    [r"h4.*trigger", r"acwr.*ceiling", r"ACWR.*hard", r"acwr.*floor"],
        "b_nontrigger": [r"h4.*not.*fire", r"acwr.*safe", r"no.*h4"],
        "c_nan_none":   [r"acwr.*None", r"None.*acwr", r"acwr.*missing"],
        "d_combined":   [r"h4.*and.*h", r"combined.*acwr", r"h4.*interaction"],
    },
    "H5_CONSECUTIVE": {
        "a_trigger":    [r"h5.*trigger", r"consecutive.*hard", "CONSECUTIVE_HARD", r"hard.*session.*count"],
        "b_nontrigger": [r"h5.*not.*fire", r"consecutive.*below", r"no.*h5"],
        "c_nan_none":   [r"consecutive.*None", r"None.*consecutive", r"h5.*missing"],
        "d_combined":   [r"h5.*and.*h", r"combined.*consecutive", r"h5.*interaction"],
    },
    "FUELING_GATE": {
        "a_trigger":    [r"fueling.*trigger", r"FUELING.*fire", r"glycogen.*gate", "FUELING_GATE_LOCK"],
        "b_nontrigger": [r"fueling.*not.*fire", r"fueling.*below", r"no.*fueling"],
        "c_nan_none":   [r"fueling.*None", r"None.*fueling", r"glycogen.*missing"],
        "d_combined":   [r"fueling.*and.*h", r"combined.*fueling", r"fueling.*interaction"],
    },
    "INTENSITY_GATE": {
        "a_trigger":    [r"intensity.*trigger", r"INTENSITY.*fire", r"intensity.*gate.*lock", "INTENSITY_GATE_RED"],
        "b_nontrigger": [r"intensity.*not.*fire", r"intensity.*below", r"no.*intensity"],
        "c_nan_none":   [r"intensity.*None", r"None.*intensity", r"intensity.*missing"],
        "d_combined":   [r"intensity.*and.*h", r"combined.*intensity"],
    },
    "2_OF_4_GATE": {
        "a_trigger":    [r"2.of.4.*trigger", r"two.*of.*four.*fire", "2_of_4.*lock", "READINESS_2OF4"],
        "b_nontrigger": [r"2.of.4.*not.*fire", r"one.*of.*four", r"no.*2.of.4"],
        "c_nan_none":   [r"sleep.*None.*2of4", r"readiness.*None.*2of4", r"2of4.*missing"],
        "d_combined":   [r"2of4.*and.*h", r"combined.*2of4", r"2of4.*interaction"],
    },
    "VO2_ELIGIBILITY": {
        "a_trigger":    [r"vo2.*eligible", r"VO2.*eligible", r"vo2.*gate.*pass", "VO2_ELIGIBILITY"],
        "b_nontrigger": [r"vo2.*ineligible", r"VO2.*not.*eligible", r"vo2.*blocked"],
        "c_nan_none":   [r"vo2.*None", r"None.*vo2", r"vo2.*missing", r"acwr.*None.*vo2"],
        "d_combined":   [r"vo2.*and.*h", r"combined.*vo2", r"vo2.*interaction"],
    },
}

# Collect all test source (root + tests/)
test_sources = []
for pattern in ("test_*.py", "tests/**/test_*.py"):
    for f in Path(".").glob(pattern):
        try:
            test_sources.append(f.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            pass
combined = "\n".join(test_sources)

DIMS = ["a_trigger", "b_nontrigger", "c_nan_none", "d_combined"]
DIM_LABELS = ["(a)trigger  ", "(b)no-trig  ", "(c)NaN/None ", "(d)combined "]

header = f"{'Gate':<22} " + " ".join(f"{d}" for d in DIM_LABELS) + " Score"
sep = "─" * (22 + 1 + len(DIM_LABELS) * 13 + 6)
print(header)
print(sep)

total_cells = 0
covered_cells = 0

for gate, patterns in GATE_TEST_PATTERNS.items():
    row = f"{gate:<22} "
    gate_covered = 0
    for dim in DIMS:
        pats = patterns.get(dim, [])
        found = any(
            re.search(p, combined, re.IGNORECASE)
            for p in pats
        )
        cell = "✅ COVERED  " if found else "❌ MISSING  "
        row += cell
        if found:
            gate_covered += 1
            covered_cells += 1
        total_cells += 1
    row += f" {gate_covered}/4"
    print(row)

print(sep)
pct = covered_cells / total_cells * 100 if total_cells else 0
print(f"{'TOTAL':<22} {covered_cells}/{total_cells} cells covered ({pct:.0f}%)")
print()
if pct < 75:
    print("  ⚠️  Gate coverage below 75% — consider adding boundary tests")
elif pct < 90:
    print("  ℹ️  Gate coverage adequate — some gaps remain")
else:
    print("  ✅ Gate coverage excellent")
PYEOF

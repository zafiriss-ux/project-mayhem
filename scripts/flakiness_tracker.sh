#!/usr/bin/env bash
# TITAN OS — Flakiness Tracker (D-5 / T5-88)
# Runs the test suite N times and reports tests that don't pass every time.
# Usage: bash scripts/flakiness_tracker.sh [runs=3] [filter=]
# Example: bash scripts/flakiness_tracker.sh 5 garmin
#
# Output: per-test PASS/FLAKY/FAIL summary
# Tests with <100% pass rate → quarantine candidates (T5-83 pattern)

set -euo pipefail
RUNS="${1:-3}"
FILTER="${2:-}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

PYTEST_BIN="${PYTEST_BIN:-.venv/bin/pytest}"
if [ ! -f "$PYTEST_BIN" ]; then
    if _pb=$(which pytest 2>/dev/null); then
        PYTEST_BIN="$_pb"
    fi
fi

RESULTS_DIR=".flakiness_results"
mkdir -p "$RESULTS_DIR"

echo ""
echo "═══ TITAN OS Flakiness Tracker ═══"
echo "Runs: $RUNS | Filter: ${FILTER:-all tests}"
echo ""

# Run suite N times, capture per-test status lines.
# --override-ini="addopts=" suppresses pyproject.toml coverage flags for speed.
# --continue-on-collection-errors handles pre-existing collection failures.
for i in $(seq 1 "$RUNS"); do
    echo "Run $i/$RUNS..."
    PYTEST_ARGS='-v --tb=no --override-ini=addopts= --continue-on-collection-errors'
    if [ -n "$FILTER" ]; then
        PYTEST_ARGS="$PYTEST_ARGS -k $FILTER"
    fi
    # shellcheck disable=SC2086
    $PYTEST_BIN $PYTEST_ARGS 2>&1 \
        | grep -E " (PASSED|FAILED|ERROR)( |$)" \
        > "$RESULTS_DIR/run_${i}.txt" || true
done

# Aggregate results and report
echo ""
echo "── Results ──"
python3 - <<'PYEOF'
import os, glob
from collections import defaultdict

results_dir = ".flakiness_results"
files = sorted(glob.glob(f"{results_dir}/run_*.txt"))

if not files:
    print("  ⚠️  No run files found — pytest may have produced no per-test output")
    exit(0)

test_results = defaultdict(list)
for f in files:
    with open(f) as fh:
        for line in fh:
            line = line.strip()
            # pytest -v format: "path::test_name PASSED" or "path::test_name FAILED"
            for status in ("PASSED", "FAILED", "ERROR"):
                if f" {status}" in line:
                    name = line.split(f" {status}")[0].strip()
                    test_results[name].append(status)
                    break

flaky = []
failing = []
for name, statuses in sorted(test_results.items()):
    if all(s == "PASSED" for s in statuses):
        continue
    elif all(s != "PASSED" for s in statuses):
        failing.append((name, statuses))
    else:
        flaky.append((name, statuses))

if not flaky and not failing:
    print("  ✅ No flaky or consistently failing tests detected")
else:
    if flaky:
        print(f"  ⚠️  FLAKY ({len(flaky)} tests — quarantine candidates):")
        for name, statuses in flaky:
            rate = statuses.count("PASSED") / len(statuses) * 100
            print(f"    {name}: {rate:.0f}% pass rate {statuses}")
    if failing:
        print(f"  ❌ CONSISTENTLY FAILING ({len(failing)} tests):")
        for name, statuses in failing:
            print(f"    {name}: {statuses}")

print(f"\n  Total unique tests tracked: {len(test_results)}")
PYEOF

# Cleanup
rm -rf "$RESULTS_DIR"

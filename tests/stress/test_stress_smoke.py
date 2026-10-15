"""Smoke test for the DB stress harness (scripts/stress/run_stress.py) at a tiny size.

Runs the harness in a subprocess (it reconfigures root logging) against disposable
databases under tmp_path. PostgreSQL, the bulk-insert phase and the concurrency phase are
skipped to keep the run short; the full run is documented in docs/validation/db-stress-report.md.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "stress" / "run_stress.py"


@pytest.mark.slow
def test_stress_harness_tiny_run(tmp_path: Path) -> None:
    out = tmp_path / "stress"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--tiny", "--athletes", "8", "--skip-pg", "--skip-bulk",
         "--skip-concurrency", "--out", str(out)],
        capture_output=True, text=True, timeout=600, cwd=str(REPO), check=False,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    res = json.loads((out / "results.json").read_text())

    assert res["environment"]["pragmas_as_set_by_DatabaseManager"]["journal_mode"] == "wal"
    assert res["db_deleted"] is True
    verdicts = {c["id"]: c["verdict"] for c in res["thresholds_evaluation"]}
    assert len(verdicts) == 20
    # Integrity, idempotency, isolation and crash-safety must hold even at tiny size.
    for tid in ("T12", "T13", "T14", "T15", "T16"):
        assert verdicts[tid] == "PASS", (tid, res["thresholds_evaluation"])
    assert res["phase4_resync"]["duplicate_garmin_ids_after"] == 0
    assert res["backup_restore"]["restore_row_mismatch"] == 0

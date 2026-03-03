from pathlib import Path


def test_adr_0014_records_t5_04_promotion_controls():
    text = Path("docs/adr/0014-phase7-ml-scaffold-shadow-advisory-mode.md").read_text(
        encoding="utf-8"
    )

    assert "Promotion Control Requirements (T5-04)" in text
    assert "LoadPredictionShadowModel" in text
    assert "InjuryRiskEnsembleModel" in text
    assert "AutomatedPeriodizationEngine" in text
    assert "HEURISTIC" in text and "MODERATE" in text
    assert "TITAN_ML_KILL_SWITCH=0" in text


def test_roadmap_tracks_t5_04_gate_policy():
    text = Path("docs/ROADMAP.MD").read_text(encoding="utf-8")

    assert "T5-04 · ML promotion gates (DECIDED)" in text
    assert "recall ≥0.80" in text
    assert "false positive rate <0.30" in text
    assert "Operator Console calibration review shows promotion readiness checklist" in text


def test_readme_deployment_env_documents_kill_switch_disable():
    text = Path("README.md").read_text(encoding="utf-8")

    assert "Phase 7 ML promotion control" in text
    assert "TITAN_ML_KILL_SWITCH=0" in text

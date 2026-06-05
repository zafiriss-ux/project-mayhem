#!/usr/bin/env python3
"""Apply pytest markers to root-level test files."""

import re
from pathlib import Path

MARKERS: dict[str, list[str]] = {
    "test_adr0052_stage4_calibration_cycle.py": ["unit"],
    "test_adr0053_data_void_gate.py": ["unit", "governance"],
    "test_adversarial_scenarios.py": ["unit", "governance"],
    "test_architectural_invariants.py": ["unit"],
    "test_architecture_md_sync.py": ["unit"],
    "test_archive_v50_ruff.py": ["unit"],
    "test_athlete_calibration_isolation.py": ["unit", "governance"],
    "test_athlete_database_schema_validation.py": ["integration"],
    "test_athlete_isolation_invariant.py": ["unit"],
    "test_automated_periodization.py": ["unit"],
    "test_baseline_drift_detection.py": ["unit", "governance"],
    "test_claude_md_integrity.py": ["unit"],
    "test_cli_entrypoint.py": ["integration"],
    "test_combined_gate_interactions.py": ["unit", "governance"],
    "test_complexity_budget.py": ["integration"],
    "test_concurrency_consistency.py": ["integration"],
    "test_constants_hygiene.py": ["unit"],
    "test_cp_copilot_fixes.py": ["unit"],
    "test_ctl_atl_data_error.py": ["integration"],
    "test_d2_alembic_freeze.py": ["unit"],
    "test_data_sanity.py": ["integration"],
    "test_data_trust_contract.py": ["unit"],
    "test_database_manager_thread_safety.py": ["integration"],
    "test_database_migrations.py": ["integration"],
    "test_db_schema_contracts.py": ["integration"],
    "test_degraded_tracker_persistence.py": ["unit", "governance"],
    "test_documentation_consistency.py": ["unit"],
    "test_e2e_regression_suite.py": ["unit"],
    "test_esi_compensation.py": ["unit"],
    "test_fail_closed_scenarios.py": ["unit", "governance"],
    "test_fitness_functions.py": ["unit"],
    "test_fix_weekly_plan_downgrade.py": ["integration"],
    "test_garmin_csv_import.py": ["unit"],
    "test_garmin_sync.py": ["integration"],
    "test_garmin_sync_worker_lifecycle.py": ["integration"],
    "test_governance_golden.py": ["unit", "governance"],
    "test_governance_golden_cases.py": ["unit", "governance"],
    "test_governance_integration.py": ["unit", "governance"],
    "test_governance_monotonicity.py": ["unit", "governance"],
    "test_governance_mutation.py": ["unit", "governance"],
    "test_governance_rationale.py": ["unit", "governance"],
    "test_gui_wizard_ruff.py": ["integration"],
    "test_harden_db_concurrency.py": ["integration"],
    "test_hd_07_activity_utc_date.py": ["unit", "governance"],
    "test_hydration.py": ["unit"],
    "test_import_activity_laps.py": ["integration"],
    "test_injury_risk_model.py": ["unit"],
    "test_load_prediction_shadow.py": ["unit"],
    "test_main.py": ["unit"],
    "test_metric_lifecycle.py": ["unit"],
    "test_metrics.py": ["integration"],
    "test_ml_explainability.py": ["unit"],
    "test_non_training_stress_partition.py": ["unit", "governance"],
    "test_nutrition_prefs.py": ["integration"],
    "test_operator_console_dashboard.py": ["integration"],
    "test_opus_b1_b2_b3.py": ["integration"],
    "test_opus_category_a_literal_regression_presence_gate.py": ["unit", "governance"],
    "test_opus_evidence_registry_coverage_parity_gate.py": ["unit", "governance"],
    "test_opus_mirrored_test_file_path_contract_gate.py": ["unit", "governance"],
    "test_opus_threshold_source_of_truth_gate.py": ["unit", "governance"],
    "test_outcome_tracker_guardrails.py": ["unit", "governance"],
    "test_outcome_tracker_persistence.py": ["integration"],
    "test_override_handler_registry.py": ["unit"],
    "test_parasympathetic_guard_trigger.py": ["unit"],
    "test_phase3_hygiene.py": ["unit", "governance"],
    "test_phase4_hygiene.py": ["unit", "governance"],
    "test_phase4_observability_flows.py": ["unit"],
    "test_phase7_hardening.py": ["integration"],
    "test_phase7_hygiene.py": ["unit"],
    "test_phase8_ci_checks.py": ["unit", "governance"],
    "test_physiological_bounds.py": ["integration"],
    "test_requirements_telegram_dependency_alignment.py": ["unit", "governance"],
    "test_runner_setup_docs.py": ["unit", "governance"],
    "test_secret_handling_integrations.py": ["unit"],
    "test_security_role_boundary.py": ["unit"],
    "test_setup_env_script.py": ["unit"],
    "test_sync_pipeline_integration.py": ["unit"],
    "test_t4_01_config_gate.py": ["integration", "governance"],
    "test_t4_01_governance_ruff_gate.py": ["integration", "governance"],
    "test_t4_01_quality_gate_phases.py": ["unit", "governance"],
    "test_t4_01_safe_autofix_buckets.py": ["integration", "governance"],
    "test_t4_02_import_hygiene.py": ["unit", "governance"],
    "test_t4_03_typed_payload_contracts.py": ["unit"],
    "test_t4_04_main_context_typing.py": ["unit", "governance"],
    "test_t4_05_architecture_lock.py": ["unit", "governance"],
    "test_t4_25_dependency_drift_audit.py": ["unit", "governance"],
    "test_t4_27_complexity_budget_ci.py": ["unit", "governance"],
    "test_t5_01_retention_strategy.py": ["unit", "governance"],
    "test_t5_02_ui_evolution_path.py": ["unit", "governance"],
    "test_t5_03_multisport_scope_decision.py": ["unit", "governance"],
    "test_t5_04_ml_promotion_gates.py": ["unit", "governance"],
    "test_t5_101_garth_encryption.py": ["unit"],
    "test_t5_110_coach_rbac.py": ["integration", "governance"],
    "test_t5_111_audit_log.py": ["integration"],
    "test_t5_116_manual_entry.py": ["integration"],
    "test_t5_117_profile_unification.py": ["unit"],
    "test_t5_119_profile_editor.py": ["unit"],
    "test_t5_45_hrv_sample_sd.py": ["unit"],
    "test_t5_46_hrv_dedup.py": ["unit"],
    "test_t5_48_garmin_data_age_propagation.py": ["unit", "governance"],
    "test_t5_49_governance_conservative_defaults.py": ["unit", "governance"],
    "test_t5_59_nutrition_dew_point_default.py": ["unit"],
    "test_t5_65_classify_hrv_drop_unknown_acwr.py": ["unit", "governance"],
    "test_t5_66_save_daily_metric_upsert.py": ["integration"],
    "test_t5_67_sync_success_event_gating.py": ["unit"],
    "test_t5_68_esi_dew_point_fallback.py": ["unit", "governance"],
    "test_t5_69_activity_deduplication.py": ["integration"],
    "test_t5_69_stage3_not_null_migration.py": ["integration"],
    "test_td06_dockerfile.py": ["unit", "governance"],
    "test_td17_replay.py": ["unit"],
    "test_td_new_12_sqlite_reads.py": ["integration", "governance"],
    "test_td_new_14_abc_drift.py": ["unit", "governance"],
    "test_td_new_16_corruption.py": ["integration"],
    "test_telegram_calibration_command.py": ["unit"],
    "test_telegram_rate_limit.py": ["unit"],
    "test_telegram_scheduler_lifecycle.py": ["unit"],
    "test_tsb_training_log_source.py": ["integration"],
}

DEF_TEST_RE = re.compile(r'^(\s*)(async\s+)?def\s+(test_\w+)\s*\(')
DECORATOR_RE = re.compile(r'^\s*@')
FIXTURE_DECORATOR_RE = re.compile(r'^\s*@pytest\.fixture')


def add_markers_to_file(filepath: Path, marks: list[str]) -> bool:
    """Add markers above every test function in filepath. Returns True if changed."""
    content = filepath.read_text(encoding="utf-8")
    lines = content.splitlines(keepends=True)

    has_pytest_import = bool(re.search(r'^import pytest\b', content, re.MULTILINE))

    # Build result by scanning forward
    out: list[str] = []
    i = 0
    modified = False

    while i < len(lines):
        line = lines[i]
        m = DEF_TEST_RE.match(line)
        if m:
            indent = m.group(1)
            # Walk backwards in out[] to find where this function's decorator
            # chain starts (skip blank lines among decorators)
            insert_at = len(out)
            j = len(out) - 1
            while j >= 0:
                prev = out[j]
                prev_stripped = prev.strip()
                if DECORATOR_RE.match(prev):
                    # If @pytest.fixture, don't mark this function
                    if FIXTURE_DECORATOR_RE.match(prev):
                        insert_at = None  # signal: skip this function
                        break
                    insert_at = j
                    j -= 1
                elif prev_stripped == "":
                    j -= 1  # allow blank lines between decorator and prev code
                else:
                    break

            if insert_at is not None:
                for mark in marks:
                    out.insert(insert_at, f"{indent}@pytest.mark.{mark}\n")
                    insert_at += 1
                modified = True

        out.append(line)
        i += 1

    if not modified:
        return False

    new_content = "".join(out)

    # Inject `import pytest` if absent
    if not has_pytest_import:
        new_lines = new_content.splitlines(keepends=True)
        # Skip past a leading module docstring
        k = 0
        if new_lines and new_lines[0].lstrip().startswith(('"""', "'''")):
            quote = '"""' if new_lines[0].lstrip().startswith('"""') else "'''"
            # single-line?
            if new_lines[0].count(quote) >= 2:
                k = 1
            else:
                k = 1
                while k < len(new_lines):
                    if quote in new_lines[k]:
                        k += 1
                        break
                    k += 1
        # find first import line
        first_import = None
        for p in range(k, len(new_lines)):
            if re.match(r'\s*(import |from )', new_lines[p]):
                first_import = p
                break
        insert_pos = first_import if first_import is not None else k
        new_lines.insert(insert_pos, "import pytest\n")
        new_content = "".join(new_lines)

    filepath.write_text(new_content, encoding="utf-8")
    return True


def main() -> None:
    tests_dir = Path("tests")
    total = 0
    for filename, marks in sorted(MARKERS.items()):
        filepath = tests_dir / filename
        if not filepath.exists():
            print(f"  MISSING  {filename}")
            continue
        changed = add_markers_to_file(filepath, marks)
        status = "✓" if changed else "~"
        print(f"  {status} {filename}: {', '.join(marks)}")
        if changed:
            total += 1

    print(f"\nModified {total} files.")


if __name__ == "__main__":
    main()

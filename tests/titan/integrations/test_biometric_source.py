"""Mirrored test for titan/integrations/biometric_source.py — T5-79."""
from __future__ import annotations

import pytest

from titan.integrations.biometric_source import (
    BiometricSourceSyncResult,
    NormalizedBiometricSample,
    SourceCapabilities,
)


@pytest.mark.integration
def test_module_imports_without_error() -> None:
    import titan.integrations.biometric_source  # noqa: F401


@pytest.mark.integration
def test_source_capabilities_instantiation() -> None:
    caps = SourceCapabilities(
        source_name="Garmin",
        supports_hrv=True,
        supports_resting_hr=True,
        supports_sleep=False,
        supports_activity_load=True,
    )
    assert caps.source_name == "Garmin"


@pytest.mark.integration
def test_normalized_biometric_sample_none_fields_allowed() -> None:
    sample = NormalizedBiometricSample(
        source_name="Garmin",
        sampled_at="2026-04-19T06:00:00Z",
        hrv_rmssd=None,
        resting_hr=None,
        sleep_hours=None,
        provenance="TRUSTED",
    )
    assert sample.hrv_rmssd is None


@pytest.mark.integration
def test_biometric_source_sync_result_defaults() -> None:
    result = BiometricSourceSyncResult()
    assert result.sync_status == "ok"
    assert result.samples == []
    assert result.failure_class is None


@pytest.mark.integration
def test_normalized_sample_all_fields_populated() -> None:
    sample = NormalizedBiometricSample(
        source_name="Polar",
        sampled_at="2026-04-20T07:00:00Z",
        hrv_rmssd=48.5,
        resting_hr=52,
        sleep_hours=7.5,
        provenance="TRUSTED",
    )
    assert sample.hrv_rmssd == 48.5
    assert sample.resting_hr == 52
    assert sample.sleep_hours == 7.5
    assert sample.sampled_at == "2026-04-20T07:00:00Z"


@pytest.mark.integration
def test_sync_result_failed_status_carries_failure_class() -> None:
    result = BiometricSourceSyncResult(
        sync_status="failed",
        failure_class="auth_error",
    )
    assert result.sync_status == "failed"
    assert result.failure_class == "auth_error"


@pytest.mark.integration
def test_sync_result_degraded_status() -> None:
    result = BiometricSourceSyncResult(sync_status="degraded")
    assert result.sync_status == "degraded"
    assert result.failure_class is None


@pytest.mark.integration
def test_sync_result_samples_list_populated() -> None:
    sample = NormalizedBiometricSample(
        source_name="Whoop",
        sampled_at="2026-04-20T07:00:00Z",
        hrv_rmssd=55.0,
        resting_hr=None,
        sleep_hours=None,
        provenance="INFERRED",
    )
    result = BiometricSourceSyncResult(samples=[sample], sync_status="ok")
    assert len(result.samples) == 1
    assert result.samples[0].source_name == "Whoop"


@pytest.mark.integration
def test_source_capabilities_all_false_allowed() -> None:
    caps = SourceCapabilities(
        source_name="Unknown",
        supports_hrv=False,
        supports_resting_hr=False,
        supports_sleep=False,
        supports_activity_load=False,
    )
    assert caps.source_name == "Unknown"
    assert caps.supports_hrv is False

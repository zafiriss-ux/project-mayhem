"""Mirrored test for titan/integrations/biometric_source.py — T5-79."""
from __future__ import annotations

from titan.integrations.biometric_source import (
    BiometricSourceSyncResult,
    NormalizedBiometricSample,
    SourceCapabilities,
)


def test_module_imports_without_error() -> None:
    import titan.integrations.biometric_source  # noqa: F401


def test_source_capabilities_instantiation() -> None:
    caps = SourceCapabilities(
        source_name="Garmin",
        supports_hrv=True,
        supports_resting_hr=True,
        supports_sleep=False,
        supports_activity_load=True,
    )
    assert caps.source_name == "Garmin"


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


def test_biometric_source_sync_result_defaults() -> None:
    result = BiometricSourceSyncResult()
    assert result.sync_status == "ok"
    assert result.samples == []
    assert result.failure_class is None
